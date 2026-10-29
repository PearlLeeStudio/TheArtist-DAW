"""The song planner: validate_plan rule by rule, the plan -> revise -> generate -> judge run with a
fake transport and a fake section composer, the forced failures, the rules planner for every genre,
and the rule slots. No network, no model."""

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.models.plan import PlanRequest, PlanSectionResult, SongPlan, TARGET_BARS
from app.models.schemas import CADENCE_TYPES, SectionGenerateRequest, SectionGenerateResponse, Suggestion
from app.models.sections import SECTION_TYPES, section_title
from app.services import planner
from app.services.genre_tables import GENRE_DEFAULTS
from app.services.llm import Ledger, LLMClient, LLMConfig
from app.services.song_form import apply_song_form, apply_song_form_with_slots, rule_slots

KEY = "sk-planner-test-never-log-this"
_QUIET = logging.NullHandler()


def setUpModule():
    # Failure paths log on purpose; keep them out of the runner output
    for name in ("app.services.llm", "app.services.planner"):
        logging.getLogger(name).addHandler(_QUIET)


def tearDownModule():
    for name in ("app.services.llm", "app.services.planner"):
        logging.getLogger(name).removeHandler(_QUIET)


def measure(index, chords, roman):
    return {"index": index, "chords": chords, "roman": roman}


# An 8-bar pop sketch in C major with the Roman numerals the editor would compute
SKETCH = [
    measure(0, ["Cmaj7", "Am7"], ["Imaj7", "vi7"]), measure(1, ["Dm7", "G7"], ["ii7", "V7"]),
    measure(2, ["Cmaj7", "Am7"], ["Imaj7", "vi7"]), measure(3, ["Dm7", "G7"], ["ii7", "V7"]),
    measure(4, ["Fmaj7", "G7"], ["IVmaj7", "V7"]), measure(5, ["Em7", "Am7"], ["iii7", "vi7"]),
    measure(6, ["Fmaj7", "G7"], ["IVmaj7", "V7"]), measure(7, ["Cmaj", None], ["I", None]),
]
VALID_PLAN = {"sections": [
    {"type": "chorus", "bars": 8, "cadence": "authentic", "reason": "Lift after the ii-V in bars 1 and 3",
     "cites": [{"bar": 1, "roman": "V7"}, {"bar": 3, "roman": "ii7"}]},
    {"type": "verse", "bars": 8, "cadence": "half", "reason": "Second verse, left open", "cites": []},
    {"type": "outro", "bars": 8, "cadence": "plagal", "reason": "IV-I close like bar 6", "cites": [{"bar": 6, "roman": "IVmaj7"}]},
]}
SHORT_PLAN = {"sections": [  # 20 bars instead of 24, and the last cadence is open
    {"type": "chorus", "bars": 8, "cadence": "authentic", "reason": "Lift", "cites": []},
    {"type": "outro", "bars": 12, "cadence": "half", "reason": "Fade", "cites": []},
]}
ACCEPT = {"decision": "accept", "targets": []}
USAGE = {"prompt_tokens": 800, "completion_tokens": 400}
CALL_COST = (800 * 1.25 + 400 * 4.25) / 1_000_000  # 0.0027 USD
# 16 distinct chords, none of them a chord the rules write in C major or A minor and none on
# a forced root (I or IV) at the slots the rules compare, so every rule-decided slot changes
PHRASE = "Em7 Gm7 Bbmaj7 Ebmaj7 Ab7 Dbmaj7 Gb7 Bm7 F#m7 Bmaj7 Dm9 Abm7 Gm9 Eb9 Fm7 Bb7".split()


def request(**overrides) -> PlanRequest:
    fields = {"genre": "pop", "key": "C major", "measures": SKETCH, "sections": [{"type": "verse", "start": 0, "length": 8}],
              "targetBars": 32, "wantOutro": True}
    fields.update(overrides)
    return PlanRequest(**fields)


def completion(data):
    return {"id": "chatcmpl-plan", "object": "chat.completion", "created": 0, "model": "muse-spark-1.3",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(data)}}],
            "usage": USAGE}


