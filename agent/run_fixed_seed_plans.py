"""Bounded live paired planner evaluation with request-local chord sampling seeds.

Runs rules then Meta for each public fixture, with one explicit neural checkpoint.
The two arms share request, seed derivation, temperatures and postprocessing. Meta
planning itself is not seeded. Writes new results only, with no work-date metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
from unittest import mock

from plan_and_generate import load_requests, record, write_results
from app.models.plan import PlanRequest
from app.models.schemas import MAX_SEED
from app.services import inference, planner
from app.services.llm import Ledger, LLMClient, LLMConfig


def request_seed(seed: int, name: str) -> int:
    return (seed + int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big")) & MAX_SEED


def token_records(ledger: Ledger, start: int) -> list[dict]:
    if not ledger.path.exists():
        return []
    entries = json.loads(ledger.path.read_text(encoding="utf-8"))["entries"][start:]
    fields = ("label", "provider", "model", "request_id", "response_id", "usage", "status",
              "reserved_usd", "settled_usd", "latency_ms")
    return [{key: entry.get(key) for key in fields} for entry in entries]


def evaluate(requests: list[tuple[str, dict]], seed: int, model: str, out: Path, client: LLMClient) -> None:
    if out.exists():
        raise ValueError("Output folder already exists; preserve previous results and choose a new output folder")
    documents = {
        arm: {"planner": arm, "effort": "medium" if arm == "meta" else None, "samplingSeed": seed,
              "chordModel": model, "requests": len(requests), "spentUsd": 0.0, "stopped": None,
              "controls": {"temperatures": [t for t, _ in inference._TEMPS], "rag": False,
                           "voiceLeading": not bool(os.getenv("THEARTIST_DISABLE_VOICE_LEADING")),
                           "seedDerivation": "sha256(request name)[0:4]+base seed; section +1009*i; regen +1000003; candidate +i",
                           "metaSeeded": False, "sourceRequired": "ai"}, "runs": []}
        for arm in ("rules", "meta")
    }
    for number, (name, body) in enumerate(requests, 1):
        for arm in ("rules", "meta"):
            totals = client.ledger.snapshot()
            if arm == "meta" and totals["spent_usd"] + totals["outstanding_usd"] + planner.MAX_RUN_USD > client.ledger.cap_usd:
                raise RuntimeError("Evaluation cap leaves insufficient room for another bounded Meta run")
            req = PlanRequest.model_validate({**body, "planner": arm, "seed": request_seed(seed, name), "modelKey": model})
            events = []
            generations = []

            def observe(event: str, payload: dict) -> None:
                events.append((event, payload["t_ms"]))
                if event == "generate_section":
                    generations.append({key: payload[key] for key in
                                        ("index", "source", "modelUsed", "regenerated", "sectionType", "bars")})

            with mock.patch.object(planner, "get_client", return_value=client), mock.patch.object(planner, "PLAN_EFFORT", "medium"):
                trace = planner.complete_form(req, observe)
            run = record(name, req, trace, events)
            run["samplingSeed"] = req.seed
            run["requestBody"] = req.model_dump(mode="json")
            run["apiUsage"] = token_records(client.ledger, totals["entries"])
            run["generationAttempts"] = generations
            wrong = [i for i, section in enumerate(generations)
                     if section["source"] != "ai" or section["modelUsed"] != model]
            if trace.status == "ok" and len(generations) < len(trace.sections):
                wrong.append("missing provenance")
            if wrong:
                run["evaluationError"] = f"Generation attempts {wrong} did not use the required neural checkpoint"
            document = documents[arm]
            document["runs"].append(run)
            document["spentUsd"] = round(sum(item["costUsd"] for item in document["runs"]), 8)
            if trace.status != "ok" or wrong:
                document["stopped"] = run.get("evaluationError") or (trace.error.message if trace.error else "run failed")
            filename = "rules.json" if arm == "rules" else "meta-medium.json"
            write_results(out / filename, document)
            print(f"{number}/{len(requests)} {arm} {name}: {trace.status}, {len(trace.sections)} neural sections, "
                  f"{trace.elapsedMs / 1000:.1f}s, ${trace.spendUsd:.4f}; batch ledger ${client.ledger.snapshot()['spent_usd']:.4f}",
                  flush=True)
            if document["stopped"]:
                raise RuntimeError(document["stopped"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--model", default="ft_f1")
    parser.add_argument("--max-usd", type=float, default=10)
    args = parser.parse_args()
    if not 0 <= args.seed <= MAX_SEED or not 0 < args.max_usd <= 10:
        parser.error("seed must be uint32 and this batch cap must be in (0, 10]")
    if not os.getenv("MODEL_API_KEY"):
        parser.error("MODEL_API_KEY is not configured")
    os.environ["THEARTIST_DISABLE_RAG"] = "1"
    requests = load_requests(args.requests)
    resolved = inference._resolve_model(args.model, lambda *_: None)
    if resolved is None or resolved[0].name != args.model:
        raise RuntimeError("Required neural checkpoint is unavailable; evaluation has not called Meta")
    ledger = Ledger(args.ledger, args.max_usd)
    config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                       api_key=os.environ["MODEL_API_KEY"], key_source="MODEL_API_KEY")
    client = LLMClient(config, ledger)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s | %(message)s")
    evaluate(requests, args.seed, args.model, args.out, client)
    print(f"Completed paired batch. Shared evaluation ledger spent ${ledger.snapshot()['spent_usd']:.6f} / ${ledger.cap_usd:.2f}.")


if __name__ == "__main__":
    main()
