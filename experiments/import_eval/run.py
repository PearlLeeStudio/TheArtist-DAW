"""Paid import smoke evaluation using only the repository's self-authored fixtures.

Pass absolute paths for the backend, three source fixtures, generated context PDF,
private ledger and output JSON. The batch cap defaults to $3 and cannot exceed $10.
This is an evaluation runner, never a unit test; it performs real Meta requests.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch


def absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Supply an absolute path")
    return path


def combine_fixture_pages(pages: list[bytes]) -> bytes:
    """Join this repository's simple, uncompressed Type3 fixtures; not a general PDF merger."""
    objects: dict[int, bytes] = {1: b"<< /Type /Catalog /Pages 2 0 R >>", 2: b""}
    page_ids = []
    for data in pages:
        source = {int(number): body for number, body in re.findall(rb"(?m)^(\d+) 0 obj\n(.*?)\nendobj", data, re.S)}
        if not source or b"/Type /Page " not in source.get(3, b"") or b"/Count 1" not in source.get(2, b""):
            raise ValueError("Only the single-page original vector fixtures are supported")
        mapping = {1: 1, 2: 2}
        for number in sorted(source):
            if number >= 3:
                mapping[number] = len(objects) + 1
                objects[mapping[number]] = b""
        for number, body in source.items():
            if number >= 3:
                objects[mapping[number]] = re.sub(rb"(\d+) 0 R", lambda match: f"{mapping[int(match[1])]} 0 R".encode(), body)
        page_ids.append(mapping[3])
    objects[2] = ("<< /Type /Pages /Kids [" + " ".join(f"{number} 0 R" for number in page_ids)
                  + f"] /Count {len(page_ids)} >>").encode()
    document = bytearray(b"%PDF-1.4\n%original-import-evaluation\n")
    offsets = [0]
    for number, body in objects.items():
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(document)


def musical_request(body: dict) -> dict:
    """Retain exact text context but omit attachment bytes, credentials and time metadata."""
    copied = json.loads(json.dumps(body))
    for message in copied.get("messages", []):
        if isinstance(message.get("content"), list):
            for part in message["content"]:
                if part.get("type") == "image_url":
                    part["image_url"]["url"] = "<self-authored image fixture bytes omitted>"
                elif part.get("type") == "file":
                    part["file"]["file_data"] = "<self-authored PDF fixture bytes omitted>"
    return copied


