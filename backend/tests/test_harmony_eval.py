"""Harmony evaluation: normalization, alignment, metrics, the datasets and the engine adapters (no network)."""

import contextlib
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.services import llm
from app.services.llm import Ledger, LLMClient, LLMConfig, LLMConfigError
from app.services.score_pdf import NoteEvent as ReadNote, PrintedChord, ScoreMeasure
from scripts.harmony_eval import (
    DATASET_PATH, EXPERIMENTS_DIR, REPO_ROOT, PrivateDataError, dataset, engines, outside_repo, run,
)
from scripts.harmony_eval.chords import Chord, align, normalize
from scripts.harmony_eval.dataset import (
    RECORDS, VARIANTS, build_dataset, build_real_dataset, dumps, load_songs, normalize_key, product_symbol,
)
from scripts.harmony_eval.engines import (
    AutoEngine, BarResult, LLMEngine, LocalEngine, SpendGuard, SpendLimit, measures_from_record, openweight_client,
)
from scripts.harmony_eval.metrics import Tally, call_stats, score_bar, score_slot
from scripts.harmony_eval.report import dataset_mismatch, render

KEY = "test-key-never-sent-as-note-data"
NORMALIZATION = {
    "C": (0, "maj", "none", 0), "Cm": (0, "min", "none", 0), "Cmin": (0, "min", "none", 0),
    "C-7": (0, "min", "min7", 0), "Cmi7": (0, "min", "min7", 0), "Cmaj7": (0, "maj", "maj7", 0),
    "CM7": (0, "maj", "maj7", 0), "CΔ": (0, "maj", "maj7", 0), "CΔ7": (0, "maj", "maj7", 0),
    "CΔ9": (0, "maj", "maj7", 0), "C∆9": (0, "maj", "maj7", 0), "CΔ11": (0, "maj", "maj7", 0),
    "C∆13": (0, "maj", "maj7", 0),
    "Cma7": (0, "maj", "maj7", 0), "Cmaj9": (0, "maj", "maj7", 0), "Cm9": (0, "min", "min7", 0),
    "Am11": (9, "min", "min7", 9), "CmMaj7": (0, "min", "maj7", 0), "Cm(maj7)": (0, "min", "maj7", 0),
    "Cdim": (0, "dim", "none", 0), "C°": (0, "dim", "none", 0), "Co7": (0, "dim", "dim7", 0),
    "Cdim7": (0, "dim", "dim7", 0), "C°7": (0, "dim", "dim7", 0), "Cø": (0, "dim", "halfdim7", 0),
    "Cø7": (0, "dim", "halfdim7", 0), "Cm7b5": (0, "dim", "halfdim7", 0), "F#m7b5": (6, "dim", "halfdim7", 6),
    "Caug": (0, "aug", "none", 0), "C+": (0, "aug", "none", 0), "Eaug7": (4, "aug", "dom7", 4),
    "C+maj7": (0, "aug", "maj7", 0), "Csus": (0, "sus", "none", 0), "Csus2": (0, "sus", "none", 0),
    "Dsus4": (2, "sus", "none", 2), "D7sus4": (2, "sus", "dom7", 2), "G13sus4": (7, "sus", "dom7", 7),
    "C7": (0, "maj", "dom7", 0), "C9": (0, "maj", "dom7", 0), "F13": (5, "maj", "dom7", 5),
    "C7b9": (0, "maj", "dom7", 0), "E7#9": (4, "maj", "dom7", 4), "C7(b9,#11)": (0, "maj", "dom7", 0),
    "C7alt": (0, "maj", "dom7", 0), "EbM7#11": (3, "maj", "maj7", 3), "C6": (0, "maj", "sixth", 0),
    "C6/9": (0, "maj", "sixth", 0), "Cm6": (0, "min", "sixth", 0), "C6/9/G": (0, "maj", "sixth", 7),
    "Cadd9": (0, "maj", "none", 0), "C(add9)": (0, "maj", "none", 0), "Cmadd9": (0, "min", "none", 0),
    "G7/B": (7, "maj", "dom7", 11), "C/E": (0, "maj", "none", 4), "Gsus4/D": (7, "sus", "none", 2),
    "Gdim/Bb": (7, "dim", "none", 10), "Cm/Eb": (0, "min", "none", 3), "A/C#": (9, "maj", "none", 1),
    "Db7": (1, "maj", "dom7", 1), "C#7": (1, "maj", "dom7", 1), "B#": (0, "maj", "none", 0),
    "Cb": (11, "maj", "none", 11), "A♭m7": (8, "min", "min7", 8), "F♯7": (6, "maj", "dom7", 6),
}


def note(pitch, onset, duration=2.0, staff=0, spelling=None):
    names = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
    return ReadNote(staff=staff, midi=pitch, spelling=spelling or f"{names[pitch % 12]}{pitch // 12 - 1}",
                    onset=onset, duration=duration, x=0.0, y=0.0)


def bar(index, pitches, *, chords=(), rhythm_exact=True, warnings=(), no_chord=False, onset=0.0):
    return ScoreMeasure(index=index, page=1, system=1, number=index + 1, time_signature=(4, 4),
                        notes=[note(pitch, onset) for pitch in pitches],
                        chords=[PrintedChord(symbol, 0.0, 0.0) for symbol in chords], no_chord=no_chord,
                        warnings=list(warnings), rhythm_exact=rhythm_exact)


