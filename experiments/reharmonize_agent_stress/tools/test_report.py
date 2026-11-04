"""Offline tests for denominators and repeatability, without provider calls."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('report',HERE/'report.py')
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def row(case,repeat,status,patches=()):
    result={'caseId':case,'repeat':repeat,'status':status,'traceObservations':{'musicalPatches':list(patches)}}
    if status!='not_started': result['elapsedSeconds']=repeat
    return result


class ReportChecks(unittest.TestCase):
    def test_failed_repeat_prevents_stability_claim(self):
        data=[row('x',1,'passed',['a','b','c']),row('x',2,'failed')]
        result=r.repeatability(data)
        self.assertEqual(result['allScheduledRepeatsPassed'],0)
        self.assertEqual(result['sameOfferEveryScheduledRepeat'],0)
        self.assertIsNone(result['meanPassageJaccardWhereTwoSuccesses'])

    def test_jaccard_compares_sets_not_rank(self):
        data=[row('x',1,'passed',['a','b','c']),row('x',2,'passed',['c','b','a'])]
        result=r.repeatability(data)
        self.assertEqual(result['sameOfferEveryScheduledRepeat'],1)
        self.assertEqual(result['meanPassageJaccardWhereTwoSuccesses'],1)

    def test_one_shared_candidate_has_one_fifth_overlap(self):
        data=[row('x',1,'passed',['a','b','c']),row('x',2,'passed',['a','d','e'])]
        result=r.repeatability(data)
        self.assertEqual(result['sameOfferEveryScheduledRepeat'],0)
        self.assertAlmostEqual(result['meanPassageJaccardWhereTwoSuccesses'],.2)

    def test_passage_balancing(self):
        data=[row('x',i,'passed',['a','b','c']) for i in range(10)]
        data += [row('y',1,'passed',['d','e','f']),row('y',2,'passed',['g','h','i'])]
        result=r.repeatability(data)
        self.assertEqual(result['passages'],2)
        self.assertEqual(result['meanPassageJaccardWhereTwoSuccesses'],.5)

    def test_failure_and_unstarted_stay_in_full_denominator(self):
        data=[row('x',1,'passed'),row('x',2,'failed'),row('x',3,'not_started')]
        result=r.arm_summary(data)
        self.assertEqual(result['scheduledRuns'],3)
        self.assertEqual(result['startedRuns'],2)
        self.assertEqual(result['passedRuns'],1)
        self.assertEqual(result['latencySecondsAllStarted']['n'],2)
        self.assertEqual(result['checks']['threeCandidates']['denominator'],3)

    def test_saved_trace_feedback_matches_actual_candidates(self):
        api=r.c.ev.load_backend(r.c.ROOT/'backend')
        report=r.c.read_json(r.c.OLD/'open-a/results.json')
        observation=r.observe(api,report['runs'][0])
        self.assertTrue(observation['completeOfferBackedBySearch'])
        self.assertEqual(observation['finiteF1Scores'],3)
        self.assertEqual(len(observation['musicalPatches']),3)


if __name__=='__main__': unittest.main()