def evaluation_summary(cases: list[dict]) -> dict:
    """Keep successful requests distinct from successful score reading."""
    return {
        "requestsCompleted": all(case["status"] == "completed" for case in cases),
        "allChordReadingExact": all(
            case.get("chordReading", {}).get("exactMatches") == len(case["expected"]["chords"])
            and case.get("chordReading", {}).get("actualBars") == len(case["expected"]["chords"])
            and case.get("chordReading", {}).get("keyMatches") is not False
            for case in cases
        ),
        "formAccuracyScored": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "fixture-c", "fixture-f", "fixture-png", "context-pdf", "ledger", "output"):
        parser.add_argument("--" + name, type=absolute, required=True)
    parser.add_argument("--budget-usd", type=float, default=3.0)
    parser.add_argument("--case", action="append", choices=("vector-c", "vector-f", "context-20", "notes-png"))
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 10:
        parser.error("The approved batch budget must be positive and at most $10")
    if args.output.exists():
        parser.error("The output already exists; preserve it and choose another output path")
    sys.path.insert(0, str(args.backend))
    from app.models.score_import import ScoreImportRequest
    from app.services import harmony_meta, score_import
    from app.services.llm import Ledger, LLMClient, LLMConfig, OpenAITransport
    from app.services.score_analysis import analyze_local_score
    from app.services.score_context import score_context

    original_c, original_f, original_png = args.fixture_c.read_bytes(), args.fixture_f.read_bytes(), args.fixture_png.read_bytes()
    context_pdf = combine_fixture_pages([original_c] * 8 + [original_f] * 8 + [original_c] * 4)
    args.context_pdf.write_bytes(context_pdf)
    cases = [
        ("vector-c", original_c, "application/pdf", "auto", ["C"], "C major"),
        ("vector-f", original_f, "application/pdf", "auto", ["F"], "F major"),
        ("context-20", context_pdf, "application/pdf", "auto", ["C"] * 8 + ["F"] * 8 + ["C"] * 4, None),
        ("notes-png", original_png, "image/png", "meta", ["C", "Am", "Dm", "G7"], "C major"),
    ]
    selected = set(args.case or [case[0] for case in cases])
    # Every vector case is locally parsed and its complete synopsis validated
    # before a transport exists. Unexpected PDF-merger/parser errors cost nothing.
    prepared = []
    for name, data, mime, engine, expected_chords, expected_key in cases:
        if name not in selected:
            continue
        request = ScoreImportRequest(filename=name + (".png" if mime == "image/png" else ".pdf"),
                                     mimeType=mime, dataBase64=base64.b64encode(data).decode("ascii"),
                                     engine=engine, mode="infer_harmony")
        local = analyze_local_score(request) if engine == "auto" else None
        if local is not None:
            if len(local.measures) != len(expected_chords):
                raise ValueError(f"{name}: expected {len(expected_chords)} locally read bars, got {len(local.measures)}")
            score_context(local)
        prepared.append((name, data, request, expected_chords, expected_key, local))

    config = LLMConfig.from_env()
    if config.provider != "meta" or config.model != "muse-spark-1.3":
        raise ValueError("Use the Meta Standard muse-spark-1.3 configuration")
    ledger = Ledger(args.ledger, args.budget_usd)
    transport = OpenAITransport(config)
    active_calls: list[dict] = []

    def recorded(body):
        call = {"request": musical_request(body)}
        active_calls.append(call)
        try:
            completion, headers = transport(body)
            call.update(requestId=headers.get("x-request-id"), model=completion.get("model"),
                        choices=completion.get("choices"), usage=completion.get("usage"))
            return completion, headers
        except Exception as exc:
            # SDK exception strings may carry configuration/URLs; retain only its type here.
            call["transportError"] = type(exc).__name__
            raise

    client = LLMClient(config, ledger, recorded)
    report = {"schemaVersion": 1, "model": config.model, "batchCapUsd": args.budget_usd,
              "method": "Original fixtures; real Meta calls. Optical/chord correctness and uncertain form interpretation are reported separately.",
              "cases": []}
    for name, data, request, expected_chords, expected_key, local in prepared:
        active_calls.clear()
        before = ledger.snapshot()["spent_usd"]
        case = {"name": name, "engine": request.engine, "fixtureSha256": hashlib.sha256(data).hexdigest(),
                "expected": {"chords": expected_chords, "key": expected_key},
                "localReading": local.model_dump() if local is not None else None}
        try:
            with patch.object(harmony_meta, "get_client", return_value=client), patch.object(score_import, "get_client", return_value=client):
                result = score_import.import_score(request)
            actual = [bar.chords for bar in result.measures]
            correct = [actual[index] == [chord] if index < len(actual) else False
                       for index, chord in enumerate(expected_chords)]
            case.update(status="completed", response=result.model_dump(),
                        chordReading={"expectedBars": len(expected_chords), "actualBars": len(actual),
                                      "exactMatches": sum(correct), "perBarExact": correct,
                                      "keyMatches": result.key == expected_key if expected_key else None},
                        formInterpretation={"sections": [section.model_dump() for section in result.sections],
                                            "claim": "Suggestions only; this fixture has no printed song-form ground truth."})
        except Exception as exc:
            case.update(status="failed", error={"type": type(exc).__name__, "message": str(exc),
                                               "requestId": getattr(exc, "request_id", None)})
        case["calls"] = copy_calls = json.loads(json.dumps(active_calls))
        case["callCount"] = len(copy_calls)
        case["costUsd"] = round(ledger.snapshot()["spent_usd"] - before, 8)
        report["cases"].append(case)
        report["totalCostUsd"] = round(sum(item["costUsd"] for item in report["cases"]), 8)
        report["evaluation"] = evaluation_summary(report["cases"])
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"case": name, "status": case["status"], "calls": case["callCount"],
                          "costUsd": case["costUsd"], "chordReading": case.get("chordReading"),
                          "error": case.get("error")}), flush=True)
    if not report["evaluation"]["requestsCompleted"]:
        return 1
    return 0 if report["evaluation"]["allChordReadingExact"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
