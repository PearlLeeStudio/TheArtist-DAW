"""Statistical and deduplication checks for recommendation-position analysis."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('rank_reharmonization', Path(__file__).resolve().parents[2] / 'agent' / 'rank_reharmonization.py')
ranks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ranks)


def fixture():
    versions = [['F', 'C'], ['G', 'C'], ['Dm', 'C']]
    ratings = [{'id': str(i), **{k: value for k in ranks.RUBRIC}} for i, value in enumerate((1, 2, 4))]
    judge = {'status': 'ok', 'mapping': {str(i): version for i, version in enumerate(versions)},
             'response': {'data': {'ratings': ratings}}}
    return {'id': 'one', 'tuneGroup': 'tune', 'pool': [{'id': str(i)} for i in range(3)],
            'original': ['C', 'C'], 'request': {}, 'judges': [judge, copy.deepcopy(judge)],
            'arms': {arm: {'status': 'ok', 'candidates': [{'chords': version} for version in versions]} for arm in ranks.ARMS}}


class RankTests(unittest.TestCase):
    def test_model_comparison_preserves_problem_and_compares_first_two(self):
        old, new = fixture(), fixture()
        old['request']['modelKey'] = 'ft_f2'
        new['request']['modelKey'] = 'ft_f3'
        for arm in ranks.ARMS:
            new['arms'][arm]['candidates'].reverse()
        result = ranks.compare_models({'datasetSha256': 'same', 'cases': [old]}, {'datasetSha256': 'same', 'cases': [new]})
        self.assertEqual(result['modelDifferences']['local']['top2Mean']['mean'], -1.5)
        self.assertEqual(result['modelDifferences']['local']['top3Mean']['mean'], 0)
        self.assertNotIn('combined', result)  # Different models must not become pooled replicates.
        new['pool'].append({'id': 'not-the-same-math-pool'})
        with self.assertRaisesRegex(ValueError, 'preserve musical inputs'):
            ranks.compare_models({'datasetSha256': 'same', 'cases': [old]}, {'datasetSha256': 'same', 'cases': [new]})

    def test_recommendation_order_is_not_replaced_by_judge_order(self):
        row = ranks.extract(fixture(), 'original')
        self.assertEqual(row['arms']['local']['ranks'], [1, 2, 4])
        self.assertEqual(row['arms']['local']['gap12'], -1)
        self.assertEqual(row['arms']['local']['gap23'], -2)
        self.assertEqual(row['arms']['local']['oracleLossTop2'], 2)

    def test_eight_positions_deduplicate_and_other_arm_can_rescue_a_third_choice(self):
        case = fixture()
        before = ranks.extract(case, 'original')['union']
        self.assertEqual((before['uniqueTop2'], before['uniqueTop3'], before['oracleLoss']), (2, 3, 2))
        case['arms']['meta']['candidates'] = case['arms']['meta']['candidates'][1:] + case['arms']['meta']['candidates'][:1]
        after = ranks.extract(case, 'original')['union']
        self.assertEqual((after['uniqueTop2'], after['uniqueTop3'], after['oracleLoss']), (3, 3, 0))

    def test_repeated_passages_do_not_outvote_a_tune_with_fewer_windows(self):
        rows = [{'id': str(i), 'tuneGroup': 'many', 'value': 2} for i in range(9)] * 2
        rows += [{'id': 'single', 'tuneGroup': 'few', 'value': -2}] * 2
        stats = ranks.balanced(rows, lambda r: r['value'])
        self.assertEqual((stats['caseRuns'], stats['passages'], stats['tunes']), (20, 10, 2))
        self.assertEqual(stats['mean'], 0)
        self.assertEqual(stats['interval95'], [-2, 2])

    def test_stability_distinguishes_reordering_from_new_musical_alternatives(self):
        old, new = fixture(), fixture()
        new['arms']['local']['candidates'][:2] = reversed(new['arms']['local']['candidates'][:2])
        result = ranks.stability({'cases': [old]}, {'cases': [new]})
        local = result['arms']['local']
        self.assertEqual(local['sameFirst']['mean'], 0)
        self.assertEqual(local['sameTop2Set']['mean'], 1)
        self.assertEqual(local['top2Overlap']['mean'], 1)
        self.assertEqual(local['sameOrdered3']['mean'], 0)
        new['pool'].append({'id': 'changed'})
        with self.assertRaisesRegex(ValueError, 'Pool/input changed'):
            ranks.stability({'cases': [old]}, {'cases': [new]})

    def test_failed_repeat_judge_is_excluded_from_paired_aggregate(self):
        old = ranks.extract(fixture(), 'original')
        new = fixture(); new['judges'][1] = {'status': 'failed'}
        result = ranks.aggregate([old, ranks.extract(new, 'repeat')], require_batches=2)
        self.assertEqual(result['arms']['meta']['gap12']['passages'], 0)
        self.assertEqual(result['union']['oracleLoss']['caseRuns'], 0)
