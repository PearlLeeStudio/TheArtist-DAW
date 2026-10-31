"""Real-edition import coverage, with optional three bounded live Meta readings.

This is an evaluation runner, not a unit test. Source PDFs remain outside the repo.
Key, meter and written-bar counts are source facts, not harmonic ground truth.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from statistics import mean

# Count written measures once, without unfolding repeat signs. These facts were
# read from each corresponding LilyPond source, not inferred from MIDI playback.
REFERENCE = {
    "bach-bwv846-prelude": {"key": "C major", "meter": [4, 4], "writtenBars": 35},
    "mozart-k2-minuet": {"key": "F major", "meter": [3, 4], "writtenBars": 24},
    "schumann-op68-1": {"key": "C major", "meter": [4, 4], "writtenBars": 20},
}


def add_note_evidence(report, sources):
    """Exploratory note evidence, not an expert harmonic-label accuracy score."""
    import mido
    from annotated_music_eval import describe
    midi = mido.MidiFile(sources / "bach-bwv846-prelude.mid")
    position = 0
    bars = {}
    for event in mido.merge_tracks(midi.tracks):
        position += event.time
        if event.type == "note_on" and event.velocity:
            index = position // (midi.ticks_per_beat * 4)
            bars.setdefault(index, set()).add(event.note % 12)
    if len(bars) != 35 or bars[0] != {0, 4, 7} or bars[1] != {0, 2, 5, 9}:
        raise ValueError("Unexpected Bach reference alignment")
    case = next(c for c in report["cases"] if c["id"] == "bach-bwv846-prelude")
    if case.get("meta", {}).get("status") != "completed":
        return
    actual = case["meta"]["response"]["measures"]
    scored = []
    # The first 32 bars have the recurring arpeggio pattern. The final three
    # change texture. Selection follows source layout, not model agreement.
    for index in range(32):
        expected = bars[index]
        predicted = set()
        error = None
        try:
            for symbol in actual[index]["chords"]:
                predicted.update(describe(symbol)["pcs"])
        except (ValueError, IndexError, TypeError) as exc:
            error = type(exc).__name__
            predicted.clear()
        intersection = len(expected & predicted)
        scored.append({"writtenBar": index + 1, "referenceNoteOnPcs": sorted(expected),
                       "proposedChordPcs": sorted(predicted), "exactPitchSet": predicted == expected,
                       "precision": intersection / len(predicted) if predicted else 0,
                       "recall": intersection / len(expected),
                       "jaccard": intersection / len(expected | predicted), "errorType": error})
    case["noteEvidence"] = {
        "method": "Union of proposed chord pitch classes versus reference MIDI note-on pitch classes in each of Bach BWV 846 written bars 1–32. No repeats/pickup; 4 quarter notes per bar. Final three texture-changing bars excluded. Exploratory evidence overlap, not harmonic correctness or note transcription accuracy.",
        "midiSha256": hashlib.sha256((sources / "bach-bwv846-prelude.mid").read_bytes()).hexdigest(),
        "bars": scored, "exactPitchSets": sum(b["exactPitchSet"] for b in scored),
        **{field: mean(b[field] for b in scored) for field in ("precision", "recall", "jaccard")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "sources", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--meta-ledger", type=Path)
    parser.add_argument("--rescore", type=Path, help="Add note evidence to saved readings without Meta calls")
    args = parser.parse_args()
    if any(not p.is_absolute() for p in (args.backend, args.sources, args.output)):
        parser.error("Use absolute paths")
    if args.output.exists():
        parser.error("Preserve existing results; choose a new output")
    if args.meta_ledger and not args.meta_ledger.is_absolute():
        parser.error("Use an absolute ledger path")
    if args.rescore:
        if not args.rescore.is_absolute() or args.meta_ledger:
            parser.error("Rescoring uses an absolute saved result and no Meta ledger")
        report = json.loads(args.rescore.read_text())
        add_note_evidence(report, args.sources)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        evidence = next(c for c in report["cases"] if c["id"] == "bach-bwv846-prelude")["noteEvidence"]
        print(json.dumps({k: v for k, v in evidence.items() if k != "bars"}))
        return
    sys.path.insert(0, str(args.backend))
    from app.models.score_import import ScoreImportRequest
    from app.services import score_import
    from app.services.score_pdf import parse_vector_score
    from app.services.llm import Ledger, LLMClient, LLMConfig, OpenAITransport

    sources = json.loads((args.sources / "sources.json").read_text())["mutopia"]
    client = None
    calls = []
    if args.meta_ledger:
        if not os.environ.get("MODEL_API_KEY"):
            parser.error("MODEL_API_KEY is required for the explicit paid mode")
        cfg = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                        api_key=os.environ["MODEL_API_KEY"], key_source="MODEL_API_KEY", timeout_s=75)
        transport = OpenAITransport(cfg)

        def recorded(body):
            completion, headers = transport(body)
            calls.append({"requestId": headers.get("x-request-id"), "model": completion.get("model"),
                          "usage": completion.get("usage"), "choices": completion.get("choices")})
            return completion, headers

        client = LLMClient(cfg, Ledger(args.meta_ledger, 5.0), recorded)
    report = {"method": "Eight editions / seven unique compositions; local support coverage. Three fixed editions optionally read by Meta. Written-bar/key/meter agreement does not establish chord correctness.",
              "maxMetaCalls": 3, "batchCapUsd": 5.0 if client else 0, "cases": []}
    for source in sources:
        data = (args.sources / source["files"]["pdf"]["file"]).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != source["files"]["pdf"]["sha256"]:
            raise ValueError("Source digest mismatch")
        record = {"id": source["id"], "sourcePage": source["sourcePage"], "license": source["license"],
                  "sha256": digest}
        try:
            local = parse_vector_score(data)
            record["local"] = {"supported": local.supported, "complete": local.complete,
                               "bars": len(local.measures), "notes": sum(len(m.notes) for m in local.measures),
                               "key": local.key, "meter": local.time_signature,
                               "unresolved": local.unresolved}
        except Exception as exc:
            record["local"] = {"supported": False, "errorType": type(exc).__name__}
        reference = REFERENCE.get(source["id"])
        if client and reference:
            record["reference"] = reference
            calls.clear()
            before = client.ledger.snapshot()["entries"]
            request = ScoreImportRequest(filename=source["id"] + ".pdf", mimeType="application/pdf",
                                         dataBase64=base64.b64encode(data).decode(), engine="meta", mode="infer_harmony")
            try:
                with patch.object(score_import, "get_client", return_value=client):
                    response = score_import.import_score(request)
                record["meta"] = {"status": "completed", "response": response.model_dump(mode="json"),
                                  "barCountMatches": len(response.measures) == reference["writtenBars"],
                                  "keyMatches": response.key == reference["key"],
                                  "meterMatches": response.timeSignature == reference["meter"],
                                  "chordAccuracyScored": False}
            except Exception as exc:
                record["meta"] = {"status": "failed", "errorType": type(exc).__name__,
                                  "requestId": getattr(exc, "request_id", None)}
            fields = ("label", "provider", "model", "request_id", "usage", "status", "settled_usd", "latency_ms")
            entries = json.loads(client.ledger.path.read_text())["entries"][before:]
            record["apiUsage"] = [{field: item.get(field) for field in fields} for item in entries]
            record["rawCompletions"] = list(calls)
        report["cases"].append(record)
        report["localSupported"] = sum(c["local"]["supported"] for c in report["cases"])
        if client:
            snapshot = client.ledger.snapshot()
            report["spentUsd"], report["outstandingUsd"] = snapshot["spent_usd"], snapshot["outstanding_usd"]
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"case": source["id"], "local": record["local"],
                          "meta": {k: v for k, v in record.get("meta", {}).items() if k != "response"}}), flush=True)
    if client:
        add_note_evidence(report, args.sources)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Local support: {report['localSupported']}/{len(sources)}; Meta spend ${report.get('spentUsd', 0):.6f}")


if __name__ == "__main__":
    main()