C_MAJOR = (48, 60, 64, 67)  # C2 bass under a C4 triad
G_SEVENTH = (43, 59, 62, 65, 67)
# Three lines in the private file's format: a 4/4 song with a three-chord bar in the middle,
# a 3/4 song too short for a second excerpt, and a 6/8 song the loader drops
SONGS = (
    {"id": "fixture__test__0", "source": "billboard", "genre": "pop", "title": "Fixture Title One",
     "title_is_real": True, "split": "test", "key": "Ebmaj", "time_signature": "4/4", "n_bars": 20,
     "bars": [["Ebmaj", "Cm"], ["Abmaj", "Bb7"], ["Ebmaj"], ["Fm7", "Bb7"], ["Gm", "Cm"], ["Abmaj7"],
              ["Fm", "Bbsus4"], ["Ebmaj", "Ebmaj"], ["Cm7", "F7"], ["Ebmaj", "Abmaj", "Bbmaj"], ["Ebmaj"],
              ["Abmaj", "Bbmaj"], ["Gm7", "Cm7"], ["Fm7"], ["Bb7"], ["Ebmaj7", "Abmaj7"], ["Dm7b5", "G7"],
              ["Cm"], ["Abmaj", "Bb7"], ["Ebmaj"]]},
    {"id": "fixture__val__1", "source": "jht", "genre": "jazz", "title": "Fixture Title Two",
     "title_is_real": True, "split": "val", "key": "Amin", "time_signature": "3/4", "n_bars": 10,
     "bars": [["Am7"], ["Dm7", "G7"], ["Cmaj7"], ["Fmaj7"], ["Bm7b5", "E7"], ["Am"], ["Am7", "D9"], ["Dm9"],
              ["E7#9"], ["Am6"]]},
    {"id": "fixture__test__2", "source": "chordonomicon_folk", "genre": "folk", "title": "Fixture Title Three",
     "title_is_real": False, "split": "test", "key": "Dmaj", "time_signature": "6/8", "n_bars": 8,
     "bars": [["Dmaj"], ["Gmaj"], ["Amaj"], ["Dmaj"], ["Gmaj"], ["Amaj"], ["Bm"], ["Dmaj"]]},
)


