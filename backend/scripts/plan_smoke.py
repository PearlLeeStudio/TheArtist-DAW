"""One real planner run: POST /api/plan/song in-process over a pop 8-bar sketch, targetBars 32.

Run from backend/:
    uv run python -m scripts.plan_smoke --dry-run   print the request; no network, nothing written
    uv run python -m scripts.plan_smoke [--out PATH] one billed run (about 0.01-0.05 USD): Muse Spark
                                                   plans and judges, the chord model writes the sections

Writes experiments/meta/plan_smoke.json: the request and the trace (plan, validation attempts,
sections, judgments, every call's request id and cost). Never the key, and no local path. When
Meta is disabled or not configured the run fails before any call and that failure is recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "experiments" / "meta" / "plan_smoke.json"
ROUTE = "/api/plan/song"


def measure(index: int, chords: list[str | None], roman: list[str | None]) -> dict:
    return {"index": index, "chords": chords, "roman": roman}


REQUEST = {
    "genre": "pop", "key": "C major", "bpm": 110, "timeSignature": [4, 4],
    "measures": [
        measure(0, ["Cmaj7", "Am7"], ["Imaj7", "vi7"]), measure(1, ["Dm7", "G7"], ["ii7", "V7"]),
        measure(2, ["Cmaj7", "Am7"], ["Imaj7", "vi7"]), measure(3, ["Dm7", "G7"], ["ii7", "V7"]),
        measure(4, ["Fmaj7", "G7"], ["IVmaj7", "V7"]), measure(5, ["Em7", "Am7"], ["iii7", "vi7"]),
        measure(6, ["Fmaj7", "G7"], ["IVmaj7", "V7"]), measure(7, ["Cmaj", None], ["I", None]),
    ],
    "sections": [{"type": "verse", "start": 0, "length": 8, "label": "Verse 1"}],
    "targetBars": 32, "wantOutro": True, "contrast": "medium", "planner": "meta",
}


def _print_trace(trace: dict) -> None:
    print(f"status      {trace['status']}" + (f" ({trace['error']['kind']}: {trace['error']['message']})" if trace.get("error") else ""))
    if trace.get("plan"):
        print("plan        " + ", ".join(f"{s['type']} {s['bars']} ({s['cadence']})" for s in trace["plan"]["sections"]))
    for attempt in trace.get("validation", []):
        print(f"validate #{attempt['attempt']}  {'ok' if attempt['ok'] else 'rejected: ' + '; '.join(i['message'] for i in attempt['errors'])}")
    for call in trace.get("calls", []):
        print(f"call        {call['step']} #{call['attempt']} {call['provider']} {call['model']} effort={call['effort']} "
              f"request_id={call['requestId']} ${call['costUsd']:.6f} {call['latencyMs']} ms{'' if call['ok'] else ' FAILED'}")
    for section in trace.get("sections", []):
        print(f"section     {section['sectionType']} bars {section['startMeasure']}-{section['startMeasure'] + section['bars'] - 1} "
              f"source={section['source']} model={section['modelUsed']} rulesSlots={section['rulesSlots']}"
              + (" regenerated" if section["regenerated"] else ""))
    for judged in trace.get("judge", []):
        print(f"judge       {judged['decision']} {[(t['section'], t['reason']) for t in judged['targets']]}")
    print(f"spend       ${trace.get('spendUsd', 0):.6f} (reserved ${trace.get('reservedUsd', 0):.4f}), "
          f"{trace.get('elapsedMs', 0)} ms (meta {trace.get('metaMs', 0)} ms, chord model {trace.get('generationMs', 0)} ms)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One real planner run over a pop 8-bar sketch.")
    parser.add_argument("--dry-run", action="store_true", help="print the request and exit without network I/O")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the run record (JSON)")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("dry run: nothing is sent")
        print(json.dumps(REQUEST, indent=2))
        return 0

    from fastapi.testclient import TestClient  # the app loads torch; only when a run is wanted

    import app.main

    with TestClient(app.main.app) as client:
        response = client.post(ROUTE, json=REQUEST)
    trace = response.json()
    _print_trace(trace)
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "route": ROUTE,
              "statusCode": response.status_code, "request": REQUEST, "trace": trace}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out.relative_to(REPO) if args.out.is_relative_to(REPO) else args.out.name}")
    return 0 if trace.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
