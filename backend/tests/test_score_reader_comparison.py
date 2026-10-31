"""Reference scoring never treats a failed read or empty proposal as accurate."""
import importlib.util
from pathlib import Path
import sys
import unittest

from tests.test_score_verification import reading


class ReaderComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(__file__).resolve().parents[2] / "agent"
        sys.path.insert(0, str(directory))
        spec = importlib.util.spec_from_file_location("compare_score_readers", directory / "compare_score_readers.py")
        cls.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.runner)

    def test_failure_remains_in_every_reference_denominator(self):
        reference = {"bars": 1, "key": "C major", "meter": [4, 4], "chords": [["C"]], "notes": [[0, 4, 7]]}
        result = self.runner.metrics(None, reference)
        self.assertFalse(result["completed"])
        self.assertFalse(result["barCountMatches"])
        self.assertFalse(result["chordBars"][0]["match"])
        self.assertFalse(result["noteBars"][0]["match"])
        self.assertEqual(result["missingBars"], 1)

    def test_two_source_changes_are_not_credited_as_one_chord(self):
        reference = {"bars": 1, "key": "C major", "meter": [4, 4], "chords": [["C", "G7"]]}
        result = self.runner.metrics(reading(chords=["C"]), reference)
        self.assertFalse(result["chordBars"][0]["match"])

    def test_ambiguous_melody_gets_no_fabricated_exact_harmony_target(self):
        reference = {"bars": 1, "key": None, "meter": [4, 4], "chords": [None],
                     "notes": [[2]], "ambiguousTargets": [0]}
        result = self.runner.metrics(reading(chords=["Dm"], notes=["D4"]), reference)
        self.assertEqual(result["chordBars"], [])
        self.assertTrue(result["noteBars"][0]["match"])
        self.assertEqual(result["ambiguousProposals"][0]["chords"], ["Dm"])
