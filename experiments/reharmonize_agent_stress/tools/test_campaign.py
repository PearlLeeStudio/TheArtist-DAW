"""Offline checks of scheduling, budget isolation, and recorded evidence."""
import copy
import importlib.util
import json
from collections import Counter
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('campaign',HERE/'campaign.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CampaignChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design=c.validate_identity()
        cls.api=c.ev.load_backend(c.ROOT/'backend')
        cls.cases=c.read_json(c.OUT/'inputs.json')['cases']

    def test_disjoint_complete_worker_schedule(self):
        jobs=c.jobs(self.cases)
        left=c.assign_jobs(jobs,0)
        right=c.assign_jobs(jobs,1)
        self.assertEqual(set(j['id'] for j in left)|set(j['id'] for j in right),set(j['id'] for j in jobs))
        self.assertFalse(set(j['id'] for j in left)&set(j['id'] for j in right))
        self.assertEqual([sum(len(j['cases'])*j['repeats'] for j in group) for group in (left,right)],[2120,2120])
        for group in (left,right):
            self.assertEqual(Counter(case['request']['mode'] for j in group for case in j['cases'] if case['cohort']=='new'),{mode:40 for mode in c.MODES})

    def test_factorial_cells(self):
        for mode in c.MODES:
            rows=[r for r in self.cases if r['cohort']=='new' and r['request']['mode']==mode]
            cells=Counter((r['request']['key'].split()[1],r['complexity'],r['request']['maxChanges']) for r in rows)
            self.assertEqual(len(cells),16)
            self.assertEqual(set(cells.values()),{5})

    def test_all_inputs_schema_valid(self):
        for item in self.cases:
            req=self.api.Request.model_validate(item['request'])
            self.api.search.validate_context(req)

    def test_no_repeats_counted_as_new_inputs(self):
        self.assertEqual(len(self.cases),680)
        self.assertEqual(len({c['id'] for c in self.cases}),680)
        self.assertEqual(Counter(c['cohort'] for c in self.cases),{'new':640,'regression':40})
        self.assertEqual(sum(c.get('targetedPreviousTimeout',False) for c in self.cases),1)

    def test_mode_constraint_adds_a_real_failure(self):
        report=c.read_json(c.OLD/'open-a/results.json')
        old=next(r for r in report['runs'] if r['status']=='passed')
        request=copy.deepcopy(old['request'])
        response=old['response']
        passed_modes=[]
        for mode in c.MODES[1:]:
            request['mode']=mode
            result=c.audit(self.api,request,response,True,report['model'])
            passed_modes.append(result['checks']['explicitModeCompatible'])
        self.assertIn(False,passed_modes)

    def test_baseline_audit_preserved_in_auto(self):
        old_report=c.read_json(c.OLD/'open-a/results.json')
        run=old_report['runs'][0]
        audit=c.audit(self.api,run['request'],run['response'],True,old_report['model'])
        for key,value in run['audit']['checks'].items(): self.assertEqual(audit['checks'][key],value)
        self.assertTrue(audit['checks']['explicitModeCompatible'])

    def test_unknown_usage_remains_conservative(self):
        entry={'settled_usd':.033808,'usage':None,'status':'failed','reserved_usd':.033808}
        bill=c.ev.billing([entry])
        self.assertEqual(bill['returnedUsageCostUsd'],0)
        self.assertEqual(bill['unknownUsageReservationUsd'],.033808)
        self.assertEqual(bill['accountedCostUsd'],.033808)

    def test_worker_cap_allocation_bound(self):
        caps=self.design['plannedWorkerCapsUsd']
        self.assertEqual(sum(caps.values()),120)
        for worker_cap in caps.values():
            for consumed in (0,3.1,worker_cap-.1,worker_cap):
                allocation=round(min(6,worker_cap-consumed),8)
                self.assertLessEqual(consumed+allocation,worker_cap+1e-8)

    def test_per_run_reservation_cap(self):
        ledger=c.ev.make_ledger(self.api,c.OUT/'unused-test-ledger.json',6,[False])
        state={'spent_usd':.14,'entries':[]}
        with patch.object(ledger,'audit_state',return_value=state):
            with self.assertRaises(self.api.llm.BudgetExceeded):
                ledger.reserve(label='test',provider='meta',model='muse-spark-1.3',reserved_usd=.02)

    def test_stop_refuses_before_paid_reservation(self):
        ledger=c.ev.make_ledger(self.api,c.OUT/'unused-test-ledger.json',6,[True])
        with self.assertRaises(self.api.llm.LLMCancelled):
            ledger.reserve(label='test',provider='meta',model='muse-spark-1.3',reserved_usd=.01)
        self.assertFalse((c.OUT/'unused-test-ledger.json').exists())

    def test_provider_failures_stop_instead_of_passing_local(self):
        self.assertTrue(c.terminal_provider_error({'response':{'selection':'local','metaUnavailable':'paused'}}))
        self.assertTrue(c.terminal_provider_error({'httpAttempts':[{'error':{'statusCode':401}}]}))
        self.assertFalse(c.terminal_provider_error({'error':{'type':'LLMTimeout'}}))

    def test_summary_keeps_unstarted_in_denominator(self):
        summary=c.summarize([{'caseId':'x','repeat':1,'status':'not_started'}])
        self.assertEqual(summary['scheduledRuns'],1)
        self.assertEqual(summary['startedRuns'],0)
        self.assertEqual(summary['allScheduledRepeatsPassed'],0)
        self.assertEqual(summary['checksPassedOverAllScheduled']['explicitModeCompatible'],{'passed':0,'denominator':1})


if __name__=='__main__': unittest.main()
