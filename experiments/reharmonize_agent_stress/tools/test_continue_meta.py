"""Offline guards against paid duplication, lost failures and budget resets."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('continuation', Path(__file__).with_name('continue_meta.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ContinuationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = m.c.read_json(m.BASE / 'inputs.json')['cases']
        cls.saved = m.c.read_json(m.BASE / 'summary.json')
        cls.rows = cls.saved['runs']['meta']

    def test_exact_unstarted_set_and_no_duplicate(self):
        batches = m.remaining_batches(self.cases, self.rows)
        keys = [(cid, b['originalRepeat']) for b in batches for cid in b['caseIds']]
        expected = {(x['caseId'], x['repeat']) for x in self.rows if x['status'] == 'not_started'}
        self.assertEqual(len(keys), 2524)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), expected)

    def test_failed_and_cancelled_are_never_replaced(self):
        batches = m.remaining_batches(self.cases, self.rows)
        keys = {(cid, b['originalRepeat']) for b in batches for cid in b['caseIds']}
        preserved = {(x['caseId'], x['repeat']) for x in self.rows if x['status'] in ('failed', 'cancelled')}
        self.assertEqual(len(preserved), 43)
        self.assertTrue(keys.isdisjoint(preserved))

    def test_existing_worker_ownership_and_counts(self):
        batches = m.remaining_batches(self.cases, self.rows)
        for worker, expected in ((0, 1265), (1, 1259)):
            names = {j['id'] for j in m.c.assign_jobs(m.c.jobs(self.cases), worker)}
            selected = [b for b in batches if b['worker'] == worker]
            self.assertTrue(all(b['originalJobId'] in names for b in selected))
            self.assertEqual(sum(len(b['caseIds']) for b in selected), expected)

    def test_no_original_row_mutation_and_exact_requests(self):
        before = copy.deepcopy(self.rows)
        case_map = {x['id']: x for x in self.cases}
        for batch in m.remaining_batches(self.cases, self.rows):
            job = m.job_for(batch, case_map)
            self.assertEqual(job['repeats'], 1)
            self.assertLessEqual(len(job['cases']), 20)
            for case in job['cases']:
                self.assertEqual(case['request'], case_map[case['id']]['request'])
        self.assertEqual(self.rows, before)

    def test_spent_budget_is_deducted(self):
        caps = m.remaining_caps(self.saved['workerAccounting'], {'meta-0': 40, 'meta-1': 40})
        self.assertEqual(caps, {'meta-0': 29.60513855, 'meta-1': 29.66437645})
        self.assertAlmostEqual(sum(caps.values()), 59.269515)
        self.assertLessEqual(self.saved['accountedCostUsd'] + sum(caps.values()), 120)

    def test_duplicate_source_rows_and_overspent_budget_rejected(self):
        with self.assertRaises(AssertionError):
            m.remaining_batches(self.cases, self.rows + [self.rows[0]])
        bad = copy.deepcopy(self.saved['workerAccounting'])
        bad['meta-0']['usedUsd'] = 40.01
        with self.assertRaises(AssertionError):
            m.remaining_caps(bad, {'meta-0': 40, 'meta-1': 40})


if __name__ == '__main__':
    unittest.main()
