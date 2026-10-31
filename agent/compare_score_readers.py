"""Five fixed scores, four paired reading conditions; at most 15 paid turns, $5 ledger.

Hybrid 2 shares Hybrid 1's first pass, then rechecks the original once with that
draft. This is a small diagnostic comparison, not population accuracy or a judge.
References never enter prompts. Failures stay in the denominator. No retries.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch


def cases(backend, sources):
    from tests.vector_score_fixture import build_vector_score_pdf
    yield "original-triad", build_vector_score_pdf(), {
        "bars": 1, "key": "C major", "meter": [4, 4], "chords": [["C"]], "notes": [[0, 4, 7]],
        "license": "MIT; original test artwork", "chordReference": "Designed sustained triad"}
    yield "original-mixed-counts", build_vector_score_pdf(
        measure_steps=((0, 2, 4), (), (0, 2, 4), ()),
        printed_chords=(("C",), ("Dm", "G7"), ("C",), ("N.C.",))), {
        "bars": 4, "key": None, "meter": [4, 4], "chords": [["C"], ["Dm", "G7"], ["C"], []],
        "notes": [[0, 4, 7], [], [0, 4, 7], []], "noChord": [False, False, False, True],
        "license": "MIT; original test artwork", "chordReference": "Printed symbols, including one/two per bar and N.C."}
    yield "original-context-gap", build_vector_score_pdf(
        measure_steps=((0, 2, 4), (1,), (4, 6, 8)), printed_chords=(("C",), (), ("G7",))), {
        "bars": 3, "key": None, "meter": [4, 4], "chords": [["C"], None, ["G7"]],
        "notes": [[0, 4, 7], [2], [2, 7, 11]], "ambiguousTargets": [1],
        "license": "MIT; original test artwork", "chordReference": "Printed outer bars only; D4-only middle has no unique harmony label"}
    manifest = json.loads((sources / "sources.json").read_text())["mutopia"]
    for name, count, key, meter in (("mozart-k2-minuet", 24, "F major", [3, 4]),
                                    ("bach-bwv846-prelude", 35, "C major", [4, 4])):
        source = next(item for item in manifest if item["id"] == name)
        data = (sources / source["files"]["pdf"]["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != source["files"]["pdf"]["sha256"]:
            raise ValueError("Source hash mismatch")
        reference = {"bars": count, "key": key, "meter": meter, "sourcePage": source["sourcePage"],
                     "license": source["license"], "chordReference": "Not scored: no expert harmonic labels"}
        if name == "bach-bwv846-prelude":
            import mido
            midi = mido.MidiFile(sources / source["files"]["midi"]["file"])
            ticks, notes = 0, [set() for _ in range(35)]
            for event in mido.merge_tracks(midi.tracks):
                ticks += event.time
                if event.type == "note_on" and event.velocity:
                    notes[ticks // (midi.ticks_per_beat * 4)].add(event.note % 12)
            reference["notes"] = [sorted(pitches) for pitches in notes]
            reference["noteReference"] = "All 35 written MIDI bars, no repeats/pickup; pitch-class sets, not harmony labels"
        yield name, data, reference


def metrics(response, reference):
    from app.services.score_context import score_context
    from annotated_music_eval import describe
    bars = response.measures if response is not None else []
    aligned = len(bars) == reference["bars"]
    result = {"completed": response is not None, "barCount": len(bars), "barCountMatches": aligned,
              "keyMatches": (response.key == reference["key"] if response else False) if reference["key"] else None,
              "meterMatches": response.timeSignature == reference["meter"] if response else False,
              "unresolved": sum(not bar.chords and not bar.noChord for bar in bars),
              "missingBars": max(0, reference["bars"] - len(bars))}
    chord_scores = []
    for i, expected in enumerate(reference.get("chords", [])):
        if expected is None:
            continue
        try:
            actual = bars[i].chords if aligned else None
            match = actual is not None and len(actual) == len(expected) and all(
                describe(a) == describe(b) for a, b in zip(actual, expected))
            if reference.get("noChord", [False] * reference["bars"])[i]:
                match = match and bars[i].noChord
        except (IndexError, ValueError):
            match = False
        chord_scores.append({"bar": i + 1, "match": bool(match)})
    result["chordBars"] = chord_scores
    note_scores = []
    context = score_context(response) if response is not None and bars else None
    for i, expected in enumerate(reference.get("notes", [])):
        actual = context["measures"][i]["pitchClasses"] if aligned and context else None
        note_scores.append({"bar": i + 1, "match": actual == expected,
                            "actual": actual, "reference": expected})
    result["noteBars"] = note_scores
    result["ambiguousProposals"] = [{"bar": i + 1, "chords": bars[i].chords if aligned else [],
                                       "recoveredOriginalClaim": False} for i in reference.get("ambiguousTargets", [])]
    return result


def evaluate(backend, sources, output, ledger_path):
    from app.models.score_import import ScoreImportRequest
    from app.services import score_import
    from app.services.score_analysis import analyze_local_score, LocalScoreUnsupported
    from app.services.score_context import score_context
    from app.services.score_verification import compare_readings
    from app.services.llm import Ledger, LLMClient, LLMConfig, OpenAITransport

    if output.exists():
        raise ValueError("Preserve previous results; output already exists")
    cfg = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                    api_key=os.environ["MODEL_API_KEY"], key_source="MODEL_API_KEY", timeout_s=75)
    transport, calls = OpenAITransport(cfg), []
    turns = 0
    def recorded(body):
        nonlocal turns
        if turns >= 15:
            raise RuntimeError("Evaluation turn cap reached")
        turns += 1
        completion, headers = transport(body)
        calls.append({"requestId": headers.get("x-request-id"), "model": completion.get("model"),
                      "usage": completion.get("usage"), "choices": completion.get("choices")})
        return completion, headers
    client = LLMClient(cfg, Ledger(ledger_path, 5.0), recorded)
    report = {"method": __doc__, "maxTurns": 15, "ledgerCapUsd": 5, "cases": []}
    fields = ("label", "provider", "model", "request_id", "usage", "status", "settled_usd", "latency_ms")
    for name, data, reference in cases(backend, sources):
        req = ScoreImportRequest(filename=name + ".pdf", mimeType="application/pdf",
                                  dataBase64=base64.b64encode(data).decode(), mode="infer_harmony", engine="local")
        record = {"id": name, "sha256": hashlib.sha256(data).hexdigest(), "reference": reference, "conditions": {}}
        report["cases"].append(record)
        def run(label, operation):
            start, before = time.perf_counter(), client.ledger.snapshot()["entries"]
            calls.clear()
            response, error = None, None
            try:
                response = operation()
            except Exception as exc:
                error = {"type": type(exc).__name__, "requestId": getattr(exc, "request_id", None)}
            elapsed = time.perf_counter() - start
            entries = json.loads(ledger_path.read_text())["entries"][before:] if ledger_path.exists() else []
            item = {"status": "failed" if error else "completed", "error": error,
                    "seconds": round(elapsed, 3), "costUsd": sum(e.get("settled_usd", 0) for e in entries),
                    "apiUsage": [{f: entry.get(f) for f in fields} for entry in entries],
                    "rawCompletions": list(calls), "response": response.model_dump(mode="json") if response else None,
                    "metrics": metrics(response, reference)}
            record["conditions"][label] = item
            report["ledger"] = {k: v for k, v in client.ledger.snapshot().items() if k != "path"}
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"case": name, "condition": label, "status": item["status"],
                              "seconds": item["seconds"], "costUsd": item["costUsd"],
                              "bars": item["metrics"]["barCount"], "error": error}), flush=True)
            return response
        with patch.object(score_import, "get_client", return_value=client):
            local = run("local", lambda: score_import.import_score(req))
            meta_req = req.model_copy(update={"engine": "meta"})
            run("meta", lambda: score_import.import_score(meta_req))
            # Reuse the exact local result in both hybrid conditions. A local
            # unsupported file is an explicit absence, never a fabricated input.
            if local is None:
                try:
                    analyze_local_score(req)
                except LocalScoreUnsupported:
                    pass
                else:
                    raise RuntimeError("Local completion failed for a supported file; stop before hybrid")
            attachment = score_import._attachment(req)
            def first_pass():
                checked = score_import._import_meta_score(req, attachment, local_context=score_context(local) if local else None)
                return compare_readings(local, checked)
            first = run("hybrid1", first_pass)
            first_item = record["conditions"]["hybrid1"]
            def second_pass():
                if first is None:
                    raise ValueError("First hybrid pass failed; second pass is not attempted")
                original_messages = score_import._messages
                def messages(mode, media, local_context=None):
                    result = original_messages(mode, media, local_context)
                    result[-1]["content"].insert(0, {"type": "text", "text":
                        "Second and final review: re-read the original independently, then check this prior draft. "
                        "Correct unsupported notes/chords, preserve written order and printed counts. A prior draft "
                        "is not ground truth. Explain remaining ambiguity. Prior draft musical data: "
                        + json.dumps(score_context(first), ensure_ascii=False)})
                    return result
                with patch.object(score_import, "_messages", side_effect=messages):
                    checked = score_import._import_meta_score(req, attachment, local_context=score_context(local) if local else None)
                return compare_readings(local, checked)
            run("hybrid2", second_pass)
            second = record["conditions"]["hybrid2"]
            second["incrementalSeconds"], second["incrementalCostUsd"] = second["seconds"], second["costUsd"]
            for label in ("hybrid1", "hybrid2"):
                record["conditions"][label]["seconds"] += record["conditions"]["local"]["seconds"]
            second["seconds"] += first_item["seconds"] - record["conditions"]["local"]["seconds"]
            second["costUsd"] += first_item["costUsd"]
            second["sharedFirstPass"] = "hybrid1"
            report["ledger"] = {k: v for k, v in client.ledger.snapshot().items() if k != "path"}
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "sources", "output", "ledger"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if not all(path.is_absolute() for path in vars(args).values()):
        parser.error("Use absolute paths")
    sys.path.insert(0, str(args.backend))
    evaluate(args.backend, args.sources, args.output, args.ledger)


if __name__ == "__main__":
    main()
