"""Second-ear evaluation: the inputs built from the committed planner results as the editor builds
a review, the three cyclic orders, the judges' clients, the spend and stop rules, the numbers and
the report. Fake transports, no network."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services.llm import LLMConfigError
from scripts import review_eval as ev
from tests.test_planner import USAGE, Replies

KEY = "sk-review-eval-test-never-shown"
OPEN_MODEL = "meta-models/muse-spark-open-1026"


def completion(content, model="muse-spark-1.3"):
    return {"id": "chatcmpl-review", "object": "chat.completion", "created": 0, "model": model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": USAGE}


def pick(choice, *reasons, model="muse-spark-1.3"):
    return completion(json.dumps({"choice": choice, "reasons": [{"factName": name, "value": value, "claim": "Fits."}
                                                               for name, value in reasons]}), model)


class ContentJudge:
    """A judge that picks by the chords: the candidate with the lowest roughness in the sent facts."""

    def __init__(self):
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        payload = json.loads(request["messages"][1]["content"])
        best = min(payload["candidates"], key=lambda c: c["facts"]["r1Roughness"])
        reply = pick(best["label"], ("r1Roughness", best["facts"]["r1Roughness"]))
        return reply, {"x-request-id": f"req_{len(self.calls)}"}


def quiet(*_args, **_kwargs):
    pass


class ReviewEvalCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = ev.load_sections()
        cls.by_name = {entry["request"]: entry for entry in cls.entries}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="review-eval-test-", dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def meta(self, *replies, cap=None, transport=None):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.tmp / "meta.json")}
        if cap is not None:
            env["THEARTIST_META_BUDGET_USD"] = str(cap)
        transport = transport if transport is not None else Replies(*replies)
        client, counting = ev.judge_client("meta", env=env, transport=transport)
        return client, counting, transport

    def openweight(self, *replies, cap=None):
        env = {"BASETEN_API_KEY": KEY, "THEARTIST_JUDGE_LEDGER": str(self.tmp / "judge.json"),
               "THEARTIST_META_LEDGER": str(self.tmp / "meta.json")}
        if cap is not None:
            env["THEARTIST_JUDGE_BUDGET_USD"] = str(cap)
        transport = Replies(*replies)
        client, counting = ev.judge_client("openweight", env=env, transport=transport)
        return client, counting, transport

    def run_eval(self, client, counting, entries, max_usd=1.5, judge="meta", out=None):
        out = out or self.tmp / "out" / f"results-{judge}.json"
        document = ev.run_all(judge, entries, client, counting, max_usd, out, ev.source_facts(), say=quiet)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["reviews"], document["reviews"])
        return document


class InputsTest(ReviewEvalCase):
    def test_editor_symbols_follow_the_chord_parser(self):
        cases = {"Amaj": "A", "Amin": "Am", "Amaj/Db": "A/Db", "A7b9": "A7b9", "Bbm6/F": "Bbm6/F",
                 "C#maj/Ab": "C#/Ab", "C7(b9)/E": "C7(b9)/E", "Cmaj7": "Cmaj7", "CM7": "Cmaj7", " G7 ": "G7",
                 "Hmaj": None, "": None, None: None}
        for symbol, expected in cases.items():
            self.assertEqual(ev.editor_symbol(symbol), expected, symbol)

    def test_twenty_lists_from_the_committed_planner_run(self):
        self.assertEqual(len(self.entries), 20)
        for entry in self.entries:
            body = entry["body"]
            self.assertEqual([c["label"] for c in body["candidates"]], ["A", "B", "C"], entry["request"])
            self.assertEqual(len(body["original"]), entry["bars"])
            self.assertTrue(all(slot is None for bar in body["original"] for slot in bar))
            # Every sketch has locked sections; a new song's first section has none before it
            self.assertEqual(body["previousSection"] is None, entry["kind"] == "new", entry["request"])
            self.assertEqual(len(entry["facts"]), 3)
            self.assertTrue(entry["r1Pick"] and entry["rawR1Pick"])
        facts = ev.input_facts(self.entries)
        self.assertEqual((facts["kinds"], facts["withPrevious"]), ({"complete": 6, "new": 10, "tight": 4}, 10))
        # A review request carries no cadence: where the planner's differs from the section default,
        # the planner's rules wrote slots the review's table does not mark
        self.assertEqual(set(facts["rulesMismatch"]), {"new_blues_32", "new_blues_64", "new_gospel_32",
                                                       "tight_pop_c_10bar_32_high"})

    def test_the_previous_section_is_the_sketch_section_before_from_the_same_offset(self):
        country = self.by_name["complete_country_g_16bar_32"]  # verse 0-7, chorus 8-15, then a 4-bar bridge
        sketch = json.loads((ev.REQUESTS_DIR / "complete_country_g_16bar_32.json").read_text(encoding="utf-8"))
        self.assertEqual(country["body"]["previousSection"],
                         [[ev.editor_symbol(c) for c in m["chords"]] for m in sketch["measures"][8:12]])
        pop = self.by_name["tight_pop_c_10bar_32_high"]  # a 2-bar turnaround before a 4-bar pre-chorus
        self.assertEqual(len(pop["body"]["previousSection"]), 2)

    def test_candidates_are_the_stored_suggestions_as_the_editor_writes_them(self):
        country = self.by_name["complete_country_g_16bar_32"]
        # The stored A: Cmaj7 Gmaj/B | Am Am | Gmaj Gmaj | Cmaj7/G D7/F#
        self.assertEqual(country["body"]["candidates"][0]["chords"],
                         [["Cmaj7", "G/B"], ["Am", "Am"], ["G", "G"], ["Cmaj7/G", "D7/F#"]])
        self.assertEqual([c["creativity"] for c in country["candidates"]], ["conservative", "creative", "balanced"])

    def test_the_cyclic_orders_show_every_candidate_once_under_every_letter_and_keep_the_facts(self):
        entry = self.entries[0]
        seen = {letter: set() for letter in "ABC"}
        for order in ev.ORDERS:
            request, letters = ev.ordered(entry, order)
            self.assertEqual("".join(letters.values()), order)
            for shown, stored in letters.items():
                seen[stored].add(shown)
                sent = next(c for c in request.candidates if c.label == shown)
                self.assertEqual(sent.chords, next(c["chords"] for c in entry["body"]["candidates"] if c["label"] == stored))
            rows = sorted(({**row.model_dump(), "label": letters[row.label]}
                           for row in ev.review.candidate_facts(request)), key=lambda row: row["label"])
            self.assertEqual(rows, entry["facts"])
        self.assertEqual(seen, {letter: {"A", "B", "C"} for letter in "ABC"})  # no fixed point
        with self.assertRaises(ValueError):
            ev.ordered(entry, "CBA")

    def test_fact_rank_is_strict_like_the_editor(self):
        facts = [{"label": "A", "r1Roughness": 0.4, "outOfKeyRatio": 0.0, "repetitionVsPrevious": None},
                 {"label": "B", "r1Roughness": 0.5, "outOfKeyRatio": 0.0, "repetitionVsPrevious": None},
                 {"label": "C", "r1Roughness": 0.6, "outOfKeyRatio": 0.2, "repetitionVsPrevious": None}]
        self.assertEqual(ev.fact_rank(facts, "A", "r1Roughness"), "lowest")
        self.assertEqual(ev.fact_rank(facts, "C", "r1Roughness"), "highest")
        self.assertEqual(ev.fact_rank(facts, "B", "r1Roughness"), "neither")
        self.assertEqual(ev.fact_rank(facts, "A", "outOfKeyRatio"), "neither")  # a tie is no rank
        self.assertIsNone(ev.fact_rank(facts, "A", "repetitionVsPrevious"))


class ClientsTest(ReviewEvalCase):
    def test_meta_judge_is_the_default_meta_client_on_the_meta_ledger(self):
        client, _, _ = self.meta(pick("A", ("changedSlots", 32)))
        cfg = client.config
        self.assertEqual((cfg.provider, cfg.model, cfg.key_source), ("meta", "muse-spark-1.3", "MODEL_API_KEY"))
        self.assertEqual(client.ledger.path, (self.tmp / "meta.json").resolve())
        with self.assertRaises(LLMConfigError):  # no key: refused before any review
            ev.judge_client("meta", env={"THEARTIST_META_LEDGER": str(self.tmp / "meta.json")}, transport=Replies())
        with self.assertRaises(LLMConfigError):  # the meta judge is Meta, whatever the default provider says
            ev.judge_client("meta", env={"LLM_PROVIDER": "baseten", "BASETEN_API_KEY": KEY}, transport=Replies())

    def test_openweight_judge_is_baseten_on_the_judge_ledger_and_counts_its_retry(self):
        entry = self.entries[0]
        client, counting, transport = self.openweight(
            completion("Here is my choice.", OPEN_MODEL),
            pick("A", ("r1Roughness", entry["facts"][0]["r1Roughness"]), model=OPEN_MODEL))
        cfg = client.config
        self.assertEqual((cfg.provider, cfg.model, cfg.key_source), ("baseten", OPEN_MODEL, "BASETEN_API_KEY"))
        self.assertEqual((client.ledger.path, client.ledger.cap_usd), ((self.tmp / "judge.json").resolve(), 10.0))
        record = ev.run_review(entry, "ABC", client, counting)
        self.assertEqual((record["status"], record["attempts"], record["replies"], record["choiceStored"]),
                         ("ok", 2, 2, "A"))
        self.assertEqual(transport.calls[0]["reasoning_effort"], "low")  # the review's own effort
        self.assertEqual(client.ledger.snapshot()["entries"], 2)
        metrics = ev.order_metrics(self.by_name, [record])
        self.assertEqual((metrics["attempts"], metrics["jsonValidity"]), ("2 (1 retries)", "50%"))


class RunTest(ReviewEvalCase):
    def test_every_order_maps_back_to_the_stored_letters(self):
        entry = self.entries[0]  # complete_bossa: stored C has the lowest roughness
        a_roughness = entry["facts"][0]["r1Roughness"]
        client, counting, transport = self.meta(pick("A", ("r1Roughness", a_roughness), ("changedSlots", 32)))
        document = self.run_eval(client, counting, [entry])
        self.assertEqual([(r["order"], r["choice"], r["choiceStored"]) for r in document["reviews"]],
                         [("ABC", "A", "A"), ("BCA", "A", "B"), ("CAB", "A", "C")])
        # The same value checked against the chosen row: true for stored A only
        self.assertEqual([[r["confirmed"] for r in record["reasons"]] for record in document["reviews"]],
                         [[True, True], [False, True], [False, True]])
        self.assertTrue(all(record["factsAsBuilt"] for record in document["reviews"]))
        sent = json.loads(transport.calls[2]["messages"][1]["content"])
        self.assertEqual(sent["candidates"][0]["chords"], entry["body"]["candidates"][2]["chords"])
        consistency = ev.consistency_metrics(self.by_name, document["reviews"])
        self.assertEqual((consistency["complete"], consistency["consistent"], consistency["pairwise"]),
                         (1, "0/1 (0%)", "0/3 (0%)"))
        metrics = ev.order_metrics(self.by_name, document["reviews"])
        self.assertEqual((metrics["r1Agree"], metrics["storedAAgree"], metrics["confirmed"], metrics["shownPicks"]),
                         ("1/3 (33%)", "1/3 (33%)", "4/6 (67%)", "3 / 0 / 0"))
        self.assertEqual(document["spentUsd"], round(sum(r["costUsd"] for r in document["reviews"]), 8))

    def test_a_judge_that_always_picks_the_middle_letter_is_never_consistent(self):
        entries = self.entries[:4]
        replies = [pick("B", ("changedSlots", entry["bars"] * 2)) for entry in entries for _ in ev.ORDERS]
        client, counting, _ = self.meta(*replies)
        document = self.run_eval(client, counting, entries)
        consistency = ev.consistency_metrics(self.by_name, document["reviews"])
        self.assertEqual((consistency["complete"], consistency["consistent"]), (4, "0/4 (0%)"))
        self.assertEqual(consistency["storedPicks"], "4 / 4 / 4")  # the letter, not the chords
        self.assertEqual(ev.order_metrics(self.by_name, document["reviews"])["shownPicks"], "0 / 12 / 0")

    def test_a_judge_that_picks_by_the_chords_is_consistent_and_spreads_over_the_letters(self):
        entries = self.entries[:4]
        client, counting, _ = self.meta(transport=ContentJudge())
        document = self.run_eval(client, counting, entries)
        consistency = ev.consistency_metrics(self.by_name, document["reviews"])
        self.assertEqual((consistency["consistent"], consistency["pairwise"]), ("4/4 (100%)", "12/12 (100%)"))
        metrics = ev.order_metrics(self.by_name, document["reviews"])
        self.assertEqual((metrics["r1Agree"], metrics["shownPicks"], metrics["confirmed"]),
                         ("12/12 (100%)", "4 / 4 / 4", "12/12 (100%)"))
        r1 = ev.baseline_metrics(self.by_name, document["reviews"])["R1 pick (lowest r1Roughness)"]
        self.assertEqual((r1["n"], r1["meanRoughness"]), (12, consistency["meanRoughness"]))

    def test_a_failed_review_counts_as_no_agreement_and_its_latency_and_cost_count(self):
        entry = self.entries[0]
        best = ev._baseline(entry)
        shown_best = {order: next(s for s, t in ev.ordered(entry, order)[1].items() if t == best) for order in ev.ORDERS}
        client, counting, _ = self.meta(pick(shown_best["ABC"], ("changedSlots", 32)), TimeoutError("slow"),
                                        pick(shown_best["CAB"], ("changedSlots", 32)))
        document = self.run_eval(client, counting, [entry])
        self.assertEqual([r["status"] for r in document["reviews"]], ["ok", "error", "ok"])
        metrics = ev.order_metrics(self.by_name, document["reviews"])
        self.assertEqual((metrics["r1Agree"], metrics["r1AgreeCompleted"]), ("2/3 (67%)", "2/2 (100%)"))
        self.assertEqual((metrics["failures"], metrics["attempts"], metrics["jsonValidity"]),
                         ("timeout 1", "3 (0 retries)", "100%"))  # the timeout got no reply
        self.assertGreater(document["reviews"][1]["costUsd"], 0)  # a timeout settles its reservation
        consistency = ev.consistency_metrics(self.by_name, document["reviews"])
        self.assertEqual((consistency["complete"], consistency["withFailure"], consistency["pairwise"]),
                         (0, 1, "1/1 (100%)"))
        self.assertEqual(ev.baseline_metrics(self.by_name, document["reviews"])["stored A (the planner run's order)"]["n"], 2)

    def test_the_spend_limit_stops_before_a_review_that_could_pass_it(self):
        client, counting, transport = self.meta(pick("A", ("changedSlots", 32)))
        # The first review fits exactly; after its spend, a second one's worst case would not
        document = self.run_eval(client, counting, self.entries[:2], max_usd=ev.review.REVIEW_MAX_USD)
        self.assertEqual(len(document["reviews"]), 1)
        self.assertIn("would pass --max-usd", document["stopped"])
        self.assertEqual(len(transport.calls), 1)

    def test_a_ledger_cap_stops_after_one_refused_review_that_sent_nothing(self):
        client, counting, transport = self.meta(pick("A", ("changedSlots", 32)), cap=0.001)
        document = self.run_eval(client, counting, self.entries[:2])
        self.assertEqual([r["error"]["kind"] for r in document["reviews"]], ["budget"])
        self.assertTrue(document["stopped"].startswith("budget failure"))
        self.assertEqual(transport.calls, [])
        metrics = ev.order_metrics(self.by_name, document["reviews"])
        self.assertEqual((metrics["attempts"], metrics["jsonValidity"], metrics["usdPerReview"]),
                         ("0 (0 retries, 1 refused unsent)", "-", "-"))

    def test_an_open_weight_retry_the_ledger_refused_keeps_its_cost_and_its_invalid_reply(self):
        entry = self.entries[0]
        client, counting, transport = self.openweight(completion("Here is my choice.", OPEN_MODEL), cap=0.012)
        document = self.run_eval(client, counting, [entry], judge="openweight")
        [record] = document["reviews"]
        self.assertEqual((record["error"]["kind"], record["attempts"], record["replies"]), ("budget", 1, 1))
        self.assertGreater(record["costUsd"], 0)  # the first attempt settled
        self.assertEqual(record["costUsd"], document["spentUsd"])
        metrics = ev.order_metrics(self.by_name, document["reviews"])
        self.assertEqual((metrics["attempts"], metrics["jsonValidity"]), ("1 (0 retries)", "0%"))

    def test_an_unreachable_provider_stops_after_two_reviews(self):
        client, counting, _ = self.meta(ConnectionError("blocked by the proxy"))
        document = self.run_eval(client, counting, self.entries[:3])
        self.assertEqual(len(document["reviews"]), ev.UNANSWERED_STOP)
        self.assertTrue(all(r["status"] == "error" and r["requestId"] is None for r in document["reviews"]))
        self.assertIn("no answer from the provider", document["stopped"])
        self.assertEqual(ev.order_metrics(self.by_name, document["reviews"])["jsonValidity"], "-")

    def test_failures_the_provider_answered_stop_after_three_in_a_row(self):
        client, counting, _ = self.meta(completion(json.dumps({"choice": "D", "reasons": []})))
        document = self.run_eval(client, counting, self.entries[:3])
        self.assertEqual(len(document["reviews"]), ev.FAILED_STOP)
        self.assertTrue(all(r["requestId"] for r in document["reviews"]))  # answered, so not "unanswered"
        self.assertIn("in a row failed", document["stopped"])
        self.assertEqual(ev.order_metrics(self.by_name, document["reviews"])["jsonValidity"], "0%")

    def test_an_interrupted_run_is_marked_and_keeps_its_spend(self):
        client, counting, _ = self.meta(pick("A", ("changedSlots", 32)), KeyboardInterrupt())
        document = self.run_eval(client, counting, self.entries[:2])
        self.assertEqual(len(document["reviews"]), 1)
        self.assertTrue(document["stopped"].startswith("interrupted"))
        self.assertEqual(document["spentUsd"], round(client.ledger.snapshot()["spent_usd"], 8))

    def test_no_key_is_written_and_a_failed_write_keeps_the_last_file(self):
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": KEY}):
            with self.assertRaises(RuntimeError):
                ev.write_results(self.tmp / "leak.json", {"note": f"key {KEY}"})
        self.assertFalse((self.tmp / "leak.json").exists())
        self.assertEqual(ev.scrubbed(str(ev.REPO_ROOT / "x")), "<repo>/x")
        path = self.tmp / "results.json"
        ev.write_results(path, {"reviews": [1]})
        with mock.patch.object(ev.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                ev.write_results(path, {"reviews": [1, 2]})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"reviews": [1]})
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["results.json"])  # no temp file left


class ReportTest(ReviewEvalCase):
    def test_report_renders_every_table(self):
        entries = self.entries[:2]
        replies = [pick("B", ("changedSlots", entry["bars"] * 2)) for entry in entries for _ in ev.ORDERS]
        client, counting, _ = self.meta(*replies)
        document = self.run_eval(client, counting, entries)
        self.assertEqual([r["choiceStored"] for r in document["reviews"]], ["B", "C", "A", "B", "C", "A"])
        text = ev.report(self.tmp / "out")
        for heading in ("## Inputs", "## Each judge and order", "## Position consistency", "## Facts the reasons cite",
                        "## Per section (stored letters)", "The baselines over the same completed reviews"):
            self.assertIn(heading, text)
        self.assertIn("| meta, all orders | 6 | 6/6 (100%) | 0 / 6 / 0 |", text)
        self.assertIn("| complete_bossa_f_16bar_64 | bossa | b_section | 16 | C | B (1/1) | C (1/1) | A (1/1) |", text)
        with self.assertRaises(FileNotFoundError):
            ev.report(self.tmp / "empty")

    def test_report_takes_every_files_sections_and_refuses_files_that_disagree(self):
        out = self.tmp / "out"
        client, counting, _ = self.meta(transport=ContentJudge())
        self.run_eval(client, counting, self.entries[:1], out=out / "results-meta.json")
        answers = [pick(ev.ordered(entry, order)[0].candidates[0].label, ("changedSlots", entry["bars"] * 2),
                        model=OPEN_MODEL) for entry in self.entries[:2] for order in ev.ORDERS]
        client, counting, _ = self.openweight(*answers)
        self.run_eval(client, counting, self.entries[:2], judge="openweight", out=out / "results-openweight.json")
        text = ev.report(out)
        second = next(line for line in text.splitlines() if line.startswith(f"| {self.entries[1]['request']} |"))
        self.assertEqual(second.count("not run"), 3)  # meta ran only the first section
        meta = json.loads((out / "results-meta.json").read_text(encoding="utf-8"))
        meta["sections"][0]["facts"][0]["r1Roughness"] = 9.9  # another code version
        (out / "results-meta.json").write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaises(ValueError):
            ev.report(out)


if __name__ == "__main__":
    unittest.main()
