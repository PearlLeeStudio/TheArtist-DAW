"""The planner evaluation fixtures (experiments/agent_eval/requests) and their runner
(agent/plan_and_generate.py): every request file is a valid PlanRequest the rules planner can
satisfy, the set has the promised shape, the Roman numerals are the editor's, and the runner
records a run, keeps keys and local paths out of its file and stops at the spend limit.
No network, no model."""

import importlib.util
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.models.plan import PlanRequest
from app.services import planner
from app.services.llm import Ledger, LLMClient, LLMConfig
from tests.test_planner import ACCEPT, CALL_COST, KEY, FakeComposer, Replies, completion

REPO = Path(__file__).resolve().parents[2]
REQUESTS = REPO / "experiments" / "agent_eval" / "requests"
RUNNER = REPO / "agent" / "plan_and_generate.py"
NEW_GENRES = {"pop", "jazz", "blues", "electronic", "gospel"}
NEW_LENGTHS = {32, 64}
_QUIET = logging.NullHandler()

# frontend/src/engine/romanNumeral.ts, for the chord qualities the sketches use
_NOTE_VALUES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
                "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
_LETTERS = "CDEFGAB"
_SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10)}
_MINOR_QUALITIES = {"m", "m7", "dim", "dim7", "m7b5", "m6"}
_SUFFIX = {"": "", "m": "", "7": "7", "maj7": "maj7", "m7": "7", "dim": "°", "dim7": "°7", "m7b5": "ø7",
           "6": "6", "m6": "6", "9": "9", "sus4": "sus4", "add9": "add9"}
# A plan that is valid for new_pop_32: 32 bars, intro first in an empty song, no outro, lands
POP_32_PLAN = {"sections": [
    {"type": "intro", "bars": 4, "cadence": "none", "reason": "Open", "cites": []},
    {"type": "verse", "bars": 8, "cadence": "half", "reason": "Verse", "cites": []},
    {"type": "chorus", "bars": 8, "cadence": "authentic", "reason": "Hook", "cites": []},
    {"type": "verse", "bars": 8, "cadence": "half", "reason": "Second verse", "cites": []},
    {"type": "chorus", "bars": 4, "cadence": "authentic", "reason": "Last hook", "cites": []},
]}


def setUpModule():
    for name in ("app.services.llm", "app.services.planner"):
        logging.getLogger(name).addHandler(_QUIET)


def tearDownModule():
    for name in ("app.services.llm", "app.services.planner"):
        logging.getLogger(name).removeHandler(_QUIET)


def editor_roman(symbol: str, key: str) -> str:
    head = symbol.split("/")[0]
    root = head[:2] if len(head) >= 2 and head[1] in "#b" else head[:1]
    quality = head[len(root):]
    key_root, mode = key.split()
    degree = (_LETTERS.index(root[0]) - _LETTERS.index(key_root[0])) % 7
    numeral = ["I", "II", "III", "IV", "V", "VI", "VII"][degree]
    if quality in _MINOR_QUALITIES:
        numeral = numeral.lower()
    interval = (_NOTE_VALUES[root] - _NOTE_VALUES[key_root]) % 12
    alteration = ((interval - _SCALES[mode][degree] + 18) % 12) - 6
    return ("#" * alteration if alteration > 0 else "b" * -alteration) + numeral + _SUFFIX[quality]


def load_runner():
    spec = importlib.util.spec_from_file_location("plan_and_generate", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixtures() -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(REQUESTS.glob("*.json"))}


