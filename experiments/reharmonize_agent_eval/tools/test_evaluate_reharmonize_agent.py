"""Offline evaluator checks. Simulated provider replies are never evaluation evidence."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import evaluate_reharmonize_agent as evaluation

ROOT = Path(__file__).resolve().parents[3]
BACKEND = Path(os.environ.get("REHARM_EVAL_BACKEND", str(ROOT / "backend")))
API = evaluation.load_backend(BACKEND)
CASES_PATH = ROOT / "experiments/reharmonize_agent_eval/cases.json"
DATA = json.loads(CASES_PATH.read_text())
CASES = evaluation.requests_from(DATA)


class FastScorer:
    label = "simulated-scorer-for-tests"

    def score(self, candidates):
        return [c.model_copy(update={"modelScore": -1.0 - i / 100}) for i, c in enumerate(candidates)]


def memory_ledger(cap=6, stop=None):
    base = evaluation.make_ledger(API, ROOT / "experiments/reharmonize_agent_eval/unused-ledger.json", cap, stop or [False])
    class MemoryLedger(type(base)):
        def __init__(self):
            super().__init__(path=base.path, cap_usd=cap)
            self.state = {"spent_usd": 0.0, "entries": []}

        def _load(self):
            return self.state

        @contextlib.contextmanager
        def _transaction(self):
            yield self.state
            for entry in self.state["entries"]:
                entry.pop("ts", None)

    return MemoryLedger()


class ScriptedTransport:
    def __init__(self, model=evaluation.MODELS["baseten"], bad_first=False):
        self.model, self.calls, self.bad_first = model, 0, bad_first

    def __call__(self, body):
        self.calls += 1
        if self.bad_first and self.calls == 1:
            content = "not JSON"
        else:
            tool_messages = [m for m in body["messages"] if m.get("role") == "user" and m.get("content", "").startswith("Result of")]
            if tool_messages:
                candidates = json.loads(tool_messages[-1]["content"].split("\n", 1)[1])["candidates"]
                ids = list(dict.fromkeys(c["id"] for c in candidates))[:3]
                name, arguments = "offer_candidates", {"candidateIds": ids}
            else:
                name, arguments = "search_substitutions", {"families": ["common_tones", "modal", "dominant"]}
            content = json.dumps({"name": name, "arguments": json.dumps(arguments)})
        return {"id": f"simulated-{self.calls}", "model": self.model,
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100}}, {"x-baseten-request-id": f"simulated-{self.calls}"}


def client_and_ledger(transport=None):
    config = API.llm.LLMConfig.from_env({"LLM_AGENT_PROVIDER": "baseten", "LLM_AGENT_API_KEY": "simulated-only"}, role="agent")
    ledger = memory_ledger()
    ledger.begin_run(12)
    client = evaluation.ObservedClient(API.llm.LLMClient(config, ledger, transport or ScriptedTransport()))
    return client, ledger


def good_response():
    request = CASES[0]["request"]
    client, _ = client_and_ledger()
    response = API.agent.propose(API.Request.model_validate(request), client=client, scorer=FastScorer()).model_dump(mode="json")
    return copy.deepcopy(request), response


class EvaluatorTests(unittest.TestCase):
    def audit(self, request, response, unchanged=True):
        return evaluation.audit_response(API, request, response, unchanged, evaluation.MODELS["baseten"])

    def test_frozen_inputs_and_source_identity(self):
        cases, identity = evaluation.inspect_inputs(API, BACKEND, CASES_PATH)
        self.assertEqual(len(cases), 20)
        self.assertEqual(identity["casesSha256"], "1aa3d5e56ffd2f6c9dba64c9109ec2733de27775d2af17a9a2d278fe202bb100")

    def test_duplicate_case_id_is_rejected(self):
        data = copy.deepcopy(DATA)
        data["cases"][1]["id"] = data["cases"][0]["id"]
        with self.assertRaises(ValueError):
            evaluation.requests_from(data)

    def test_all_twenty_requests_use_real_product_search_with_simulated_judge(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                client, ledger = client_and_ledger()
                req = API.Request.model_validate(case["request"])
                before = req.model_dump(mode="json")
                response = API.agent.propose(req, client=client, scorer=FastScorer()).model_dump(mode="json")
                self.assertTrue(self.audit(case["request"], response, before == req.model_dump(mode="json"))["passed"])
                self.assertEqual(evaluation.billing(ledger.audit_state()["entries"])["attempts"], 2)

    def test_real_f1_context_scorer_with_simulated_provider(self):
        # Checks weight loading and actual learned scores, not the provider's quality.
        for case in (CASES[0], CASES[15]):
            client, _ = client_and_ledger()
            result = API.agent.propose(API.Request.model_validate(case["request"]), client=client)
            self.assertTrue(self.audit(case["request"], result.model_dump(mode="json"))["passed"])
            self.assertTrue(all(c.modelScore is not None for c in result.candidates))
            self.assertEqual(result.modelUsed, "F1 — 10K pop mix")

    def test_semantic_duplicates_with_different_ids_fail(self):
        req, res = good_response()
        res["candidates"][1]["changes"] = copy.deepcopy(res["candidates"][0]["changes"])
        result = self.audit(req, res)
        self.assertTrue(result["checks"]["threeUniqueIds"])
        self.assertFalse(result["checks"]["threeDistinctVersions"])

    def test_change_outside_selection_fails(self):
        req, res = good_response()
        res["candidates"][0]["changes"][0]["address"] = {"measureIndex": 0, "slotIndex": 0}
        self.assertFalse(self.audit(req, res)["checks"]["outsideSelectionPreserved"])

    def test_change_limit_and_repeated_address_fail(self):
        req, res = good_response()
        res["candidates"][0]["changes"] *= 2
        checks = self.audit(req, res)["checks"]
        self.assertFalse(checks["changeBoundsRespected"])
        self.assertFalse(checks["addressesValid"])

    def test_wrong_before_value_fails(self):
        req, res = good_response()
        res["candidates"][0]["changes"][0]["before"] = "B"
        self.assertFalse(self.audit(req, res)["checks"]["beforeValuesMatch"])

    def test_local_choice_never_counts_as_model_completion(self):
        req, res = good_response()
        res.update(selection="local", metaModel="not used")
        self.assertFalse(self.audit(req, res)["passed"])
        self.assertFalse(self.audit(req, res)["checks"]["modelCompleted"])

    def test_input_mutation_fails(self):
        req, res = good_response()
        self.assertFalse(self.audit(req, res, False)["passed"])

    def test_missing_candidates_fail(self):
        req, res = good_response()
        res["candidates"] = []
        self.assertFalse(self.audit(req, res)["passed"])

    def test_retry_attempt_is_preserved_in_ledger(self):
        client, ledger = client_and_ledger(ScriptedTransport(bad_first=True))
        API.agent.propose(API.Request.model_validate(CASES[0]["request"]), client=client, scorer=FastScorer())
        entries = ledger.audit_state()["entries"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["status"], "failed")
        self.assertTrue(all(e["request_id"] for e in entries))
        self.assertTrue(all("ts" not in e for e in entries))

    def test_per_run_reservation_cannot_exceed_cap(self):
        ledger = memory_ledger()
        ledger.begin_run(12)
        entry = ledger.reserve(label="first", provider="baseten", model="model", reserved_usd=.1)
        ledger.settle(entry, settled_usd=.1, status="settled")
        with self.assertRaises(API.llm.BudgetExceeded):
            ledger.reserve(label="retry", provider="baseten", model="model", reserved_usd=.06)
        self.assertEqual(len(ledger.audit_state()["entries"]), 1)

    def test_global_budget_is_independent_of_per_run_budget(self):
        ledger = memory_ledger(.1)
        ledger.begin_run(12)
        with self.assertRaises(API.llm.SpendCapReached):
            ledger.reserve(label="first", provider="baseten", model="model", reserved_usd=.11)

    def test_attempt_cap_stops_before_reservation(self):
        ledger = memory_ledger()
        ledger.begin_run(1)
        entry = ledger.reserve(label="one", provider="baseten", model="model", reserved_usd=.01)
        ledger.settle(entry, settled_usd=.001, status="settled")
        with self.assertRaises(API.llm.BudgetExceeded):
            ledger.reserve(label="two", provider="baseten", model="model", reserved_usd=.01)

    def test_cancellation_stops_before_send(self):
        ledger = memory_ledger(stop=[True])
        ledger.begin_run(12)
        with self.assertRaises(API.llm.LLMCancelled):
            ledger.reserve(label="one", provider="baseten", model="model", reserved_usd=.01)

    def test_ledger_removes_work_timestamp_before_persisting(self):
        ledger = evaluation.make_ledger(API, ROOT / "experiments/reharmonize_agent_eval/unused.json", 6, [False])
        state = {"entries": [{"ts": "forbidden", "request_id": "id"}]}
        with patch.object(API.llm.Ledger, "_write") as write:
            ledger._write(state)
        self.assertNotIn("ts", write.call_args.args[0]["entries"][0])

    def test_unknown_usage_is_a_reservation_not_measured_cost(self):
        result = evaluation.billing([
            {"settled_usd": .02, "usage": {"completion_tokens": 2}, "status": "settled"},
            {"settled_usd": .08, "usage": None, "status": "failed"},
            {"settled_usd": None, "usage": None, "status": "reserved", "reserved_usd": .01},
        ])
        self.assertEqual(result["returnedUsageCostUsd"], .02)
        self.assertEqual(result["unknownUsageReservationUsd"], .08)
        self.assertEqual(result["accountedCostUsd"], .1)
        self.assertEqual(result["outstandingUsd"], .01)

    def test_failed_and_unstarted_rows_stay_in_denominator(self):
        rows = [{"caseId": "same", "repeat": 1, "status": "failed", "elapsedSeconds": 4},
                {"caseId": "same", "repeat": 2, "status": "not_started"}]
        result = evaluation.summary(rows)
        self.assertEqual(result["distinctPassages"], 1)
        self.assertEqual(result["checksPassedOverAllScheduled"]["modelCompleted"], {"passed": 0, "denominator": 2})
        self.assertEqual(result["bothRepeatsPassed"], 0)
        self.assertEqual(result["latencySecondsAllStarted"]["n"], 1)

    def test_full_runner_offline_with_no_file_or_network_writes(self):
        cases, identity = evaluation.inspect_inputs(API, BACKEND, CASES_PATH)
        ledger = memory_ledger()
        args = SimpleNamespace(approved_max_usd=6, provider="baseten", out=ROOT / "experiments/reharmonize_agent_eval/not-created",
            cases_sha256=identity["casesSha256"], service_sha256=identity["serviceSha256"], checkpoint_sha256=identity["checkpointSha256"])
        reports = []
        original_propose = API.agent.propose
        def propose(req, **kwargs):
            return original_propose(req, scorer=FastScorer(), **kwargs)
        with patch.dict(os.environ, {"BASETEN_API_KEY": "simulated-only"}), \
             patch.object(API.agent, "meta_budget_unlimited", return_value=False), \
             patch.object(evaluation, "make_ledger", return_value=ledger), \
             patch.object(API.llm, "OpenAITransport", side_effect=lambda config: ScriptedTransport()), \
             patch.object(API.agent, "propose", side_effect=propose), \
             patch.object(Path, "mkdir"), \
             patch.object(evaluation, "safe_write", side_effect=lambda path, report, secret: reports.append(copy.deepcopy(report))), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(evaluation.execute(API, args, cases, identity), 0)
        final = reports[-1]
        self.assertEqual(final["summary"]["passedRuns"], 40)
        self.assertEqual(final["summary"]["distinctPassages"], 20)
        self.assertEqual(final["ledgerTotals"]["attempts"], 80)
        self.assertEqual(final["ledgerTotals"]["outstandingUsd"], 0)
        self.assertTrue(all(r["httpAttempts"] and r["turns"] for r in final["runs"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