def strings_in(node):
    """Every dict key and string value in a JSON-like object."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from strings_in(value)
    elif isinstance(node, list):
        for item in node:
            yield from strings_in(item)
    elif isinstance(node, str):
        yield node


class FakeTransport:
    """Answers each requested measure with the chords given by index; replies can be made invalid."""

    def __init__(self, chords_by_index=None, model="muse-spark-1.3", invalid_first=False):
        self.chords_by_index = chords_by_index or {}
        self.model = model
        self.invalid_first = invalid_first
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.invalid_first and len(self.requests) == 1:
            content = "not json at all"
        else:
            # The leading JSON object of the user turn; a retry appends the rejection text after it
            payload = json.JSONDecoder().raw_decode(request["messages"][1]["content"])[0]
            content = json.dumps({"measures": [
                {"index": measure["index"], "chords": self.chords_by_index.get(measure["index"], ["C"]),
                 "confidence": "high", "evidence": "The notes spell the chord; a possible harmonization."}
                for measure in payload["measures"]]})
        return ({"id": f"completion-{len(self.requests)}", "model": self.model,
                 "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                 "usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
                {"x-request-id": f"req-{len(self.requests)}"})


class UnreachableTransport:
    """Every request fails before it leaves the machine, as behind a proxy that refuses the host."""

    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        raise ConnectionError("blocked by the proxy")


class HarmonyEvalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = build_dataset()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def meta_client(self, transport):
        config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                           api_key=KEY, key_source="MODEL_API_KEY")
        return LLMClient(config, Ledger(self.tmp / "meta.json", cap_usd=1.0), transport)

    def write_songs(self):
        path = self.tmp / "songs.jsonl"
        path.write_text("".join(json.dumps(song) + "\n" for song in SONGS), encoding="utf-8")
        return path

    def assert_block_thirds(self, records):
        """Each slot of a block bar strikes the third its truth names, never the other; returns the slots checked."""
        checked = 0
        for record in records:
            if record["variant"] != "block":
                continue
            for item in record["bars"]:
                harmony = [note for note in item["notes"] if note["staff"] == 0]
                onsets = sorted({note["onset"] for note in harmony})
                self.assertEqual(len(onsets), 2, f"{record['id']} bar {item['index']}")
                for onset, symbol in zip(onsets, align(item["chords"])):
                    chord = normalize(symbol)
                    third = {"maj": 4, "aug": 4, "min": 3, "dim": 3}.get(chord.triad)
                    if third is None:  # a sus chord has no third
                        continue
                    struck = {note["pitch"] % 12 for note in harmony if note["onset"] == onset}
                    where = f"{record['id']} bar {item['index']} {symbol}: struck {sorted(struck)}"
                    self.assertIn((chord.root + third) % 12, struck, where)
                    self.assertNotIn((chord.root + 7 - third) % 12, struck, where)
                    checked += 1
        return checked

    def assert_struck_bass(self, records):
        """Every struck bass note is the bass its slot's truth names; returns the slots checked."""
        checked = 0
        for record in records:
            for item in record["bars"]:
                basses = sorted((note for note in item["notes"] if note["staff"] == dataset.BASS_STAFF),
                                key=lambda note: note["onset"])
                for note, symbol in zip(basses, align(item["chords"])):
                    where = f"{record['id']} bar {item['index']} {symbol}: bass {note['spelling']}"
                    self.assertEqual(note["pitch"] % 12, normalize(symbol).bass, where)
                    checked += 1
        return checked

    def quiet_main(self, main, argv):
        """main(argv) with its printing captured; returns (exit code, stdout text)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(run, "_ledgers", return_value=[
                    ("meta", Ledger(self.tmp / "ledger-meta.json", 25.0)),
                    ("baseten", Ledger(self.tmp / "ledger-baseten.json", 8.0))]):
            try:
                code = main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue() + err.getvalue()

    def test_symbol_normalization_table(self):
        for symbol, expected in NORMALIZATION.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(normalize(symbol), Chord(*expected))
        for symbol in ("N.C.", "X", "", "Cgibberish", "Cmajorminor", "C/", "C//G", "H7", "c", None, 7):
            with self.subTest(symbol=symbol):
                self.assertIsNone(normalize(symbol))
        # Enharmonic spellings compare equal
        self.assertEqual(normalize("Dbmaj7"), normalize("C#maj7"))
        self.assertEqual(normalize("G7/B"), normalize("G7/Cb"))

    def test_slot_alignment_follows_the_import(self):
        self.assertEqual(align(["C"]), ("C", "C"))
        self.assertEqual(align(["C", None]), ("C", "C"))
        self.assertEqual(align(["C", "G7"]), ("C", "G7"))
        self.assertEqual(align([]), (None, None))
        self.assertEqual(align(["C", "F", "G"]), (None, None))

    def test_metric_arithmetic_on_hand_made_cases(self):
        truth = normalize("Cmaj7/E")

        def matches(proposal):
            score = score_slot(truth, proposal, "high")
            return score.root, score.triad, score.seventh, score.bass, score.exact

        self.assertEqual(score_slot(truth, None, None).covered, False)
        self.assertTrue(score_slot(truth, "???", "high").unparseable)
        self.assertEqual(matches("Cmaj7/E"), (True, True, True, True, True))
        self.assertEqual(matches("C7/E"), (True, True, False, True, False))
        self.assertEqual(matches("Em"), (False, False, False, True, False))
        self.assertEqual(matches("Cmaj7"), (True, True, True, False, False))
        tally = Tally()
        tally.extend(score_bar(["Dm7", "G7"], ["Dm7", "G7"], "high"))   # 2 exact
        tally.extend(score_bar(["Cmaj7", None], ["C"], "medium"))        # 2 root+triad, seventh wrong
        tally.extend(score_bar(["F", None], [], None))                   # 2 uncovered
        tally.extend(score_bar(["G", None], ["G", "G7", "G"], "low"))    # more than two: unresolved
        tally.extend(score_bar(["A", "B", "C"], ["A"], "low"))           # truth without a two-slot form: not scored
        summary = tally.summary()
        self.assertEqual((summary["slots"], summary["covered"], summary["coverage"]), (8, 4, .5))
        self.assertEqual(summary["all"], {"root": .5, "triad": .5, "seventh": .25, "bass": .5, "exact": .25})
        self.assertEqual(summary["on_covered"], {"root": 1.0, "triad": 1.0, "seventh": .5, "bass": 1.0, "exact": .5})
        self.assertEqual(summary["calibration"], {"high": {"slots": 2, "root": 1.0, "exact": 1.0},
                                                  "medium": {"slots": 2, "root": 1.0, "exact": 0.0}})
        stats = call_stats([{"latency_ms": 10, "cost_usd": .01, "status": "ok", "bars": 8, "request_id": "a", "attempts": 2},
                            {"latency_ms": 30, "cost_usd": .02, "status": "invalid_json", "bars": 4, "request_id": "b",
                             "attempts": 2}])
        self.assertEqual((stats["calls"], stats["attempts"], stats["retries"], stats["retry_rate"]), (2, 4, 2, 1.0))
        self.assertEqual((stats["json_validity"], stats["failed"], stats["bars_sent"]), (.25, {"invalid_json": 1}, 12))
        self.assertEqual((stats["latency_ms_p50"], stats["latency_ms_p95"], stats["cost_usd"]), (10, 30, .03))

    def test_dataset_is_deterministic_and_every_bar_has_notes(self):
        self.assertEqual(dumps(self.records), dumps(build_dataset()))
        self.assertNotEqual(dumps(self.records), dumps(build_dataset(seed=1)))
        self.assertEqual(len(self.records), RECORDS)
        self.assertEqual({record["variant"] for record in self.records}, set(VARIANTS))
        self.assertEqual(len({record["id"] for record in self.records}), RECORDS)
        for record in self.records:
            self.assertEqual(set(record), {"id", "source", "progression", "genre", "key", "timeSignature", "variant", "bars"})
            self.assertEqual(record["timeSignature"], [3, 4] if record["variant"] == "waltz" else [4, 4])
            for item in record["bars"]:
                self.assertTrue(item["notes"], f"{record['id']} bar {item['index']} has no notes")
                self.assertTrue(item["chords"][0])
                for symbol in item["chords"]:  # both slots: a truth the scorer cannot read would go unscored
                    self.assertTrue(symbol is None or normalize(symbol),
                                    f"{record['id']} bar {item['index']}: {symbol}")
                self.assertTrue(all(0 <= n["pitch"] <= 127 and n["duration"] > 0 for n in item["notes"]))
        inversions = [record for record in self.records if record["variant"] == "inversion"]
        self.assertTrue(all("/" in item["chords"][0] for record in inversions for item in record["bars"]))
        # The committed file is the builder's output
        self.assertEqual(DATASET_PATH.read_text(encoding="utf-8"), dumps(self.records))

    def test_block_realization_strikes_the_third_its_truth_names(self):
        self.assertGreater(self.assert_block_thirds(self.records), 100)
        songs, _, _ = load_songs(self.write_songs())
        real = build_real_dataset(songs, total=4)
        self.assertGreater(self.assert_block_thirds(real), 0)
        # The check catches the voicing table without "m" that played Am as A major
        tones = {quality: tones for quality, tones in dataset._CHORD_TONES.items() if quality != "m"}
        with mock.patch.dict(dataset._CHORD_TONES, tones, clear=True):
            with self.assertRaisesRegex(AssertionError, "Am|Em|Dm"):
                self.assert_block_thirds(build_dataset())

    def test_every_struck_bass_is_the_bass_its_truth_names(self):
        self.assertGreater(self.assert_struck_bass(self.records), 400)
        inversions = [record for record in self.records if record["variant"] == "inversion"]
        self.assertGreater(self.assert_struck_bass(inversions), 100)
        songs, _, _ = load_songs(self.write_songs())
        self.assertGreater(self.assert_struck_bass(build_real_dataset(songs, total=4)), 0)
        # A one-chord bar whose second half strikes another bass is caught
        broken = json.loads(json.dumps(inversions[0]))
        item = next(item for item in broken["bars"] if item["chords"][1] is None)
        basses = sorted((note for note in item["notes"] if note["staff"] == dataset.BASS_STAFF),
                        key=lambda note: note["onset"])
        basses[1]["pitch"] += 1
        with self.assertRaisesRegex(AssertionError, "bass"):
            self.assert_struck_bass([broken])

    def test_inversion_basses_are_names_the_product_can_strike(self):
        for key in ("C major", "E major", "F minor"):
            for symbol in ("C#", "G#7", "Abm", "Fm7b5", "Fdim", "Bbdim", "Eaug", "A#m", "Csus4", "Gsus4", "Asus2",
                           "Dsus2"):
                for seed in range(6):
                    inverted = dataset._inverted(symbol, random.Random(seed), key)
                    with self.subTest(key=key, symbol=symbol, seed=seed, inverted=inverted):
                        self.assertIn(inverted.split("/")[1], dataset._NOTE_PC)
                        self.assertEqual(dataset._bass_pc(inverted), normalize(inverted).bass)

    def test_a_connection_error_stops_the_run_after_one_reservation(self):
        transport = UnreachableTransport()
        engine = LLMEngine("meta", self.meta_client(transport))
        section = run.run_synthetic(engine, self.records[:2], log=lambda *a, **k: None)
        self.assertFalse(section["complete"])
        self.assertTrue(section["stopped"].startswith("LLMConnectionError: "), section["stopped"])
        self.assertEqual((len(transport.requests), len(section["calls"])), (1, 1))
        self.assertEqual(section["calls"][0]["status"], "LLMConnectionError")
        self.assertEqual(section["records"], [])

    def test_prior_spend_counts_each_family_of_results_on_its_own(self):
        files = {
            "results-meta.json": {"engine": "meta", "provider": "meta", "synthetic": {"cost_usd": 3.0},
                                  "real": {"cost_usd": .25}},
            "results-real-songs-meta.json": {"engine": "meta", "provider": "meta", "real_songs": {"cost_usd": .5}},
            "results-real-songs-auto.json": {"engine": "auto", "provider": "meta", "real_songs": {"cost_usd": .125}},
        }
        for name, content in files.items():
            (self.tmp / name).write_text(json.dumps(content), encoding="utf-8")
        self.assertEqual(run.prior_spend(self.tmp, "meta", ("auto", "real_songs")), .5)
        self.assertEqual(run.prior_spend(self.tmp, "meta", ("meta", "real_songs")), .125)
        self.assertEqual(run.prior_spend(self.tmp, "meta", ("auto", "synthetic")), 3.25)
        self.assertEqual(run.prior_spend(self.tmp, "meta", ("meta", "synthetic")), .25)
        self.assertEqual(run.prior_spend(self.tmp, "baseten", ("openweight", "synthetic")), 0.0)

    def test_a_ledger_stop_names_no_local_path(self):
        config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                           api_key=KEY, key_source="MODEL_API_KEY")
        transport = FakeTransport()
        engine = LLMEngine("meta", LLMClient(config, Ledger(self.tmp / "meta.json", cap_usd=.001), transport))
        section = run.run_synthetic(engine, self.records[:1], log=lambda *a, **k: None)
        self.assertTrue(section["stopped"].startswith("BudgetExceeded: "), section["stopped"])
        self.assertEqual(transport.requests, [])
        self.assertNotIn(str(self.tmp), json.dumps(section))

    def test_the_report_refuses_to_compare_engines_run_on_different_datasets(self):
        same = {"local": {"dataset": {"sha256": "a" * 64}, "real_songs": {"bars": 1}},
                "meta": {"dataset": {"sha256": "a" * 64}, "real_songs": {"bars": 1}},
                "openweight": {"dataset": {"sha256": "b" * 64}, "real_songs": None}}
        self.assertIsNone(dataset_mismatch(same, "real_songs"))
        same["meta"]["dataset"]["sha256"] = "c" * 64
        self.assertRegex(dataset_mismatch(same, "real_songs"), r"Not comparable.*local `aaaaaaaaaaaa…`, meta `cccccccccccc…`")

    def test_truth_symbols_the_scorer_cannot_read_are_counted_not_dropped(self):
        tally = Tally()
        self.assertEqual(tally.add_bar(["Cgibberish", None], ["C"], "high"), [])  # one symbol fills both slots
        self.assertEqual(len(tally.add_bar(["C", "Hm7"], ["C", "G"], "high")), 1)
        tally.add_bar(["A", "B", "C"], ["A"], "low")  # no two-slot form: not scored, not a symbol problem
        summary = tally.summary()
        self.assertEqual((summary["slots"], summary["unscored_truth"], summary["all"]["exact"]), (1, 3, 1.0))

    def test_local_engine_runs_the_product_analyzer_on_read_notes(self):
        engine = LocalEngine()
        results = engine.analyze([bar(0, C_MAJOR), bar(1, G_SEVENTH), bar(2, [])], "C major")
        self.assertEqual([result.chords for result in results], [("C",), ("G7",), ()])
        self.assertEqual([result.confidence for result in results], ["medium", "medium", None])
        self.assertEqual(len(engine.calls), 3)
        self.assertTrue(all(call.cost_usd == 0 and call.status == "ok" for call in engine.calls))
        self.assertEqual(engine.analyze([bar(0, C_MAJOR, rhythm_exact=False)], "C major")[0].confidence, "low")

    def test_meta_engine_batches_notes_only_with_the_key_and_never_the_truth(self):
        transport = FakeTransport({index: ["F7"] for index in range(12)})
        engine = LLMEngine("meta", self.meta_client(transport))
        record = next(record for record in self.records if "12-bar-blues" in record["id"])
        results = engine.analyze(measures_from_record(record), record["key"])
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual([len(json.loads(r["messages"][1]["content"])["measures"]) for r in transport.requests], [8, 4])
        payload = json.loads(transport.requests[0]["messages"][1]["content"])
        self.assertEqual((payload["key"], payload["context"]), ("F major", []))
        self.assertEqual(set(payload["measures"][0]), {"index", "timeSignature", "notes", "timingIsEstimated", "readWarnings"})
        for request in transport.requests:
            for symbol in {chord for item in record["bars"] for chord in item["chords"] if chord}:
                self.assertNotIn(f'"{symbol}"', json.dumps(request["messages"]))
        self.assertEqual([result.chords for result in results], [("F7",)] * 12)
        self.assertEqual({result.confidence for result in results}, {"high"})
        self.assertEqual([result.request_id for result in results], ["req-1"] * 8 + ["req-2"] * 4)
        self.assertEqual([(call.bars, call.status, call.attempts, call.request_id) for call in engine.calls],
                         [(8, "ok", 1, "req-1"), (4, "ok", 1, "req-2")])
        self.assertEqual(engine.calls[0].cost_usd, .003375)
        self.assertEqual(engine.client.ledger.snapshot()["spent_usd"], .00675)

    def test_meta_failures_are_recorded_as_failures_not_as_chords(self):
        transport = FakeTransport({0: ["Not a chord!!"]})
        engine = LLMEngine("meta", self.meta_client(transport))
        results = engine.analyze([bar(0, C_MAJOR), bar(1, [])], "C major")
        self.assertEqual([(r.chords, r.confidence, r.error) for r in results],
                         [((), None, "harmony_validation"), ((), None, "no_notes")])
        self.assertEqual((engine.calls[0].status, engine.calls[0].bars), ("harmony_validation", 1))

    def test_openweight_client_is_baseten_at_high_effort_on_its_own_ledger_and_counts_retries(self):
        transport = FakeTransport({0: ["Cmaj7"]}, model="meta-models/muse-spark-open-1026", invalid_first=True)
        with mock.patch.object(engines, "OPENWEIGHT_LEDGER_PATH", self.tmp / "baseten.json"):
            client, counting = openweight_client(transport, env={"BASETEN_API_KEY": KEY})
        cfg = client.config
        self.assertEqual((cfg.provider, cfg.model, cfg.reasoning_effort, cfg.key_source, cfg.api_key),
                         ("baseten", "meta-models/muse-spark-open-1026", "high", "BASETEN_API_KEY", KEY))
        self.assertEqual((client.ledger.path, client.ledger.cap_usd), ((self.tmp / "baseten.json").resolve(), 8.0))
        prices = (cfg.price_input_per_m, cfg.price_cached_per_m, cfg.price_output_per_m)
        self.assertEqual(prices, llm.BASETEN_PRICES)
        # Baseten's own list price, not LLMConfig's Spark default that it equals today
        with mock.patch.object(engines, "OPENWEIGHT_LEDGER_PATH", self.tmp / "baseten.json"), \
                mock.patch.object(engines, "BASETEN_PRICES", (2.0, .2, 6.0)):
            repriced = openweight_client(FakeTransport(), env={"BASETEN_API_KEY": KEY})[0].config
        self.assertEqual((repriced.price_input_per_m, repriced.price_cached_per_m, repriced.price_output_per_m),
                         (2.0, .2, 6.0))
        engine = LLMEngine("openweight", client, transport=counting)
        results = engine.analyze([bar(0, C_MAJOR)], "C major")
        self.assertEqual(results[0].chords, ("Cmaj7",))
        self.assertEqual(transport.requests[0]["reasoning_effort"], "high")
        self.assertIn("max_tokens", transport.requests[0])
        self.assertEqual((engine.calls[0].attempts, engine.calls[0].status), (2, "ok"))
        stats = call_stats([call.to_dict() for call in engine.calls])
        self.assertEqual((stats["retries"], stats["retry_rate"], stats["json_validity"]), (1, 1.0, .5))
        self.assertEqual(client.ledger.snapshot()["entries"], 2)

    def test_a_missing_key_is_a_configuration_error_before_any_run(self):
        with mock.patch.object(engines, "OPENWEIGHT_LEDGER_PATH", self.tmp / "baseten.json"):
            with self.assertRaisesRegex(LLMConfigError, "BASETEN_API_KEY is not set"):
                openweight_client(FakeTransport(), env={})
            with mock.patch.dict("os.environ", {"BASETEN_API_KEY": ""}):
                with self.assertRaises(LLMConfigError):
                    engines.build_engine("openweight", max_usd=8.0)
        keyless = LLMClient(LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                                      key_source="MODEL_API_KEY"), Ledger(self.tmp / "meta.json", 1.0), FakeTransport())
        with mock.patch.object(engines, "meta_client", return_value=keyless):
            with self.assertRaisesRegex(LLMConfigError, "MODEL_API_KEY is not set"):
                engines.build_engine("meta", max_usd=4.0)
        self.assertFalse((self.tmp / "baseten.json").exists())

    def test_auto_engine_sends_only_the_bars_local_left_open_and_keeps_local_chords(self):
        transport = FakeTransport({1: ["Dm7"], 3: ["G7"]})
        engine = AutoEngine(LocalEngine(), LLMEngine("meta", self.meta_client(transport)))
        measures = [bar(0, C_MAJOR), bar(1, C_MAJOR), bar(2, G_SEVENTH), bar(3, G_SEVENTH, rhythm_exact=False)]
        real_inference = engines._inferred_harmony

        def unreadable_odd_bars(measure, *args):
            return ([], "unreadable", "low", "") if measure.index % 2 else real_inference(measure, *args)

        with mock.patch.object(engines, "_inferred_harmony", side_effect=unreadable_odd_bars):
            results = engine.analyze(measures, "C major")
        self.assertEqual([json.loads(r["messages"][1]["content"])["measures"][i]["index"]
                          for r in transport.requests for i in range(2)], [1, 3])
        self.assertEqual([(r.chords, r.source, r.confidence) for r in results],
                         [(("C",), "local", "medium"), (("Dm7",), "meta", "high"),
                          (("G7",), "local", "medium"), (("G7",), "meta", "low")])
        self.assertEqual(len(engine.calls), 1)
        self.assertEqual(engine.analyze([bar(0, C_MAJOR)], "C major")[0].source, "local")
        self.assertEqual(len(transport.requests), 1)

    def test_spend_guard_stops_a_run_before_the_limit_and_marks_it_incomplete(self):
        ledger = Ledger(self.tmp / "meta.json", cap_usd=1.0)
        guard = SpendGuard(ledger, max_usd=.15, prior_usd=.0)
        guard.check()
        entry = ledger.reserve(label="t", provider="meta", model="m", reserved_usd=.06)
        ledger.settle(entry, settled_usd=.06, status="settled")
        with self.assertRaisesRegex(SpendLimit, "0.15"):
            guard.check()
        self.assertEqual(SpendGuard(ledger, max_usd=.15, prior_usd=.0).spent(), 0.0)
        transport = FakeTransport()
        client = self.meta_client(transport)
        engine = LLMEngine("meta", client, guard=SpendGuard(client.ledger, max_usd=.05, prior_usd=.0))
        section = run.run_synthetic(engine, self.records[:2], log=lambda *a, **k: None)
        self.assertFalse(section["complete"])
        self.assertIn("SpendLimit", section["stopped"])
        self.assertEqual((section["records"], transport.requests, section["cost_usd"]), ([], [], 0.0))

    def test_run_synthetic_records_per_bar_outputs_calls_and_metrics(self):
        transport = FakeTransport()
        engine = LLMEngine("meta", self.meta_client(transport))
        section = run.run_synthetic(engine, self.records[:1], log=lambda *a, **k: None)
        self.assertTrue(section["complete"])
        self.assertEqual(section["bars"], len(self.records[0]["bars"]))
        first = section["records"][0]["bars"][0]
        self.assertEqual(set(first), {"index", "chords", "confidence", "source", "evidence", "request_id", "error", "truth"})
        self.assertEqual(section["metrics"]["slots"], 2 * section["bars"])
        self.assertEqual(section["call_stats"]["request_ids"], ["req-1"])
        self.assertEqual(section["cost_usd"], .003375)
        self.assertNotIn(KEY, json.dumps(section))

    def test_real_score_keeps_only_bars_with_printed_chords_and_notes_and_hides_the_chords(self):
        measures = [bar(0, C_MAJOR, chords=["C"]), bar(1, C_MAJOR, chords=["C", "G7"]), bar(2, C_MAJOR),
                    bar(3, [], chords=["F"]), bar(4, C_MAJOR, chords=["C", "F", "G"]), bar(5, C_MAJOR, no_chord=True),
                    bar(6, G_SEVENTH, chords=["G7"], rhythm_exact=False, warnings=["Beams unclear."])]
        score = SimpleNamespace(measures=measures, key=None, key_signature=1, time_signature=(4, 4))
        estimate = SimpleNamespace(key="G major", source="inferred", confidence=.3)
        seen = []

        class Engine(LocalEngine):
            def analyze(self, bars, key):
                seen.extend(bars)
                return super().analyze(bars, key)

        with mock.patch.object(run, "parse_vector_score", return_value=score), \
                mock.patch.object(run, "_score_events", return_value=[]), \
                mock.patch.object(run, "estimate_key", return_value=estimate):
            section, private = run.run_real(Engine(), b"%PDF-", log=lambda *a, **k: None)
        self.assertEqual([m.index for m in seen], [0, 1, 6])
        self.assertTrue(all(m.chords == [] and not m.no_chord for m in seen))
        self.assertEqual(section["excluded"], {"no_printed_chords": 1, "no_notes": 1,
                                               "more_than_two_printed_chords": 1, "no_chord_sign": 1})
        self.assertEqual((section["bars_total"], section["bars_scored"], section["key"], section["timing_estimated_bars"]),
                         (7, 3, "G major", 1))
        self.assertEqual(section["metrics"]["slots"], 6)
        self.assertEqual([item["truth"] for item in private["bars"]], [["C"], ["C", "G7"], ["G7"]])
        for text in (json.dumps(section), json.dumps(private)):  # no note data, no chord symbols in the public rows
            self.assertNotIn('"pitch"', text)
            self.assertNotIn('"spelling"', text)
        self.assertNotIn('"truth"', json.dumps(section))

    def test_sensitivity_a_mutated_output_lowers_the_metric(self):
        truths = [["Dm7", "G7"], ["Cmaj7", None], ["F", "G/B"], ["C", None]]
        perfect = [[c for c in chords if c] for chords in truths]

        def exact(outputs, confidence="high"):
            tally = Tally()
            for truth, output in zip(truths, outputs):
                tally.extend(score_bar(truth, output, confidence))
            return tally.summary()

        base = exact(perfect)
        self.assertEqual((base["coverage"], base["all"]["exact"]), (1.0, 1.0))
        wrong_root = exact([["Em7", "G7"], *perfect[1:]])
        self.assertLess(wrong_root["all"]["root"], base["all"]["root"])
        self.assertLess(wrong_root["all"]["exact"], base["all"]["exact"])
        wrong_seventh = exact([*perfect[:1], ["C7"], *perfect[2:]])
        self.assertEqual(wrong_seventh["all"]["root"], base["all"]["root"])
        self.assertLess(wrong_seventh["all"]["seventh"], base["all"]["seventh"])
        wrong_bass = exact([*perfect[:2], ["F", "G"], perfect[3]])
        self.assertEqual(wrong_bass["all"]["seventh"], base["all"]["seventh"])
        self.assertLess(wrong_bass["all"]["bass"], base["all"]["bass"])
        self.assertLess(wrong_bass["all"]["exact"], base["all"]["exact"])
        dropped = exact([*perfect[:3], []])
        self.assertLess(dropped["coverage"], base["coverage"])
        self.assertLess(dropped["all"]["exact"], base["all"]["exact"])
        self.assertEqual(dropped["on_covered"]["exact"], 1.0)

    def test_report_renders_a_row_per_engine_and_the_real_score_aggregates(self):
        transport = FakeTransport()
        engine = LLMEngine("meta", self.meta_client(transport))
        synthetic = run.run_synthetic(engine, self.records[:1], log=lambda *a, **k: None)
        real = {"label": run.REAL_LABEL, "complete": True, "stopped": None, "bars_total": 52, "bars_scored": 37,
                "excluded": {"no_printed_chords": 7}, "timing_estimated_bars": 30, "bars_with_reader_warnings": 30,
                "meters": {"4/4": 37}, "key": "G major", "key_source": "inferred", "key_confidence": .3,
                "calls": synthetic["calls"], "call_stats": synthetic["call_stats"], "cost_usd": synthetic["cost_usd"],
                "metrics": synthetic["metrics"]}
        results = {"meta": {"engine": "meta", "provider": "meta", "model": "muse-spark-1.3",
                            "settings": engine.describe(), "dataset": {"path": "experiments/harmony_eval/dataset.jsonl",
                                                                       "sha256": "abc", "records": 1, "bars": 8},
                            "synthetic": synthetic, "real": real},
                   "local": {"engine": "local", "provider": "local", "model": "harmony_analysis", "settings": {},
                             "dataset": {}, "synthetic": None, "real": None}}
        text = render(results)
        self.assertIn("| meta | 16 |", text)
        self.assertIn("one private real score, 37 bars", text)
        self.assertIn("**local**: the product's deterministic analyzer, no model — not run", text)
        self.assertIn("## By variant", text)
        self.assertIn("complete; truth slots left unscored: 0", text)
        self.assertNotIn(KEY, text)

    def test_report_survives_an_engine_stopped_before_its_first_record(self):
        local = run.run_synthetic(LocalEngine(), self.records[:2], log=lambda *a, **k: None)
        client = self.meta_client(FakeTransport())
        engine = LLMEngine("meta", client, guard=SpendGuard(client.ledger, max_usd=.05, prior_usd=.0))
        stopped = run.run_synthetic(engine, self.records[:2], log=lambda *a, **k: None)
        self.assertEqual((stopped["records"], stopped["complete"]), ([], False))
        self.assertTrue(stopped["stopped"].startswith("SpendLimit: "))
        results = {"local": {"engine": "local", "provider": "local", "model": "harmony_analysis", "settings": {},
                             "dataset": {}, "synthetic": local, "real": None},
                   "meta": {"engine": "meta", "provider": "meta", "model": "muse-spark-1.3",
                            "settings": engine.describe(), "dataset": {}, "synthetic": stopped, "real": None}}
        text = render(results)
        self.assertIn("- **meta**, synthetic: exact – (– vs ", text)
        self.assertIn("; no variant scored; $0.0000 for 0 calls, p50 – per call", text)
        self.assertIn("— incomplete (SpendLimit: ", text)

    def test_real_song_loader_keeps_4_4_and_3_4_normalizes_keys_and_skips_three_chord_bars(self):
        songs, dropped, left_out = load_songs(self.write_songs())
        self.assertEqual([(song["id"], song["key"], song["meter"]) for song in songs],
                         [("fixture__test__0", "Eb major", (4, 4)), ("fixture__val__1", "A minor", (3, 4))])
        self.assertEqual((dict(dropped), dict(left_out)), ({"meter": 1}, {"more_than_two_chords": 1}))
        pop, jazz = songs
        self.assertIsNone(pop["bars"][9])
        self.assertEqual(pop["bars"][:3], [["Eb", "Cm"], ["Ab", "Bb7"], ["Eb", None]])
        self.assertEqual(pop["bars"][7], ["Eb", None])  # a repeated chord fills the bar, as the import does
        self.assertEqual([normalize_key(text) for text in ("Ebmaj", "Amin", "F#min", "Hmaj", "Eb major", None)],
                         ["Eb major", "A minor", "F# minor", None, None, None])
        self.assertEqual([product_symbol(text) for text in ("Ebmaj", "F#m7", "Bbmaj/D", "Am", "E7#9", "Cfoo", "Cbmaj")],
                         ["Eb", "F#m7", "Bb/D", "Am", "E7#9", None, None])
        records = build_real_dataset(songs, total=4)
        self.assertEqual(sorted((record["genre"], record["song"]) for record in records),
                         [("jazz", "fixture__val__1"), ("pop", "fixture__test__0"), ("pop", "fixture__test__0")])
        for record in records:
            if record["song"] == pop["id"]:  # never across the three-chord bar 9
                self.assertTrue(record["start"] + 8 <= 9 or record["start"] >= 10, record["start"])
            self.assertEqual(len(record["bars"]), 8)
            for item in record["bars"]:
                self.assertLessEqual(len([symbol for symbol in item["chords"] if symbol]), 2)
                self.assertTrue(all(normalize(symbol) for symbol in item["chords"] if symbol))
        starts = sorted(record["start"] for record in records if record["genre"] == "pop")
        self.assertGreaterEqual(starts[1] - starts[0], 8)  # the song's two excerpts do not overlap
        three_four = next(record for record in records if record["genre"] == "jazz")
        self.assertEqual(three_four["timeSignature"], [3, 4])
        self.assertTrue(all(note["onset"] + note["duration"] <= 3.0
                            for item in three_four["bars"] for note in item["notes"]))
        self.assertEqual({record["keySource"] for record in records}, {"file"})
        # The corpus placeholder C major is replaced by the product's estimate over the excerpt's chords
        placeholder = build_real_dataset([{**pop, "key": "C major"}], total=1)[0]
        self.assertEqual((placeholder["keySource"], placeholder["fileKey"]), ("estimated", "C major"))
        self.assertIn(placeholder["key"], ("Eb major", "C minor"))

    def test_real_song_dataset_is_deterministic(self):
        songs, _, _ = load_songs(self.write_songs())
        first = dumps(build_real_dataset(songs, total=4))
        self.assertEqual(first, dumps(build_real_dataset(load_songs(self.write_songs())[0], total=4)))
        self.assertGreater(len({dumps(build_real_dataset(songs, seed=seed, total=4)) for seed in range(6)}), 1)

    def test_real_song_results_carry_aggregates_only(self):
        songs, dropped, left_out = load_songs(self.write_songs())
        records = build_real_dataset(songs, total=4)
        engine = LLMEngine("meta", self.meta_client(FakeTransport({index: ["Ebmaj7", "Cm"] for index in range(8)})))
        section, outputs = run.run_real_songs(engine, records, log=lambda *a, **k: None)
        results = {"engine": "meta", "provider": "meta", "model": "muse-spark-1.3", "settings": engine.describe(),
                   "dataset": run.real_songs_facts(songs, dropped, left_out, records, 7), "real_songs": section}
        private = run.private_strings(songs, records, outputs)
        run.assert_aggregate(results, private)
        self.assertEqual((section["excerpts"], section["bars"], results["dataset"]["slots"]), (3, 24, 48))
        self.assertEqual(set(section["by_genre"]), {"jazz", "pop"})
        self.assertEqual(sum(group["slots"] for group in section["by_variant"].values()), section["metrics"]["slots"])
        self.assertEqual(section["call_stats"]["request_ids"], ["req-1", "req-2", "req-3"])
        strings = set(strings_in(results))
        symbols = {symbol for song in SONGS for bar in song["bars"] for symbol in bar}
        symbols |= {symbol for record in records for item in record["bars"] for symbol in item["chords"] if symbol}
        self.assertFalse(strings & (symbols | {"Ebmaj7", "Cm"}))
        self.assertFalse([text for text in strings if normalize(text)])
        text = json.dumps(results, ensure_ascii=False)
        for song in SONGS:
            self.assertNotIn(song["title"], text)
            self.assertNotIn(song["id"], text)
        for field in ('"chords"', '"truth"', '"notes"', '"pitch"', '"title"', '"evidence"', '"song"'):
            self.assertNotIn(field, text)
        self.assertNotIn(KEY, text)
        # The guard refuses a per-bar field, a chord symbol or a private name anywhere in the object
        for leaked in ({**results, "real_songs": {**section, "truth": [["Eb", None]]}},
                       {**results, "note": ["Ebmaj7"]}, {**results, "label": "Fixture Title One"},
                       {**results, "where": str(REPO_ROOT.parent / ".tooling")}):
            with self.assertRaises(PrivateDataError):
                run.assert_aggregate(leaked, private)

    def test_real_song_run_writes_aggregates_in_the_repo_and_everything_else_outside(self):
        songs_path, out_dir, private_dir = self.write_songs(), self.tmp / "out", self.tmp / "private"
        code, printed = self.quiet_main(run.main, ["--engine", "local", "--songs", str(songs_path), "--out-dir",
                                                   str(out_dir), "--private-dir", str(private_dir), "--seed", "7"])
        self.assertEqual(code, 0, printed)
        self.assertIn("ledger meta (ledger-meta.json): spent $0.0000 of $25.00 before", printed)
        self.assertIn("ledger baseten (ledger-baseten.json): spent $0.0000 of $8.00 after (+$0.0000)", printed)
        self.assertEqual([path.name for path in out_dir.iterdir()], ["results-real-songs-local.json"])
        public = json.loads((out_dir / "results-real-songs-local.json").read_text(encoding="utf-8"))
        run.assert_aggregate(public)
        self.assertEqual((public["dataset"]["excerpts"], public["real_songs"]["metrics"]["slots"]), (3, 48))
        self.assertEqual(sorted(path.name for path in private_dir.iterdir()),
                         ["real-songs-dataset.jsonl", "real-songs-local.jsonl"])
        self.assertEqual((private_dir / "real-songs-dataset.jsonl").read_text(encoding="utf-8"),
                         dumps(build_real_dataset(load_songs(songs_path)[0], 7)))
        # Nothing derived from the songs goes inside the repository: not the per-bar outputs or the dataset,
        # and the songs file itself is refused there
        inside = EXPERIMENTS_DIR / "never-written"
        for main, argv in ((run.main, ["--engine", "local", "--songs", str(songs_path), "--private-dir", str(inside),
                                       "--out-dir", str(out_dir)]),
                           (run.main, ["--engine", "local", "--songs", str(EXPERIMENTS_DIR / "songs.jsonl"),
                                       "--out-dir", str(out_dir)]),
                           (dataset.main, ["--songs", str(songs_path), "--private-dir", str(inside)])):
            code, printed = self.quiet_main(main, argv)
            self.assertEqual(code, 2)
            self.assertIn("is inside the repository", printed)
        self.assertFalse(inside.exists())
        with self.assertRaises(PrivateDataError):
            outside_repo(REPO_ROOT / "backend" / "real-songs-dataset.jsonl")

    def test_an_engine_that_cannot_be_built_leaves_a_not_run_record_that_the_report_shows(self):
        out_dir = self.tmp / "out"
        with mock.patch.dict("os.environ", {"BASETEN_API_KEY": ""}):
            code, printed = self.quiet_main(run.main, ["--engine", "openweight", "--out-dir", str(out_dir)])
            self.assertEqual(code, 1)
            stub = json.loads((out_dir / "results-openweight.json").read_text(encoding="utf-8"))
            self.assertEqual((stub["engine"], stub["provider"], stub["not_run"]), (
                "openweight", "baseten", "BASETEN_API_KEY is not set, so provider baseten cannot be called"))
            # A results file with numbers is never replaced by a not-run record
            (out_dir / "results-real-songs-openweight.json").write_text('{"engine": "openweight"}', encoding="utf-8")
            self.quiet_main(run.main, ["--engine", "openweight", "--songs", str(self.write_songs()),
                                       "--out-dir", str(out_dir), "--private-dir", str(self.tmp / "private")])
        self.assertEqual(json.loads((out_dir / "results-real-songs-openweight.json").read_text(encoding="utf-8")),
                         {"engine": "openweight"})
        self.assertFalse((self.tmp / "private").exists())
        text = render({"openweight": stub})
        self.assertIn("- **openweight**: Muse Spark Open on Baseten, effort high, own ledger — not run: "
                      "BASETEN_API_KEY is not set, so provider baseten cannot be called", text)

    def test_report_puts_the_real_songs_first_with_their_size_and_source(self):
        songs, dropped, left_out = load_songs(self.write_songs())
        records = build_real_dataset(songs, total=4)
        facts = run.real_songs_facts(songs, dropped, left_out, records, 7)
        local, _ = run.run_real_songs(LocalEngine(), records, log=lambda *a, **k: None)
        engine = LLMEngine("meta", self.meta_client(FakeTransport()))
        meta, _ = run.run_real_songs(engine, records, log=lambda *a, **k: None)
        real_songs = {"local": {"engine": "local", "provider": "local", "model": "harmony_analysis",
                                "settings": LocalEngine().describe(), "dataset": facts, "real_songs": local},
                      "meta": {"engine": "meta", "provider": "meta", "model": "muse-spark-1.3",
                               "settings": engine.describe(), "dataset": facts, "real_songs": meta},
                      "openweight": {"engine": "openweight", "provider": "baseten", "model": "x",
                                     "not_run": "BASETEN_API_KEY is not set, so provider baseten cannot be called"}}
        synthetic = {"local": {"engine": "local", "provider": "local", "model": "harmony_analysis", "settings": {},
                               "dataset": {}, "synthetic": run.run_synthetic(LocalEngine(), self.records[:1],
                                                                             log=lambda *a, **k: None)}}
        text = render(synthetic, real_songs)
        self.assertLess(text.index("## Real songs"), text.index("## Results (synthetic scores)"))
        self.assertIn("Source: 3-song test split of the training corpora, private; excerpts realized with the "
                      "product's voicing code. N = 3 excerpts from 2 songs, 24 bars, 48 slots.", text)
        self.assertIn("bars left out of every excerpt: more_than_two_chords 1; songs dropped: meter 1", text)
        self.assertIn("| meta | 48 |", text)
        self.assertIn("- **meta**, real songs: exact", text)
        self.assertIn("### By genre (real songs, all slots)", text)
        self.assertIn("| jazz | local | 16 |", text)
        self.assertIn("— not run: BASETEN_API_KEY is not set", text)
        for song in SONGS:
            self.assertNotIn(song["title"], text)
            self.assertNotIn(song["id"], text)


if __name__ == "__main__":
    unittest.main()
