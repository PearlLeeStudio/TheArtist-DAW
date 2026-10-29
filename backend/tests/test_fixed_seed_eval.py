"""Offline guards for the paid paired evaluation's controls and provenance."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.models.plan import PlanTrace
from tests.test_agent_eval_requests import fixtures, load_runner


def runner_module():
    path = Path(__file__).resolve().parents[2] / "agent" / "run_fixed_seed_plans.py"
    spec = importlib.util.spec_from_file_location("run_fixed_seed_plans", path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"plan_and_generate": load_runner()}):
        spec.loader.exec_module(module)
    return module


class FixedSeedEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.runner = runner_module()
        self.out = mock.Mock(spec=Path)
        self.out.exists.return_value = False
        self.out.__truediv__ = mock.Mock(return_value=Path("unused-result.json"))
        self.ledger = mock.Mock(cap_usd=10)
        self.ledger.snapshot.return_value = {"spent_usd": 0, "outstanding_usd": 0, "entries": 0}
        self.client = SimpleNamespace(ledger=self.ledger)
        self.fixture = [("new_pop_32", fixtures()["new_pop_32"])]

    def fake_run(self, req, emit):
        emit("generate_section", {"t_ms": 1, "index": 0, "source": "ai", "modelUsed": "ft_f1",
                                  "regenerated": False, "sectionType": "verse", "bars": 8})
        return PlanTrace(planner=req.planner, genre=req.genre, key=req.key, status="ok",
                         bpm=req.bpm, timeSignature=req.timeSignature, plan=None, validation=[],
                         sections=[], judge=[], calls=[], spendUsd=0, reservedUsd=0,
                         elapsedMs=1, metaMs=0, generationMs=1)

    def test_matched_arms_share_seed_and_model_and_capture_every_attempt(self):
        requests, outputs = [], []

        def compose(req, emit):
            requests.append(req)
            return self.fake_run(req, emit)

        with mock.patch.object(self.runner.planner, "complete_form", side_effect=compose), \
                mock.patch.object(self.runner, "token_records", return_value=[]), \
                mock.patch.object(self.runner, "write_results", side_effect=lambda _, doc: outputs.append(doc)), \
                mock.patch("builtins.print"):
            self.runner.evaluate(self.fixture, 1380, "ft_f1", self.out, self.client)
        self.assertEqual([req.planner for req in requests], ["rules", "meta"])
        self.assertEqual(requests[0].seed, requests[1].seed)
        self.assertEqual([req.modelKey for req in requests], ["ft_f1", "ft_f1"])
        self.assertEqual([len(doc["runs"][0]["generationAttempts"]) for doc in outputs], [1, 1])

    def test_rules_fallback_is_rejected_even_when_later_attempt_is_ai(self):
        outputs = []

        def compose(req, emit):
            emit("generate_section", {"t_ms": 0, "index": 0, "source": "rules", "modelUsed": None,
                                      "regenerated": False, "sectionType": "verse", "bars": 8})
            return self.fake_run(req, emit)

        with mock.patch.object(self.runner.planner, "complete_form", side_effect=compose), \
                mock.patch.object(self.runner, "token_records", return_value=[]), \
                mock.patch.object(self.runner, "write_results", side_effect=lambda _, doc: outputs.append(doc)), \
                mock.patch("builtins.print"), self.assertRaisesRegex(RuntimeError, "Generation attempts"):
            self.runner.evaluate(self.fixture, 1380, "ft_f1", self.out, self.client)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(len(outputs[0]["runs"][0]["generationAttempts"]), 2)
        self.assertIn("required neural checkpoint", outputs[0]["stopped"])

    def test_preserves_previous_output_folder(self):
        self.out.exists.return_value = True
        with self.assertRaisesRegex(ValueError, "already exists"), \
                mock.patch.object(self.runner.planner, "complete_form") as complete:
            self.runner.evaluate(self.fixture, 1380, "ft_f1", self.out, self.client)
        complete.assert_not_called()

    def test_exhausted_batch_cap_stops_before_the_next_meta_run(self):
        self.ledger.snapshot.return_value = {"spent_usd": 9.95, "outstanding_usd": 0, "entries": 0}
        with mock.patch.object(self.runner.planner, "complete_form", side_effect=self.fake_run) as complete, \
                mock.patch.object(self.runner, "token_records", return_value=[]), \
                mock.patch.object(self.runner, "write_results"), mock.patch("builtins.print"), \
                self.assertRaisesRegex(RuntimeError, "insufficient room"):
            self.runner.evaluate(self.fixture, 1380, "ft_f1", self.out, self.client)
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(complete.call_args.args[0].planner, "rules")


if __name__ == "__main__":
    unittest.main()
