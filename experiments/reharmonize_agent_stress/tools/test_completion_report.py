"""Offline continuation merge checks; no provider calls."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('completion', Path(__file__).with_name('completion_report.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MergeChecks(unittest.TestCase):
    def setUp(self):
        self.batch = {'id': 'original-r4', 'originalJobId': 'original', 'originalRepeat': 4, 'caseIds': ['x']}
        self.old = {'caseId': 'x', 'repeat': 4, 'cohort': 'new', 'jobId': 'original', 'mode': 'auto',
                    'threeSearchPatchesAvailable': True, 'status': 'not_started'}
        self.run = {'caseId': 'x', 'repeat': 1, 'cohort': 'new', 'status': 'failed', 'elapsedSeconds': 2,
                    'within100Seconds': True, 'billing': {}, 'apiUsage': [], 'httpAttempts': [],
                    'error': {'type': 'LLMTimeout'}}
        self.path = m.m.OUT / 'runs/meta/original-r4/results.json.gz'

    def test_restores_original_repeat_and_preserves_failure(self):
        rows = {('x', 4): copy.deepcopy(self.old)}
        with patch.object(m.r, 'observe', return_value={}):
            m.place_row(rows, self.batch, self.run, None, self.path)
        self.assertEqual(rows[('x', 4)]['repeat'], 4)
        self.assertEqual(rows[('x', 4)]['rawRepeat'], 1)
        self.assertEqual(rows[('x', 4)]['status'], 'failed')
        self.assertEqual(rows[('x', 4)]['error']['type'], 'LLMTimeout')

    def test_cannot_overwrite_any_started_result(self):
        for status in ('passed', 'failed', 'cancelled', 'failed_checks', 'local_selection'):
            rows = {('x', 4): {**self.old, 'status': status}}
            with self.assertRaises(AssertionError):
                m.place_row(rows, self.batch, self.run, None, self.path)

    def test_duplicate_continuation_is_rejected(self):
        rows = {('x', 4): copy.deepcopy(self.old)}
        with patch.object(m.r, 'observe', return_value={}):
            m.place_row(rows, self.batch, self.run, None, self.path)
            with self.assertRaises(AssertionError):
                m.place_row(rows, self.batch, self.run, None, self.path)

    def test_unstarted_does_not_become_failure_or_overwrite_trace(self):
        rows = {('x', 4): copy.deepcopy(self.old)}
        m.place_row(rows, self.batch, {**self.run, 'status': 'not_started'}, None, self.path)
        self.assertEqual(rows[('x', 4)], self.old)

    def test_wrong_job_and_raw_repeat_are_rejected(self):
        rows = {('x', 4): copy.deepcopy(self.old)}
        with self.assertRaises(AssertionError):
            m.place_row(rows, {**self.batch, 'originalJobId': 'wrong'}, self.run, None, self.path)
        with self.assertRaises(AssertionError):
            m.place_row(rows, self.batch, {**self.run, 'repeat': 4}, None, self.path)

    def test_aggregate_without_new_rows_reproduces_original_metrics(self):
        previous = m.c.read_json(m.m.BASE / 'summary.json')
        result = copy.deepcopy(previous)
        cases = {x['id']: x for x in m.c.read_json(m.m.BASE / 'inputs.json')['cases']}
        m.refresh_aggregates(result, cases)
        for name in ('arms', 'scheduledRuns', 'unstartedRuns', 'pairedStartedArms', 'inputCoverage',
                     'cohorts', 'searchCapacityStrata', 'repeatability', 'accountedCostUsd', 'failures',
                     'failureCategories', 'pairedOutcomes', 'pairedSuccessfulCandidateOverlap'):
            self.assertEqual(result[name], previous[name], name)


if __name__ == '__main__':
    unittest.main()