class Replies:
    """A transport that answers each result in turn (the last one for every later call) and records the requests."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, request):
        result = self.results[min(len(self.calls), len(self.results) - 1)]
        self.calls.append(request)
        if isinstance(result, BaseException):
            raise result
        return result, {"x-request-id": f"req_{len(self.calls)}"}


class FakeComposer:
    """Stands in for compose_section: one diatonic suggestion per call, every request kept."""

    def __init__(self):
        self.requests: list[SectionGenerateRequest] = []

    def __call__(self, req: SectionGenerateRequest) -> SectionGenerateResponse:
        self.requests.append(req)
        start, bars = len(req.context), req.chordCount // 2
        chords = {str(m): ["Cmaj7", "Am7"] if m % 2 == 0 else ["Dm7", "G7"] for m in range(start, start + bars)}
        return SectionGenerateResponse(sectionType=req.sectionType, title=section_title(req.sectionType, bars),
                                       startMeasure=start, bars=bars, chordCount=bars * 2,
                                       suggestions=[Suggestion(label="Option A — fake", chords=chords)],
                                       source="ai", modelUsed="ft_f1")


class ValidatePlanTest(unittest.TestCase):
    def plan(self, **changes) -> SongPlan:
        data = json.loads(json.dumps(VALID_PLAN))
        for key, value in changes.items():
            index, field = key.split("_", 1)
            data["sections"][int(index)][field] = value
        return SongPlan.model_validate(data)

    def codes(self, plan, req=None):
        return [(issue.code, issue.section) for issue in planner.validate_plan(plan, req or request())]

    def test_valid_plan_has_no_issues(self):
        self.assertEqual(planner.validate_plan(self.plan(), request()), [])

    def test_each_rule_reports_its_code(self):
        cases = {
            "section_type": (self.plan(**{"1_type": "coda"}), ("section_type", 1)),
            "bars_low": (self.plan(**{"0_bars": 1, "1_bars": 15}), ("bars", 0)),
            "bars_high": (self.plan(**{"0_bars": 33, "1_bars": 2, "2_bars": 2}), ("bars", 0)),  # 37 + 8 != 32 too
            "cadence": (self.plan(**{"1_cadence": "deceptive"}), ("cadence", 1)),
            "reason_length": (self.plan(**{"0_reason": "x" * 121}), ("reason_length", 0)),
            "intro_first": (self.plan(**{"0_type": "intro"}), ("intro_first", 0)),
            "outro_last": (self.plan(**{"0_type": "outro"}), ("outro_last", 0)),
            "final_cadence": (self.plan(**{"2_cadence": "half"}), ("final_cadence", 2)),
            "outro_wanted": (self.plan(**{"2_type": "chorus"}), ("outro_wanted", 2)),
            "cite_bar": (self.plan(**{"1_cites": [{"bar": 8, "roman": "I"}]}), ("cite_bar", 1)),
            "cite_roman": (self.plan(**{"1_cites": [{"bar": 1, "roman": "IV"}]}), ("cite_roman", 1)),
            "total_bars": (SongPlan.model_validate(SHORT_PLAN), ("total_bars", None)),
        }
        for name, (plan, expected) in cases.items():
            with self.subTest(rule=name):
                self.assertIn(expected, self.codes(plan))
        self.assertEqual(self.codes(SongPlan(sections=[])), [("empty", None)])

    def test_rules_follow_the_request(self):
        plan = self.plan(**{"2_type": "chorus", "2_cadence": "authentic"})
        self.assertEqual(self.codes(plan, request(wantOutro=False)), [])
        self.assertEqual(self.codes(self.plan(), request(wantOutro=False)), [("outro_unwanted", 2)])
        # An empty song may open with an intro, but then nothing can be cited
        new_song = request(measures=[], sections=[], targetBars=16)
        opening = SongPlan.model_validate({"sections": [
            {"type": "intro", "bars": 4, "cadence": "none", "reason": "Open", "cites": [{"bar": 0, "roman": "I"}]},
            {"type": "chorus", "bars": 8, "cadence": "authentic", "reason": "Hook", "cites": []},
            {"type": "outro", "bars": 4, "cadence": "plagal", "reason": "Close", "cites": []}]})
        self.assertEqual(self.codes(opening, new_song), [("cite_bar", 0)])
        self.assertEqual(self.codes(self.plan(), request(targetBars=48)), [("total_bars", None)])

    def test_request_shape_is_checked_before_the_validator(self):
        for bad in ({"targetBars": 20}, {"contrast": "wild"}, {"planner": "gpt"}, {"genre": "polka"},
                    {"key": "H major"}, {"measures": SKETCH[:3]}, {"measures": SKETCH[::-1]},
                    {"measures": SKETCH * 4}, {"sections": [{"type": "verse", "start": 4, "length": 8}]},
                    {"sections": [{"type": "verse", "start": 0, "length": 4}, {"type": None, "start": 2, "length": 4}]},
                    {"measures": [measure(0, ["C", "F", "G"], ["I", "IV", "V"])]}, {"prompt": "make it sad"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                request(**bad)
        new_song = PlanRequest(genre="jazz", targetBars=32)
        self.assertEqual((new_song.key, new_song.bpm, new_song.timeSignature), ("F major", 110, (4, 4)))
        self.assertEqual(PlanRequest(genre="pop", key="a Minor", targetBars=16).key, "A minor")


class RulesPlannerTest(unittest.TestCase):
    def test_every_genre_validates_at_every_length(self):
        for genre in [*GENRE_DEFAULTS]:
            for target in TARGET_BARS:
                for outro in (False, True):
                    for sketch_bars in (0, 8, 13, target - 2):
                        sketch = [measure(i, ["Cmaj7", "Am7"], ["Imaj7", "vi7"]) for i in range(sketch_bars)]
                        req = PlanRequest(genre=genre, measures=sketch, targetBars=target, wantOutro=outro, planner="rules")
                        plan = planner.rules_plan(req)
                        with self.subTest(genre=genre, target=target, outro=outro, sketch=sketch_bars):
                            self.assertEqual([i.message for i in planner.validate_plan(plan, req)], [])
                            self.assertEqual(sketch_bars + sum(s.bars for s in plan.sections), target)

    def test_forms_follow_the_genre_and_keep_the_sketch_first(self):
        new_pop = planner.rules_plan(PlanRequest(genre="pop", targetBars=32, planner="rules"))
        self.assertEqual([(s.type, s.bars) for s in new_pop.sections],
                         [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 4)])
        self.assertEqual([s.cadence for s in new_pop.sections], ["none", "authentic", "authentic", "authentic", "authentic"])
        continued = planner.rules_plan(request(planner="rules"))
        self.assertEqual([(s.type, s.bars) for s in continued.sections],
                         [("verse", 8), ("chorus", 8), ("verse", 4), ("outro", 4)])
        self.assertEqual([s.cadence for s in continued.sections], ["authentic", "authentic", "authentic", "plagal"])
        jazz = planner.rules_plan(PlanRequest(genre="jazz", targetBars=64, planner="rules"))
        self.assertEqual([s.type for s in jazz.sections], ["a_section", "a_section", "b_section", "a_section"] * 2)
        blues = planner.rules_plan(PlanRequest(genre="blues", targetBars=48, wantOutro=True, planner="rules"))
        self.assertEqual([(s.type, s.bars) for s in blues.sections],
                         [("intro", 4), ("verse", 12), ("verse", 12), ("verse", 12), ("verse", 4), ("outro", 4)])
        self.assertTrue(all(s.cites == [] and "rules" in s.reason for s in blues.sections))


class RuleSlotsTest(unittest.TestCase):
    def test_slots_match_what_apply_song_form_rewrote(self):
        for section in SECTION_TYPES:
            for cadence in (None, *CADENCE_TYPES):
                for key, minor in (("C", False), ("A", True)):
                    for n in (1, 2, 3, 4, 5, 16):
                        with self.subTest(section=section, cadence=cadence, key=key, n=n):
                            chords, slots = apply_song_form_with_slots(PHRASE[:n], section, key, minor, cadence)
                            changed = [i for i in range(n) if chords[i] != PHRASE[i]]
                            self.assertEqual(changed, slots)
                            self.assertEqual(slots, rule_slots(section, n, cadence))
                            self.assertEqual(chords, apply_song_form(PHRASE[:n], section, key, minor, cadence))

    def test_a_chosen_cadence_replaces_the_section_ending(self):
        self.assertEqual(apply_song_form(PHRASE[:4], "verse", "C")[-2:], ["G7", "Cmaj"])
        self.assertEqual(apply_song_form(PHRASE[:4], "verse", "C", cadence="half")[-1:], ["G7"])
        self.assertEqual(apply_song_form(PHRASE[:4], "verse", "C", cadence="plagal")[-2:], ["Fmaj7", "Cmaj"])
        self.assertEqual(apply_song_form(PHRASE[:4], "verse", "C", cadence="none"), PHRASE[:4])
        self.assertEqual(apply_song_form(PHRASE[:4], "outro", "C", cadence="turnaround"), ["Cmaj7", "Am7", "Dm7", "G7"])
        self.assertEqual(apply_song_form(PHRASE[:4], "intro", "C", cadence="authentic"), ["Cmaj7", "Gm7", "G7", "Cmaj"])
        self.assertEqual(rule_slots("post_chorus", 8, "half"), [4, 5, 6, 7])
        self.assertEqual(rule_slots("tag", 8), [6, 7])
        self.assertEqual(rule_slots("tag", 8, "none"), [])
        self.assertEqual(rule_slots("solo", 8, "authentic"), [6, 7])


class SketchFactsTest(unittest.TestCase):
    def test_cadences_and_repeats_come_from_the_roman_numerals(self):
        facts = planner.sketch_facts(request().measures)
        self.assertEqual(facts["cadences"], [{"bar": 2, "type": "authentic"}, {"bar": 3, "type": "half"},
                                             {"bar": 4, "type": "half"}, {"bar": 7, "type": "authentic"}])
        self.assertEqual(facts["repeats"], [{"bars": [2, 3], "sameAs": [0, 1]}])
        self.assertEqual(planner.sketch_facts([]), {"cadences": [], "repeats": []})


class SectionReportTest(unittest.TestCase):
    def test_facts_cover_the_model_slots_only(self):
        chords = {"8": ["Cmaj7", "Ebmaj7"], "9": ["F#7", "G7/B"], "10": ["Cmaj7", "Ebmaj7"], "11": ["G7", "Cmaj"]}
        section = PlanSectionResult(sectionType="chorus", title="Chorus — 4 bars", startMeasure=8, bars=4, chordCount=8,
                                    suggestions=[Suggestion(label="A", chords=chords)], source="ai", modelUsed="ft_f1",
                                    cadence="authentic", rulesSlots=[6, 7], reason="", cites=[])
        before = ["Cmaj7", "Am7", "F#7", "D7", "Cmaj7", "Dm7", "Dm7", "G7"]
        report = planner.section_report(0, section, before, "C major")
        self.assertEqual((report.modelSlots, report.distinctChords, report.emptySlots), (6, 4, 0))
        self.assertEqual(report.outsideKey, round(3 / 6, 3))     # Ebmaj7 twice and F#7
        self.assertEqual(report.repeatRate, round(3 / 6, 3))     # Cmaj7, F#7, Cmaj7 at the same slots
        self.assertIsNone(planner.section_report(0, section, [], "A minor").repeatRate)


class PlannerRunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="planner-test-", dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        self.ledger = Ledger(Path(tmp.name) / "meta_ledger.json", 25.0)
        self.composer = FakeComposer()
        patcher = mock.patch.object(planner, "compose_section", self.composer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def client(self, transport, cap=25.0):
        config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                           api_key=KEY, key_source="MODEL_API_KEY")
        self.ledger = Ledger(self.ledger.path, cap)
        client = LLMClient(config, self.ledger, transport)
        patcher = mock.patch.object(planner, "get_client", return_value=client)
        self.get_client = patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_invalid_plan_is_revised_then_generated_and_judged(self):
        transport = Replies(completion(SHORT_PLAN), completion(VALID_PLAN), completion(ACCEPT))
        self.client(transport)
        events = []
        trace = planner.complete_form(request(), lambda name, payload: events.append(name))
        self.assertEqual((trace.status, trace.error), ("ok", None))
        self.assertEqual([(v.attempt, v.ok, [i.code for i in v.errors]) for v in trace.validation],
                         [(1, False, ["total_bars", "final_cadence"]), (2, True, [])])
        self.assertEqual([(c.step, c.attempt, c.effort, c.requestId, c.ok) for c in trace.calls],
                         [("plan_song", 1, "medium", "req_1", True), ("plan_song", 2, "low", "req_2", True),
                          ("judge", 1, "low", "req_3", True)])
        self.assertEqual([r["reasoning_effort"] for r in transport.calls], ["medium", "low", "low"])
        self.assertEqual([r["timeout"] for r in transport.calls], [45.0] * 3)
        self.assertEqual(transport.calls[0]["response_format"]["json_schema"]["name"], "song_plan")
        # The revision carries the rejected plan and the validator's issues as a user message
        revision = transport.calls[1]["messages"]
        self.assertEqual([m["role"] for m in revision], ["system", "user", "assistant", "user"])
        self.assertIn('"code":"total_bars"', revision[-1]["content"])
        self.assertIn('"cadences":[{"bar":2,"type":"authentic"}', transport.calls[0]["messages"][1]["content"])
        self.assertEqual(trace.plan.model_dump(), VALID_PLAN)
        self.assertEqual([(s.sectionType, s.bars, s.startMeasure, s.cadence) for s in trace.sections],
                         [("chorus", 8, 8, "authentic"), ("verse", 8, 16, "half"), ("outro", 8, 24, "plagal")])
        self.assertEqual([s.rulesSlots for s in trace.sections], [[14, 15], [15], [14, 15]])
        self.assertEqual([len(r.context) for r in self.composer.requests], [8, 16, 24])
        self.assertEqual([(r.cadence, r.chordCount, r.genre, r.key) for r in self.composer.requests],
                         [("authentic", 16, "pop", "C major"), ("half", 16, "pop", "C major"), ("plagal", 16, "pop", "C major")])
        self.assertEqual(self.composer.requests[1].context[8].chords, ["Cmaj7", "Am7"])  # section A applied
        self.assertEqual([j.decision for j in trace.judge], ["accept"])
        self.assertEqual(len(trace.judge[0].report), 3)
        self.assertAlmostEqual(trace.spendUsd, 3 * CALL_COST, places=8)
        self.assertAlmostEqual(trace.spendUsd, self.ledger.snapshot()["spent_usd"], places=8)
        self.assertLessEqual(trace.reservedUsd, planner.MAX_RUN_USD)
        self.assertEqual(events, ["plan", "validate", "revise", "validate", "generate_section", "generate_section",
                                  "generate_section", "judge"])
        self.assertEqual(self.get_client.call_args_list, [mock.call("default"), mock.call("judge")])

    def test_revisions_exhausted_is_an_error_with_the_spend(self):
        self.client(Replies(completion(SHORT_PLAN)))
        trace = planner.complete_form(request())
        self.assertEqual((trace.status, trace.error.kind, trace.error.requestId), ("error", "invalid", "req_3"))
        self.assertEqual([c.step for c in trace.calls], ["plan_song"] * 3)
        self.assertEqual([v.ok for v in trace.validation], [False, False, False])
        self.assertEqual((trace.sections, trace.judge), ([], []))
        self.assertAlmostEqual(trace.spendUsd, 3 * CALL_COST, places=8)
        self.assertEqual(self.composer.requests, [])

    def test_judge_regenerates_each_target_once_and_judges_twice_at_most(self):
        first = {"decision": "regenerate", "targets": [{"section": 1, "reason": "repeats the chorus"},
                                                        {"section": 1, "reason": "twice"}]}
        second = {"decision": "regenerate", "targets": [{"section": 9, "reason": "no such"}, {"section": 1, "reason": "again"}]}
        self.client(Replies(completion(VALID_PLAN), completion(first), completion(second)))
        trace = planner.complete_form(request())
        self.assertEqual(trace.status, "ok")
        self.assertEqual([(j.decision, [t.section for t in j.targets]) for j in trace.judge],
                         [("regenerate", [1]), ("regenerate", [1])])
        self.assertEqual([s.regenerated for s in trace.sections], [False, True, False])
        self.assertEqual(len(self.composer.requests), 4)
        self.assertEqual((self.composer.requests[3].sectionType, len(self.composer.requests[3].context)), ("verse", 16))
        self.assertEqual([c.step for c in trace.calls], ["plan_song", "judge", "judge"])
        self.assertEqual((trace.judge[0].requestId, trace.judge[1].requestId), ("req_2", "req_3"))
        self.assertEqual(trace.judge[0].targets[0].reason, "repeats the chorus")

    def test_a_regenerate_without_valid_targets_counts_as_accept(self):
        self.client(Replies(completion(VALID_PLAN), completion({"decision": "regenerate", "targets": [{"section": 7, "reason": "x"}]})))
        trace = planner.complete_form(request())
        self.assertEqual([(j.decision, j.targets) for j in trace.judge], [("accept", [])])
        self.assertEqual(len(trace.calls), 2)

    def test_budget_limits_stop_the_run_before_any_call(self):
        transport = Replies(completion(VALID_PLAN))
        self.client(transport)
        with mock.patch.object(planner, "MAX_RUN_USD", 0.001):
            trace = planner.complete_form(request())
        self.assertEqual((trace.status, trace.error.kind), ("error", "budget"))
        self.assertIn("run's reservations", trace.error.message)
        self.assertEqual((trace.calls, trace.spendUsd, transport.calls), ([], 0.0, []))
        with mock.patch.object(planner, "MAX_REQUEST_USD", 0.0001):
            trace = planner.complete_form(request())
        self.assertEqual((trace.status, trace.error.kind, trace.calls), ("error", "budget", []))
        self.client(transport, cap=0.001)  # the ledger's own cap
        trace = planner.complete_form(request())
        self.assertEqual((trace.status, trace.error.kind, trace.calls, transport.calls), ("error", "budget", [], []))
        self.assertIn("cap $0.00", trace.error.message)
        self.assertNotIn(str(self.ledger.path), trace.error.message)

    def test_a_timeout_leaves_a_failed_trace_with_the_settled_spend(self):
        self.client(Replies(TimeoutError("read timed out")))
        trace = planner.complete_form(request())
        self.assertEqual((trace.status, trace.error.kind), ("error", "timeout"))
        self.assertEqual([(c.step, c.ok, c.requestId) for c in trace.calls], [("plan_song", False, None)])
        self.assertGreater(trace.spendUsd, 0)  # the reservation, as the ledger settled it
        self.assertAlmostEqual(trace.spendUsd, self.ledger.snapshot()["spent_usd"], places=8)
        self.assertEqual((trace.plan, trace.sections), (None, []))

    def test_the_chord_model_time_budget_stops_generation(self):
        self.client(Replies(completion(VALID_PLAN), completion(ACCEPT)))
        with mock.patch.object(planner, "OWN_MODEL_BUDGET_S", 0):
            trace = planner.complete_form(request())
        self.assertEqual((trace.status, trace.error.kind), ("error", "timeout"))
        self.assertIn("chord-model time", trace.error.message)
        self.assertEqual(([c.step for c in trace.calls], trace.sections), (["plan_song"], []))
        self.assertAlmostEqual(trace.spendUsd, CALL_COST, places=8)
        self.assertIsNotNone(trace.plan)

    def test_the_rules_planner_makes_no_llm_call(self):
        self.client(Replies(completion(VALID_PLAN)))
        trace = planner.complete_form(request(planner="rules"))
        self.assertEqual((trace.status, trace.planner, trace.calls, trace.judge, trace.spendUsd), ("ok", "rules", [], [], 0.0))
        self.assertEqual([(s.sectionType, s.bars) for s in trace.sections], [("verse", 8), ("chorus", 8), ("verse", 4), ("outro", 4)])
        self.assertEqual([v.ok for v in trace.validation], [True])
        self.get_client.assert_not_called()

    def test_plan_song_plans_without_generating(self):
        self.client(Replies(completion(VALID_PLAN)))
        trace = planner.plan_song(request())
        self.assertEqual((trace.status, len(trace.calls), trace.sections, trace.judge), ("ok", 1, [], []))
        self.assertEqual(trace.plan.model_dump(), VALID_PLAN)
        self.assertEqual(self.composer.requests, [])
        self.assertEqual(self.get_client.call_args_list, [mock.call("default")])


if __name__ == "__main__":
    unittest.main()
