import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent.listening_results import RATINGS, summarize


class ListeningResultsTests(unittest.TestCase):
    def setUp(self):
        self.key = {"first": dict(pair="p", arm="reuse"), "second": dict(pair="p", arm="new")}
        self.response = dict(version=1, participant="listener", responses=[dict(pair="p", preference="B",
            variants=[dict(id="first", label="B", listenedToEnd=True, ratings={k: 5 for k in RATINGS}),
                      dict(id="second", label="A", listenedToEnd=False, ratings={k: 2 for k in RATINGS})])])

    def test_unblinds_by_id_and_label_not_array_order(self):
        result = summarize([self.response], self.key)
        self.assertEqual(result["preferences"], {"reuse": 1})
        self.assertEqual(result["clipsNotPlayedToEnd"], 1)
        self.assertEqual(result["ratings"]["reuse/Flow"]["mean"], 5)

    def test_rejects_duplicate_listener_or_forged_clip(self):
        with self.assertRaises(ValueError):
            summarize([self.response, self.response], self.key)
        invalid = copy.deepcopy(self.response)
        invalid["responses"][0]["variants"][0]["id"] = "unrelated"
        with self.assertRaises(ValueError):
            summarize([invalid], self.key)

    def test_rejects_missing_or_boolean_ratings(self):
        for value in (None, True, 6):
            invalid = copy.deepcopy(self.response)
            invalid["responses"][0]["variants"][0]["ratings"]["Flow"] = value
            with self.assertRaises(ValueError):
                summarize([invalid], self.key)