class RequestFixturesTest(unittest.TestCase):
    def test_every_request_is_valid_and_the_rules_planner_can_satisfy_it(self):
        bodies = fixtures()
        self.assertEqual(len(bodies), 20)
        for name, body in bodies.items():
            with self.subTest(request=name):
                self.assertNotIn("planner", body)  # the runner chooses the planner
                self.assertNotIn("modelKey", body)
                req = PlanRequest.model_validate({**body, "planner": "rules"})
                self.assertEqual([i.message for i in planner.validate_plan(planner.rules_plan(req), req)], [])

    def test_the_set_has_the_promised_shape(self):
        bodies = fixtures()
        kinds = {name: name.split("_", 1)[0] for name in bodies}
        new = {name for name, kind in kinds.items() if kind == "new"}
        completions = {name for name, kind in kinds.items() if kind in ("complete", "tight")}
        tight = {name for name, kind in kinds.items() if kind == "tight"}
        self.assertEqual((len(new), len(completions)), (10, 10))
        self.assertGreaterEqual(len(tight), 3)
        self.assertEqual({(bodies[name]["genre"], bodies[name]["targetBars"]) for name in new},
                         {(genre, bars) for genre in NEW_GENRES for bars in NEW_LENGTHS})
        for name in new:
            self.assertEqual((bodies[name]["measures"], bodies[name]["sections"]), ([], []), name)
        for name in completions:
            body = bodies[name]
            with self.subTest(request=name):
                self.assertTrue(8 <= len(body["measures"]) <= 16)
                self.assertTrue(body["sections"], "a completion has locked sections")
                for measure in body["measures"]:
                    self.assertIsNotNone(measure["chords"][0])
                    self.assertEqual([r is None for r in measure["roman"]], [c is None for c in measure["chords"]])
        for name in tight:
            body = bodies[name]
            room = body["targetBars"] - len(body["measures"])
            with self.subTest(request=name):
                self.assertTrue(room <= 4 or room % 8, "a tight request leaves little or an odd amount of room")

    def test_roman_numerals_are_the_editors(self):
        for name, body in fixtures().items():
            for measure in body["measures"]:
                for chord, roman in zip(measure["chords"], measure["roman"]):
                    if chord is not None:
                        with self.subTest(request=name, bar=measure["index"], chord=chord):
                            self.assertEqual(roman, editor_roman(chord, body["key"]))


class RunnerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="agent-eval-test-", dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.composer = FakeComposer()
        patcher = mock.patch.object(planner, "compose_section", self.composer)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = load_runner()

    def client(self, transport, cap=25.0):
        config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                           api_key=KEY, key_source="MODEL_API_KEY")
        self.ledger = Ledger(self.tmp / "meta_ledger.json", cap)
        client = LLMClient(config, self.ledger, transport)
        patcher = mock.patch.object(planner, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_the_effort_subset_names_fixture_files(self):
        names = set(fixtures())
        self.assertEqual(len(self.runner.EFFORT_SUBSET), 6)
        self.assertLessEqual(set(self.runner.EFFORT_SUBSET), names)
        self.assertGreaterEqual(sum(name.startswith("tight_") for name in self.runner.EFFORT_SUBSET), 3)
        self.assertEqual([name for name, _ in self.runner.load_requests(REQUESTS, self.runner.EFFORT_SUBSET)],
                         list(self.runner.EFFORT_SUBSET))
        self.assertEqual(len(self.runner.load_requests(REQUESTS)), 20)
        self.assertEqual([self.runner.results_name("rules", None), self.runner.results_name("meta", None),
                          self.runner.results_name("meta", "high")], ["rules.json", "meta-medium.json", "meta-high.json"])

    def test_the_rules_run_records_each_request_without_a_call(self):
        self.client(Replies(completion(POP_32_PLAN)))
        out = self.tmp / "rules.json"
        requests = self.runner.load_requests(REQUESTS, ("new_pop_32", "tight_folk_g_14bar_16_outro"))
        said = []
        document = self.runner.run_all(requests, "rules", None, 6.0, out, said.append)
        self.assertEqual((document["planner"], document["effort"], document["stopped"], document["spentUsd"]),
                         ("rules", None, None, 0.0))
        self.assertEqual([(r["request"], r["kind"], r["status"], r["firstPass"], r["revisions"], r["planValid"], r["calls"])
                          for r in document["runs"]],
                         [("new_pop_32", "new", "ok", {"ok": True, "errors": []}, 0, True, 0),
                          ("tight_folk_g_14bar_16_outro", "tight", "ok", {"ok": True, "errors": []}, 0, True, 0)])
        self.assertEqual(document["runs"][1]["plan"], [["outro", 2, "plagal"]])
        self.assertEqual((document["runs"][1]["sketchBars"], document["runs"][1]["targetBars"]), (14, 16))
        run = document["runs"][0]
        self.assertEqual([event for event, _ in run["events"][:2]], ["plan", "validate"])
        self.assertLessEqual(run["planMs"], run["totalMs"])
        self.assertEqual((run["judge"], run["regenerated"], run["requestIds"], run["costUsd"]), ([], 0, [], 0.0))
        self.assertEqual(run["trace"]["status"], "ok")
        self.assertEqual(len(self.composer.requests), 6)  # five pop sections, one outro
        text = out.read_text(encoding="utf-8")
        self.assertEqual(json.loads(text)["runs"][1]["request"], "tight_folk_g_14bar_16_outro")
        self.assertNotIn(str(REPO), text)
        self.assertNotIn(KEY, text)
        self.assertEqual(document["ledger"]["before"]["judge"], {"sharedWith": "default"})
        self.assertIn("2 runs, 0 failed", said[-2])

    def test_the_meta_run_stops_before_the_spend_limit_and_restores_the_effort(self):
        transport = Replies(completion(POP_32_PLAN), completion(ACCEPT), completion(POP_32_PLAN), completion(ACCEPT))
        self.client(transport)
        out = self.tmp / "meta-high.json"
        requests = self.runner.load_requests(REQUESTS, ("new_pop_32", "new_jazz_64"))
        # The first run fits under the limit (nothing spent + a run's cap); after it the second does not
        document = self.runner.run_all(requests, "meta", "high", planner.MAX_RUN_USD + 0.005, out, lambda _: None)
        self.assertEqual(len(document["runs"]), 1)
        self.assertIn("would pass --max-usd", document["stopped"])
        run = document["runs"][0]
        self.assertEqual((run["status"], run["firstPass"]["ok"], run["revisions"], run["judge"], run["requestIds"]),
                         ("ok", True, 0, ["accept"], ["req_1", "req_2"]))
        self.assertAlmostEqual(run["costUsd"], 2 * CALL_COST, places=8)
        self.assertAlmostEqual(run["planCostUsd"], CALL_COST, places=8)
        self.assertAlmostEqual(document["spentUsd"], 2 * CALL_COST, places=8)
        self.assertEqual([r["reasoning_effort"] for r in transport.calls], ["high", "low"])
        self.assertEqual((document["effort"], document["efforts"]["plan"], planner.PLAN_EFFORT), ("high", "high", "medium"))
        self.assertEqual(document["ledger"]["after"]["default"]["spentUsd"], self.ledger.snapshot()["spent_usd"])
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["stopped"], document["stopped"])

    def test_a_failure_every_later_run_would_repeat_stops_the_invocation(self):
        self.client(Replies(completion(POP_32_PLAN)), cap=0.001)  # the product ledger's cap refuses the first call
        requests = self.runner.load_requests(REQUESTS, ("new_pop_32", "new_jazz_64"))
        document = self.runner.run_all(requests, "meta", None, 6.0, self.tmp / "meta-medium.json", lambda _: None)
        self.assertEqual([(r["status"], r["error"]["kind"], r["firstPass"], r["planMs"]) for r in document["runs"]],
                         [("error", "budget", None, None)])
        self.assertIn("budget failure", document["stopped"])
        self.assertEqual(document["effort"], "medium")
        self.assertEqual(self.runner.metrics(document["runs"])["firstPass"], "0/1 (0%)")

    def test_a_provider_that_never_answers_stops_the_invocation(self):
        self.client(Replies(ConnectionError("refused")))  # settled at the reservation, no request id
        requests = self.runner.load_requests(REQUESTS, ("new_pop_32", "new_jazz_64", "new_blues_32"))
        document = self.runner.run_all(requests, "meta", "low", 6.0, self.tmp / "meta-low.json", lambda _: None)
        self.assertEqual([(r["status"], r["error"]["kind"], r["calls"], r["requestIds"]) for r in document["runs"]],
                         [("error", "llm", 1, [])] * 2)
        self.assertIn("2 runs in a row got no answer", document["stopped"])
        self.assertGreater(document["spentUsd"], 0)  # the two reservations, as the ledger settled them
        self.assertAlmostEqual(document["spentUsd"], self.ledger.snapshot()["spent_usd"], places=8)
        self.assertEqual(self.runner.metrics(document["runs"])["failures"], "llm 2")

    def test_a_key_in_the_results_is_never_written(self):
        with mock.patch.dict("os.environ", {"MODEL_API_KEY": "sk-eval-secret-value"}):
            with self.assertRaises(RuntimeError):
                self.runner.scrubbed('{"error": "sk-eval-secret-value"}')
            self.assertEqual(self.runner.scrubbed(f'{{"path": "{REPO}/x"}}'), '{"path": "<repo>/x"}')


if __name__ == "__main__":
    unittest.main()
