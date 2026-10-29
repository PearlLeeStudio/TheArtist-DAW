"""API tests for /api/plan/song (+ /stream): the happy path with a fake Meta transport and the
rules-path section composer, the Meta flag off (503), the failure status codes and the SSE order."""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import app.main
from app.services import llm, planner
from app.services.llm import Ledger, LLMClient, LLMConfig
from tests.test_planner import ACCEPT, SHORT_PLAN, SKETCH, VALID_PLAN, Replies, completion
from tests.test_section_api import sse_events

CLIENT = TestClient(app.main.app)
PLAN = "/api/plan/song"
PLAN_STREAM = "/api/plan/song/stream"
KEY = "sk-plan-api-test-never-shown"
TRACE_KEYS = {"status", "planner", "genre", "key", "bpm", "timeSignature", "plan", "validation", "sections", "judge",
              "calls", "spendUsd", "reservedUsd", "elapsedMs", "metaMs", "generationMs", "error"}
_QUIET = logging.NullHandler()


def setUpModule():
    for name in ("app.services.llm", "app.services.planner", "app.routes.plan"):
        logging.getLogger(name).addHandler(_QUIET)


def tearDownModule():
    for name in ("app.services.llm", "app.services.planner", "app.routes.plan"):
        logging.getLogger(name).removeHandler(_QUIET)


def body(**overrides) -> dict:
    req = {"genre": "pop", "key": "C major", "measures": SKETCH, "sections": [{"type": "verse", "start": 0, "length": 8}],
           "targetBars": 32, "wantOutro": True}
    req.update(overrides)
    return req


class PlanApiTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="plan-api-test-", dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        self.ledger_path = Path(tmp.name) / "meta_ledger.json"
        # The chord model is not needed: the rules composer runs the real song-form path
        patcher = mock.patch("app.routes.generate.TORCH_AVAILABLE", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_meta(self, *replies) -> Replies:
        transport = Replies(*replies)
        config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                           api_key=KEY, key_source="MODEL_API_KEY")
        client = LLMClient(config, Ledger(self.ledger_path, 25.0), transport)
        patcher = mock.patch.object(planner, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return transport

    def test_the_ai_path_receives_each_planned_cadence(self):
        from app.models.schemas import Suggestion
        from app.services.inference import AIResult

        def fake_ai(**kwargs):
            chords = {str(m): ["Cmaj7", "G7"] for m in kwargs["selected_measures"]}
            return AIResult(suggestions=[Suggestion(label="Option A — fake", chords=chords)], model_key="ft_f1")

        self.fake_meta(completion(VALID_PLAN), completion(ACCEPT))
        with mock.patch("app.routes.generate.TORCH_AVAILABLE", True), \
                mock.patch("app.routes.generate.generate_ai_result", side_effect=fake_ai) as ai:
            response = CLIENT.post(PLAN, json=body())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([call.kwargs["cadence"] for call in ai.call_args_list],
                         [section["cadence"] for section in VALID_PLAN["sections"]])
        self.assertTrue(all(section["source"] == "ai" for section in response.json()["sections"]))

    def test_happy_path_returns_the_whole_trace(self):
        self.fake_meta(completion(VALID_PLAN), completion(ACCEPT))
        res = CLIENT.post(PLAN, json=body())
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(set(data), TRACE_KEYS)
        self.assertEqual((data["status"], data["planner"], data["error"]), ("ok", "meta", None))
        self.assertEqual((data["key"], data["bpm"], data["timeSignature"]), ("C major", 110, [4, 4]))
        self.assertEqual(data["plan"], VALID_PLAN)
        self.assertEqual([v["ok"] for v in data["validation"]], [True])
        self.assertEqual([(c["step"], c["provider"], c["model"], c["requestId"]) for c in data["calls"]],
                         [("plan_song", "meta", "muse-spark-1.3", "req_1"), ("judge", "meta", "muse-spark-1.3", "req_2")])
        self.assertGreater(data["spendUsd"], 0)
        self.assertEqual([(s["sectionType"], s["startMeasure"], s["bars"], s["source"], s["modelUsed"], s["regenerated"])
                          for s in data["sections"]],
                         [("chorus", 8, 8, "rules", None, False), ("verse", 16, 8, "rules", None, False),
                          ("outro", 24, 8, "rules", None, False)])
        chorus, verse, outro = data["sections"]
        self.assertEqual(chorus["rulesSlots"], [14, 15])
        for s in data["sections"]:
            self.assertEqual(sorted(s["suggestions"][0]["chords"], key=int),
                             [str(m) for m in range(s["startMeasure"], s["startMeasure"] + s["bars"])])
        self.assertEqual(chorus["suggestions"][0]["chords"]["15"], ["G7", "Cmaj"])     # authentic
        self.assertEqual(verse["suggestions"][0]["chords"]["23"][-1], "G7")             # half: the planner's cadence
        self.assertEqual(outro["suggestions"][0]["chords"]["31"], ["Fmaj7", "Cmaj"])    # plagal
        self.assertEqual([j["decision"] for j in data["judge"]], ["accept"])
        self.assertEqual(len(data["judge"][0]["report"]), 3)
        self.assertNotIn(KEY, res.text)

    def test_a_new_song_takes_the_genre_defaults_and_the_rules_planner_needs_no_meta(self):
        res = CLIENT.post(PLAN, json={"genre": "jazz", "targetBars": 32, "planner": "rules"})
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual((data["status"], data["planner"], data["calls"], data["judge"], data["spendUsd"]),
                         ("ok", "rules", [], [], 0.0))
        self.assertEqual((data["key"], data["bpm"]), ("F major", 110))
        self.assertEqual([(s["sectionType"], s["startMeasure"]) for s in data["sections"]],
                         [("a_section", 0), ("a_section", 8), ("b_section", 16), ("a_section", 24)])
        self.assertEqual(data["sections"][-1]["suggestions"][0]["chords"]["31"], ["C7", "Fmaj"])

    def test_meta_flag_off_is_503_with_a_trace_and_rules_still_answer(self):
        env = {"THEARTIST_META_ENABLED": "0", "MODEL_API_KEY": KEY}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "_clients", {}):
            res = CLIENT.post(PLAN, json=body())
            self.assertEqual(res.status_code, 503, res.text)
            data = res.json()
            self.assertEqual((data["status"], data["error"]["kind"], data["calls"], data["sections"]),
                             ("error", "disabled", [], []))
            self.assertIn("disabled", data["error"]["message"])
            self.assertEqual(llm._clients, {})
            self.assertEqual(CLIENT.post(PLAN, json=body(planner="rules")).status_code, 200)
            events = sse_events(CLIENT.post(PLAN_STREAM, json=body()).text)
            self.assertEqual([name for name, _ in events], ["error"])
            self.assertEqual(events[0][1]["error"]["kind"], "disabled")

    def test_failures_keep_the_trace_under_their_status(self):
        transport = self.fake_meta(TimeoutError("read timed out"))
        res = CLIENT.post(PLAN, json=body())
        self.assertEqual(res.status_code, 504, res.text)
        data = res.json()
        self.assertEqual((data["status"], data["error"]["kind"]), ("error", "timeout"))
        self.assertEqual([(c["step"], c["ok"]) for c in data["calls"]], [("plan_song", False)])
        self.assertGreater(data["spendUsd"], 0)

        transport.results = [completion(SHORT_PLAN)]
        transport.calls = []
        res = CLIENT.post(PLAN, json=body())
        self.assertEqual(res.status_code, 502, res.text)
        data = res.json()
        self.assertEqual((data["error"]["kind"], len(data["calls"]), [v["ok"] for v in data["validation"]]),
                         ("invalid", 3, [False, False, False]))
        self.assertEqual(data["error"]["requestId"], "req_3")

        with mock.patch.object(planner, "MAX_RUN_USD", 0.001):
            res = CLIENT.post(PLAN, json=body())
        self.assertEqual(res.status_code, 429, res.text)
        self.assertEqual(res.json()["error"]["kind"], "budget")

    def test_stream_events_arrive_in_run_order(self):
        self.fake_meta(completion(SHORT_PLAN), completion(VALID_PLAN), completion(ACCEPT))
        res = CLIENT.post(PLAN_STREAM, json=body())
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/event-stream"))
        events = sse_events(res.text)
        self.assertEqual([name for name, _ in events],
                         ["plan", "validate", "revise", "validate", "generate_section", "generate_section",
                          "generate_section", "judge", "complete"])
        for name, payload in events[:-1]:
            self.assertIn("t_ms", payload)
        self.assertEqual(events[1][1]["ok"], False)
        self.assertEqual([i["code"] for i in events[1][1]["errors"]], ["total_bars", "final_cadence"])
        self.assertEqual(events[2][1]["attempt"], 2)
        self.assertEqual([e[1]["index"] for e in events[4:7]], [0, 1, 2])
        self.assertEqual(events[7][1]["decision"], "accept")
        trace = events[-1][1]
        self.assertEqual(set(trace), TRACE_KEYS)
        self.assertEqual((trace["status"], len(trace["calls"]), len(trace["sections"])), ("ok", 3, 3))

    def test_stream_failure_ends_with_one_error_frame(self):
        self.fake_meta(completion(VALID_PLAN), TimeoutError("read timed out"))
        events = sse_events(CLIENT.post(PLAN_STREAM, json=body()).text)
        self.assertEqual([name for name, _ in events],
                         ["plan", "validate", "generate_section", "generate_section", "generate_section", "error"])
        trace = events[-1][1]
        self.assertEqual((trace["status"], trace["error"]["kind"], len(trace["calls"])), ("error", "timeout", 2))
        self.assertEqual(trace["calls"][1]["ok"], False)

    def test_bad_bodies_are_422_on_both_routes(self):
        for route in (PLAN, PLAN_STREAM):
            for bad in ({"targetBars": 20}, {"contrast": "wild"}, {"genre": "polka"}, {"key": "H major"},
                        {"measures": SKETCH * 4}, {"sections": [{"type": "verse", "start": 4, "length": 8}]},
                        {"measures": [{"index": 0, "chords": ["C", "F", "G"], "roman": ["I", "IV", "V"]}]},
                        {"prompt": "make it sad"}):
                with self.subTest(route=route, bad=bad):
                    self.assertEqual(CLIENT.post(route, json=body(**bad)).status_code, 422)


if __name__ == "__main__":
    unittest.main()
