"""Exercise an installed reconstruction through HTTP with real F1, without Meta."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.root.is_absolute() or not args.out.is_absolute() or args.out.exists():
        parser.error("Use an absolute app root and a new absolute report path")
    sys.path[:0] = [str(args.root / "backend"), str(args.root)]
    os.environ.update(THEARTIST_PUBLIC_HOST="1", THEARTIST_SERVE_FRONTEND="1", THEARTIST_META_ENABLED="0",
                      THEARTIST_DISABLE_RAG="0", THEARTIST_RAG_OMT_ENABLED="1", THEARTIST_RAG_BERKLEE_ENABLED="0")
    import app.main
    import mido
    from fastapi.testclient import TestClient
    from app.models.plan import PlanRequest
    from agent.export_plan_samples import snapshot

    if not Path(app.main.__file__).is_relative_to(args.root):
        raise SystemExit("Wrong app import; run with the reconstructed backend environment")
    with TestClient(app.main.app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json() == {"status": "ok"}
        sources = client.get("/api/capabilities").json()["data"]["rag"]["sources"]
        assert sources == {"omt": "ready", "berklee": "disabled"}
        raw = (args.root / "experiments/import_eval/context-20.pdf").read_bytes()
        imported = client.post("/api/import/score", json=dict(filename="original.pdf", mimeType="application/pdf",
                               dataBase64=base64.b64encode(raw).decode(), engine="local", mode="infer_harmony"))
        assert imported.status_code == 200, imported.status_code
        measures = imported.json()["measures"]
        assert len(measures) == 20
        sketch = [dict(index=i, chords=(bar["chords"] + [None, None])[:2], roman=[None, None])
                  for i, bar in enumerate(measures)]
        req = PlanRequest(genre="pop", key="C major", measures=sketch, targetBars=64, wantOutro=True,
                          chorusMode="reuse", planner="rules", modelKey="ft_f1", seed=17)
        response = client.post("/api/plan/song", json=req.model_dump(mode="json"))
        assert response.status_code == 200, response.status_code
        trace = response.json()
        assert trace["status"] == "ok" and not trace["calls"]
        assert all(s["source"] in {"ai", "reuse"} for s in trace["sections"])
        assert all(s["modelUsed"] == "ft_f1" for s in trace["sections"] if s["source"] == "ai")
        spec = snapshot(dict(request="original-sketch", requestBody=req.model_dump(mode="json"), trace=trace), "completion")
        exported_sketch = [[chord["symbol"] if chord else None for chord in bar["chords"]]
                           for bar in spec.model_dump()["measures"][:20]]
        assert exported_sketch == [bar["chords"] for bar in sketch]
        midi = client.post("/api/export/midi", json=spec.model_dump(mode="json"))
        assert midi.status_code == 200
        decoded = mido.MidiFile(file=io.BytesIO(midi.content))
        ticks = 64 * 4 * decoded.ticks_per_beat
        assert len(decoded.tracks) == 4 and all(sum(e.time for e in t) == ticks for t in decoded.tracks)
        report = dict(staticUI=True, health=True, rag=sources, importedBars=len(measures), targetBars=64,
                      sourceCounts={source: sum(s["source"] == source for s in trace["sections"]) for source in ("ai", "reuse")},
                      model="ft_f1", metaCalls=0, midiBytes=len(midi.content), midiTracks=len(decoded.tracks),
                      midiBars=64, scope="Fresh reconstructed app, in-process HTTP; cached downloads; not browser/DAW/audio or external hosting")
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
