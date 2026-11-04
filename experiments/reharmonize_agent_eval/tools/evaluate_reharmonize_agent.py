"""Evaluate the unmodified product search, independently of fixed-pool selection.

Preflight is offline. Paid execution needs explicit budget and input/code/weight
hash acknowledgments. No server, product configuration or existing result is edited.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
from collections import Counter
from types import SimpleNamespace

PROTOCOL = "reharmonize-agent-reliability-v1"
MODELS = {"baseten": "meta-models/muse-spark-open-1026", "meta": "muse-spark-1.3"}
AUDIT_CHECKS = ("modelCompleted", "threeCandidates", "threeUniqueIds", "threeDistinctVersions",
                "outsideSelectionPreserved", "changeBoundsRespected", "addressesValid",
                "beforeValuesMatch", "inputUnchanged", "finishedWithOffer")
SERVICE_FILES = (
    "app/models/reharmonize.py", "app/services/reharmonize_agent.py",
    "app/services/reharmonize.py", "app/services/llm.py",
    "app/services/chord_context.py", "app/services/inference.py",
    "app/services/env_flags.py",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Use an absolute path")
    return path.resolve()


def load_backend(backend):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(backend))
    from app.models.reharmonize import ReharmRequest
    from app.services import llm, reharmonize, reharmonize_agent
    if not Path(reharmonize_agent.__file__).resolve().is_relative_to(backend):
        raise ValueError("The imported product is not the requested backend")
    return SimpleNamespace(llm=llm, search=reharmonize, agent=reharmonize_agent, Request=ReharmRequest)


def requests_from(data):
    if data["protocol"] != PROTOCOL or data["repeats"] != 2 or data["modelKey"] != "ft_f1" or data["mode"] != "auto":
        raise ValueError("Unexpected frozen protocol")
    cases = data["cases"]
    if len(cases) != 20 or len({c["id"] for c in cases}) != 20:
        raise ValueError("Exactly twenty unique case IDs are required")
    if Counter(c["key"].split()[1] for c in cases) != {"major": 10, "minor": 10}:
        raise ValueError("Expected ten major and ten minor cases")
    if Counter(c["complexity"] for c in cases) != {"simple": 10, "complex": 10}:
        raise ValueError("Expected ten simple and ten complex cases")
    if Counter(c["maxChanges"] for c in cases) != {1: 5, 2: 5, 3: 5, 4: 5}:
        raise ValueError("Expected five cases per change limit")
    return [{"id": c["id"], "complexity": c["complexity"], "request": {
        "key": c["key"], "timeSignature": c["meter"], "modelKey": data["modelKey"], "mode": data["mode"],
        "context": [{"measure": i, "chords": bar} for i, bar in enumerate(c["bars"])],
        "selectedSlots": [{"measureIndex": m, "slotIndex": s} for m, s in c["selected"]],
        "maxChanges": c["maxChanges"],
    }} for c in cases]


def inspect_inputs(api, backend, cases_path):
    data = json.loads(cases_path.read_text())
    cases = requests_from(data)
    signatures = []
    for case in cases:
        req = api.Request.model_validate(case["request"])
        api.search.validate_context(req)
        tonic = api.search.pitch(req.key.split()[0])
        # Reject transpositions of the same passage, irrespective of selection/limit.
        signatures.append(canonical([[(
            (api.search.chord(s)[0] - tonic) % 12,
            sorted((pc - tonic) % 12 for pc in api.search.chord(s)[1]),
            (api.search.chord(s)[2] - tonic) % 12,
        ) if s else None for s in bar.chords] for bar in req.context]))
    if len(set(signatures)) != 20:
        raise ValueError("Two passages are identical or transpositions of each other")
    source_hashes = {name: file_hash(backend / name) for name in SERVICE_FILES}
    for name in ("model.py", "tokenizer.py"):
        source_hashes["ai/training/" + name] = file_hash(backend.parent / "ai/training" / name)
    checkpoint = backend.parent / "ai/checkpoints/ft_jazz_pop80/best.pt"
    limits = {name: getattr(api.agent, name) for name in (
        "MAX_USD", "MAX_TURNS", "MAX_TOOL_CALLS", "MAX_SECONDS", "MAX_COMPLETION_TOKENS")}
    expected = dict(MAX_USD=.15, MAX_TURNS=4, MAX_TOOL_CALLS=6, MAX_SECONDS=100, MAX_COMPLETION_TOKENS=4096)
    if limits != expected:
        raise ValueError("Product limits differ from the prepared protocol; review before execution")
    identity = {
        "protocol": PROTOCOL, "casesSha256": file_hash(cases_path),
        "requestsSha256": digest(cases), "serviceSha256": digest(source_hashes), "sourceFiles": source_hashes,
        "checkpointSha256": file_hash(checkpoint) if checkpoint.is_file() else None,
        "modelKey": "ft_f1", "limits": limits,
        "evaluatorSha256": file_hash(Path(__file__).resolve()),
    }
    return cases, identity


def audit_response(api, request, response, input_unchanged, expected_model):
    original = {(b["measure"], s): value for b in request["context"] for s, value in enumerate(b["chords"])}
    selected = {(s["measureIndex"], s["slotIndex"]) for s in request["selectedSlots"]}
    candidates = response.get("candidates", [])
    outside_ok = before_ok = bounds_ok = addresses_ok = True
    versions = []
    counts = []
    for candidate in candidates:
        updated = dict(original)
        seen = set()
        changes = candidate["changes"]
        counts.append(len(changes))
        bounds_ok &= 1 <= len(changes) <= request["maxChanges"]
        for change in changes:
            address = (change["address"]["measureIndex"], change["address"]["slotIndex"])
            addresses_ok &= address in original and address not in seen
            outside_ok &= address in selected
            before_ok &= original.get(address) == change["before"] and change["before"] != change["after"]
            seen.add(address)
            updated[address] = change["after"]
        outside_ok &= all(updated.get(a) == v for a, v in original.items() if a not in selected)
        normalized = []
        for address, symbol in sorted(updated.items()):
            if symbol is None:
                normalized.append((address, None))
            else:
                root, tones, bass, _ = api.search.chord(symbol)
                normalized.append((address, root, sorted(tones), bass))
        versions.append(canonical(normalized))
    checks = {
        "modelCompleted": response.get("selection") == "meta" and response.get("metaModel") == expected_model,
        "threeCandidates": len(candidates) == 3,
        "threeUniqueIds": len(candidates) == 3 and len({c["id"] for c in candidates}) == 3,
        "threeDistinctVersions": len(candidates) == 3 and len(set(versions)) == 3,
        "outsideSelectionPreserved": bool(candidates) and outside_ok,
        "changeBoundsRespected": bool(candidates) and bounds_ok,
        "addressesValid": bool(candidates) and addresses_ok,
        "beforeValuesMatch": bool(candidates) and before_ok,
        "inputUnchanged": input_unchanged,
        "finishedWithOffer": response.get("toolCalls", [])[-1:] == ["offer_candidates"],
    }
    return {"checks": checks, "passed": all(checks.values()), "changeCounts": counts}


def billing(entries):
    settled = [e for e in entries if e.get("settled_usd") is not None]
    return {
        "attempts": len(entries),
        "accountedCostUsd": round(sum(e["settled_usd"] for e in settled), 8),
        "returnedUsageCostUsd": round(sum(e["settled_usd"] for e in settled if e.get("usage") is not None), 8),
        "unknownUsageReservationUsd": round(sum(e["settled_usd"] for e in settled if e.get("usage") is None), 8),
        "outstandingUsd": round(sum(e["reserved_usd"] for e in entries if e.get("status") == "reserved"), 8),
    }


def summary(records):
    started = [r for r in records if r["status"] != "not_started"]
    latencies = sorted(r["elapsedSeconds"] for r in started)
    checks = AUDIT_CHECKS
    return {
        "scheduledRuns": len(records), "distinctPassages": len({r["caseId"] for r in records}),
        "startedRuns": len(started), "passedRuns": sum(r["status"] == "passed" for r in records),
        "statusCounts": dict(Counter(r["status"] for r in records)),
        "checksPassedOverAllScheduled": {k: {"passed": sum(r.get("audit", {}).get("checks", {}).get(k, False) for r in records),
                                             "denominator": len(records)} for k in checks},
        "bothRepeatsPassed": sum(all(r["status"] == "passed" for r in records if r["caseId"] == c)
                                 for c in {r["caseId"] for r in records}),
        "latencySecondsAllStarted": {"n": len(latencies), **{
            name: latencies[max(0, math.ceil(len(latencies) * p) - 1)] if latencies else None
            for name, p in (("p50", .5), ("p95", .95))}},
        "accountedCostUsd": round(sum(r.get("billing", {}).get("accountedCostUsd", 0) for r in records), 8),
        "httpAttempts": sum(r.get("billing", {}).get("attempts", 0) for r in records),
        "extraAttemptsWithinToolTurns": sum(r.get("extraAttemptsWithinToolTurns", 0) for r in records),
        "within100SecondsOverAllScheduled": {"passed": sum(r.get("within100Seconds", False) for r in records), "denominator": len(records)},
        "returnedUsageCostUsd": round(sum(r.get("billing", {}).get("returnedUsageCostUsd", 0) for r in records), 8),
        "unknownUsageReservationUsd": round(sum(r.get("billing", {}).get("unknownUsageReservationUsd", 0) for r in records), 8),
    }


def safe_write(path, value, secret=""):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if secret and secret in text:
        raise ValueError("Refusing to persist a credential")
    pending = path.with_name(path.name + ".pending")
    with pending.open("x", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def make_ledger(api, path, cap, stop):
    class EvaluationLedger(api.llm.Ledger):
        """Same product reservation/settlement, with an independent experiment cap."""
        run_start_spend = 0.0
        run_start_entries = 0
        max_attempts = 12

        def audit_state(self):
            # The product's public snapshot contains an entry count, not entries.
            # This evaluation is strictly sequential and owns this dedicated ledger.
            return copy.deepcopy(self._load())

        def _write(self, state):
            for entry in state["entries"]:
                entry.pop("ts", None)
            super()._write(state)

        def begin_run(self, max_attempts):
            state = self.audit_state()
            self.run_start_spend = state["spent_usd"]
            self.run_start_entries = len(state["entries"])
            self.max_attempts = max_attempts

        def reserve(self, **kwargs):
            if stop[0]:
                raise api.llm.LLMCancelled("Evaluation stopped before the next paid attempt")
            state = self.audit_state()
            spent = state["spent_usd"] - self.run_start_spend
            entries = state["entries"][self.run_start_entries:]
            outstanding = billing(entries)["outstandingUsd"]
            if len(entries) >= self.max_attempts or spent + outstanding + kwargs["reserved_usd"] > .15 + 1e-8:
                raise api.llm.BudgetExceeded("Evaluation per-run safety limit", spent_usd=spent,
                    outstanding_usd=outstanding, request_usd=kwargs["reserved_usd"], cap_usd=.15)
            return super().reserve(**kwargs)

    return EvaluationLedger(path=path, cap_usd=cap, unlimited=False)


class ObservedClient:
    def __init__(self, client):
        self.client, self.config = client, client.config
        self.turns = []

    def chat_tools(self, messages, tools, **kwargs):
        entry = {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools), "options": kwargs}
        self.turns.append(entry)
        try:
            reply = self.client.chat_tools(messages, tools, **kwargs)
            entry["reply"] = reply.to_dict()
            return reply
        except Exception as exc:
            entry["error"] = {"type": type(exc).__name__, "kind": getattr(exc, "kind", None)}
            raise


def execute(api, args, cases, identity):
    if not 0 < args.approved_max_usd <= 6:
        raise ValueError("Approve a positive per-arm cap no greater than $6")
    if api.agent.meta_budget_unlimited():
        raise ValueError("Unlimited mode is set; refusing evaluation without changing that setting")
    for name, expected in (("cases_sha256", "casesSha256"), ("service_sha256", "serviceSha256"),
                           ("checkpoint_sha256", "checkpointSha256")):
        if not identity[expected] or getattr(args, name) != identity[expected]:
            raise ValueError("Acknowledged input/code/checkpoint hash mismatch: " + name)
    if args.provider == "meta":
        env = {"MODEL_API_KEY": os.environ.get("MODEL_API_KEY", ""), "LLM_AGENT_PROVIDER": "meta"}
    else:
        key = os.environ.get("BASETEN_API_KEY", "")
        if not key and os.environ.get("LLM_AGENT_PROVIDER") == "baseten":
            key = os.environ.get("LLM_AGENT_API_KEY", "")
        env = {"LLM_AGENT_PROVIDER": "baseten", "LLM_AGENT_API_KEY": key}
    env["LLM_AGENT_REASONING_EFFORT"] = "low"
    config = api.llm.LLMConfig.from_env(env, role="agent")
    if not config.api_key or config.model != MODELS[args.provider]:
        raise ValueError("The explicitly selected provider credential/model is unavailable")
    if args.out.exists():
        raise ValueError("Use a new output directory; previous evidence is never overwritten")
    args.out.mkdir(parents=True)
    stop = [False]
    def stop_after_attempt(signum, frame):
        stop[0] = True
    old_handlers = {s: signal.signal(s, stop_after_attempt) for s in (signal.SIGINT, signal.SIGTERM)}
    ledger = make_ledger(api, args.out / "ledger.json", args.approved_max_usd, stop)
    records = [{"caseId": c["id"], "repeat": repeat, "request": c["request"], "status": "not_started"}
               for repeat in (1, 2) for c in cases]
    report = {"identity": identity, "provider": config.provider, "model": config.model,
              "reasoningEffort": "low", "approvedMaxUsd": args.approved_max_usd,
              "pricesPerMillion": {"input": config.price_input_per_m, "cached": config.price_cached_per_m,
                                   "output": config.price_output_per_m, "source": config.price_source},
              "scope": "In-process product agent and real F1 scoring; excludes browser, HTTP admission, deployment and MIDI export.",
              "runs": records}
    def persist():
        report["summary"] = summary(records)
        report["ledgerTotals"] = billing(ledger.audit_state()["entries"])
        safe_write(args.out / "results.json", report, config.api_key)
    try:
        persist()
        for record in records:
            if stop[0]:
                break
            state = ledger.audit_state()
            if state["spent_usd"] + .15 > args.approved_max_usd + 1e-8:
                report["stoppedReason"] = "Insufficient approved budget to reserve another complete run"
                break
            ledger.begin_run(12 if args.provider == "baseten" else 4)
            raw_attempts = []
            transport = api.llm.OpenAITransport(config)
            def observed_transport(body):
                attempt = {"request": copy.deepcopy(body)}
                raw_attempts.append(attempt)
                began = time.monotonic()
                try:
                    response, headers = transport(body)
                    # Whitelist provider data; omit provider timestamps and unrelated headers.
                    attempt["response"] = {k: response[k] for k in ("id", "model", "choices", "usage") if k in response}
                    attempt["responseHeaders"] = {k: v for k, v in headers.items()
                                                 if k.lower() in ("x-request-id", "x-baseten-request-id")}
                    return response, headers
                except Exception as exc:
                    attempt["error"] = {"type": type(exc).__name__, "statusCode": getattr(exc, "status_code", None)}
                    raise
                finally:
                    attempt["elapsedSeconds"] = round(time.monotonic() - began, 6)
            client = ObservedClient(api.llm.LLMClient(config=config, ledger=ledger, transport=observed_transport))
            req = api.Request.model_validate(record["request"])
            before = req.model_dump(mode="json")
            began = time.monotonic()
            try:
                response = api.agent.propose(req, client=client).model_dump(mode="json")
                record["response"] = response
                record["audit"] = audit_response(api, record["request"], response,
                                                  before == req.model_dump(mode="json"), config.model)
                record["status"] = "passed" if record["audit"]["passed"] else "local_selection" if response["selection"] == "local" else "failed_checks"
            except Exception as exc:
                record["status"] = "cancelled" if isinstance(exc, api.llm.LLMCancelled) else "failed"
                record["error"] = {"type": type(exc).__name__, "kind": getattr(exc, "kind", None),
                                   "statusCode": getattr(exc, "status_code", None),
                                   "requestId": getattr(exc, "request_id", None)}
            finally:
                record["elapsedSeconds"] = round(time.monotonic() - began, 6)
                record["within100Seconds"] = record["elapsedSeconds"] <= 100
                entries = ledger.audit_state()["entries"][ledger.run_start_entries:]
                record["billing"] = billing(entries)
                record["apiUsage"] = entries
                record["turns"] = client.turns
                record["httpAttempts"] = raw_attempts
                # Count attempts by tool-turn label, including malformed replies and failed turns.
                record["extraAttemptsWithinToolTurns"] = sum(max(0, n - 1) for n in Counter(e["label"] for e in entries).values())
                persist()
        if stop[0]:
            report["stoppedReason"] = "Interrupted; active attempt settled; unstarted runs retained"
        persist()
    finally:
        for s, handler in old_handlers.items():
            signal.signal(s, handler)
    print(json.dumps(report["summary"], indent=2))
    return 0 if all(r["status"] == "passed" for r in records) else 1


def compare(left, right):
    a, b = json.loads(left.read_text()), json.loads(right.read_text())
    for field in ("protocol", "casesSha256", "requestsSha256", "serviceSha256", "checkpointSha256", "limits", "evaluatorSha256"):
        if a["identity"][field] != b["identity"][field]:
            raise ValueError("Unpaired comparison: " + field)
    if {a["provider"], b["provider"]} != {"meta", "baseten"}:
        raise ValueError("Compare one arm per provider")
    keyed = lambda report: {(r["caseId"], r["repeat"]): r for r in report["runs"]}
    aa, bb = keyed(a), keyed(b)
    if len(aa) != 40 or aa.keys() != bb.keys() or len(bb) != 40:
        raise ValueError("Both arms must retain all forty scheduled rows")
    if any(aa[k]["request"] != bb[k]["request"] for k in aa):
        raise ValueError("Musical inputs changed between providers")
    return {"scope": "Paired execution reliability, not listening preference; two repeats share each of twenty passages.",
            "arms": {a["provider"]: summary(a["runs"]), b["provider"]: summary(b["runs"])},
            "bothArmsPassed": sum(aa[k]["status"] == bb[k]["status"] == "passed" for k in aa)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "run"):
        p = sub.add_parser(name)
        p.add_argument("--backend", type=absolute, required=True)
        p.add_argument("--cases", type=absolute, required=True)
        if name == "run":
            p.add_argument("--provider", choices=MODELS, required=True)
            p.add_argument("--out", type=absolute, required=True)
            p.add_argument("--approved-max-usd", type=float, required=True)
            for item in ("cases", "service", "checkpoint"):
                p.add_argument("--" + item + "-sha256", required=True)
    p = sub.add_parser("compare")
    p.add_argument("--left", type=absolute, required=True)
    p.add_argument("--right", type=absolute, required=True)
    args = parser.parse_args()
    if args.command == "compare":
        print(json.dumps(compare(args.left, args.right), indent=2))
        return 0
    api = load_backend(args.backend)
    cases, identity = inspect_inputs(api, args.backend, args.cases)
    if args.command == "preflight":
        print(json.dumps({"identity": identity, "distinctPassages": len(cases), "scheduledRunsPerArm": 40,
            "networkCalls": 0, "sourceOfInputs": "authored fixtures, not sampled songs", "weightsAvailable": identity["checkpointSha256"] is not None,
            "suggestedCapPerArmUsd": 6, "typicalHttpAttemptsPerArmFromExistingTrace": "80–120; not a forecast for these inputs",
            "hardEvaluationHttpAttemptLimits": {"baseten": 480, "meta": 160}}, indent=2))
        return 0
    return execute(api, args, cases, identity)


if __name__ == "__main__":
    raise SystemExit(main())
