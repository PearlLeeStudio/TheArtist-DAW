"""Continue only originally unstarted Meta rows after explicit user authorization.

The frozen campaign's run_job executes every call. Existing artifacts are read-only.
One continuation batch represents one original repeat; plan.json maps its rows back.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('saved_report', HERE / 'report.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
c = r.c
BASE = c.OUT
OUT = BASE / 'continuation'


def remaining_batches(cases, rows):
    original = {(x['caseId'], x['repeat']): x for x in rows}
    assert len(original) == len(rows), 'Duplicate original row'
    all_jobs = c.jobs(cases)
    ownership = {j['id']: worker for worker in (0, 1) for j in c.assign_jobs(all_jobs, worker)}
    batches = []
    covered = set()
    for job in all_jobs:
        for repeat in range(1, job['repeats'] + 1):
            ids = [case['id'] for case in job['cases'] if original[(case['id'], repeat)]['status'] == 'not_started']
            if not ids:
                continue
            batches.append({'id': job['id'] + '-r' + str(repeat), 'originalJobId': job['id'],
                            'originalRepeat': repeat, 'worker': ownership[job['id']], 'caseIds': ids})
            for case_id in ids:
                assert (case_id, repeat) not in covered
                covered.add((case_id, repeat))
    assert covered == {key for key, row in original.items() if row['status'] == 'not_started'}
    return batches


def remaining_caps(accounting, caps):
    result = {}
    for worker in (0, 1):
        name = 'meta-' + str(worker)
        used = accounting[name]['usedUsd']
        assert 0 <= used <= caps[name]
        result[name] = round(caps[name] - used, 8)
    return result


def build_plan():
    design = c.validate_identity()
    previous = c.read_json(BASE / 'summary.json')
    original = c.read_json(BASE / 'execution-plan.json')
    assert previous['unstartedRuns'] == 2524
    assert previous['arms']['baseten']['startedRuns'] == 4240
    assert previous['arms']['meta']['startedRuns'] == 1716
    assert previous['verification']['noOutstandingReservations']
    assert c.ev.file_hash(HERE / 'campaign.py') == original['runnerSha256']
    assert c.ev.file_hash(BASE / 'design.json') == original['designSha256']
    for artifact in previous['artifacts']:
        path = BASE / artifact['results']
        assert c.ev.file_hash(path) == artifact['resultsSha256']
        assert c.ev.file_hash(path.with_name('ledger.json')) == artifact['ledgerSha256']
    for provider in ('baseten', 'meta'):
        for worker in (0, 1):
            assert 'finished' in c.read_json(BASE / (provider + '-' + str(worker) + '-progress.json'))
    batches = remaining_batches(c.read_json(BASE / 'inputs.json')['cases'], previous['runs']['meta'])
    caps = remaining_caps(previous['workerAccounting'], original['workerCapsUsd'])
    assert sum(len(b['caseIds']) for b in batches) == 2524
    return {'protocol': 'reharmonize-agent-stress-v2-continuation',
            'authorization': 'The participant explicitly requested completing the remaining Spark 1.3 schedule after the operator stop. No further expansion is planned.',
            'previousDevelopmentCommit': 'eb5adc534e42d3b3c9fd68a8dc59eef492c76513',
            'previousSummarySha256': c.ev.file_hash(BASE / 'summary.json'),
            'previousReportSha256': c.ev.file_hash(BASE / 'summary.md'),
            'previousStopDecisionSha256': c.ev.file_hash(BASE / 'stop-decision.json'),
            'executionPlanSha256': c.ev.file_hash(BASE / 'execution-plan.json'),
            'inputsSha256': design['inputsSha256'], 'serviceSha256': design['serviceSha256'],
            'frozenRunnerSha256': original['runnerSha256'],
            'continuationRunnerSha256': c.ev.file_hash(Path(__file__).resolve()),
            'scheduledAdditionalRuns': 2524, 'originalScheduledRuns': 8480,
            'previousAccountedUsd': previous['accountedCostUsd'],
            'previousWorkerAccounting': previous['workerAccounting'],
            'remainingWorkerCapsUsd': caps, 'additionalCapUsd': round(sum(caps.values()), 8),
            'estimatedAdditionalUsd': round(previous['arms']['meta']['accountedCostUsd'] / 1716 * 2524, 2),
            'originalCombinedCapUsd': original['approvedMaxUsd'],
            'deadlineElapsedSeconds': 43200,
            'mapping': 'Each continuation batch runs repeats=1 in the unchanged runner; its raw repeat=1 maps to originalRepeat here. caseId and request are unchanged. Started failures and the prior cancellation are never scheduled again.',
            'jobs': batches}


def validate_plan():
    assert c.OUT == BASE
    plan = c.read_json(OUT / 'plan.json')
    assert plan == build_plan(), 'Continuation identity or original evidence changed'
    return plan


def job_for(batch, case_map):
    return {'id': batch['id'], 'repeats': 1, 'cases': [case_map[name] for name in batch['caseIds']]}


def worker(args):
    plan = validate_plan()
    name = 'meta-' + str(args.worker)
    with (OUT / (name + '.lock')).open('x') as claim:
        claim.write('One execution only; do not remove to restart.\n')
    api = c.ev.load_backend(c.ROOT / 'backend')
    assert not api.agent.meta_budget_unlimited()
    assert {k: getattr(api.agent, k) for k in ('MAX_USD', 'MAX_TURNS', 'MAX_TOOL_CALLS', 'MAX_SECONDS', 'MAX_COMPLETION_TOKENS')} == {
        'MAX_USD': .15, 'MAX_TURNS': 4, 'MAX_TOOL_CALLS': 6, 'MAX_SECONDS': 100, 'MAX_COMPLETION_TOKENS': 4096}
    case_map = {x['id']: x for x in c.read_json(BASE / 'inputs.json')['cases']}
    design = c.read_json(BASE / 'design.json')
    identity = {k: design[k] for k in ('inputsSha256', 'serviceSha256', 'checkpointSha256', 'frozenEvaluatorSha256')}
    identity['runnerSha256'] = plan['frozenRunnerSha256']
    batches = [b for b in plan['jobs'] if b['worker'] == args.worker]
    cap = plan['remainingWorkerCapsUsd'][name]
    stop = [False]
    def request_stop(signum, frame):
        stop[0] = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    deadline = time.monotonic() + args.remaining_seconds
    state = {'worker': name, 'capUsd': cap, 'completedJobs': [], 'accountedCostUsd': 0,
             'startedRuns': 0, 'passedRuns': 0, 'scheduledRuns': sum(len(b['caseIds']) for b in batches)}
    c.write_json(OUT / (name + '-progress.json'), state)
    # Only the evaluation output root changes. The frozen run_job and all product
    # code, requests, constraints, provider configuration and observations remain intact.
    c.OUT = OUT
    for batch in batches:
        if stop[0] or time.monotonic() >= deadline or cap - state['accountedCostUsd'] < .15:
            state['stoppedReason'] = 'Stop, deadline or insufficient remaining original worker budget'
            break
        allocated = round(min(6, cap - state['accountedCostUsd']), 8)
        report = c.run_job(api, job_for(batch, case_map), 'meta', allocated, stop, deadline, identity)
        state['accountedCostUsd'] = round(state['accountedCostUsd'] + report['ledgerTotals']['accountedCostUsd'], 8)
        state['startedRuns'] += report['summary']['startedRuns']
        state['passedRuns'] += report['summary']['passedRuns']
        state['completedJobs'].append({'id': batch['id'], 'allocatedCapUsd': allocated,
                                       'summary': report['summary'], 'stoppedReason': report.get('stoppedReason')})
        assert state['accountedCostUsd'] <= cap + 1e-8
        c.write_json(OUT / (name + '-progress.json'), state)
        print(json.dumps({k: state[k] for k in ('worker', 'startedRuns', 'passedRuns', 'accountedCostUsd')}), flush=True)
        if report.get('stoppedReason'):
            state['stoppedReason'] = report['stoppedReason']
            break
    state['finished'] = state['startedRuns'] == state['scheduledRuns'] and not state.get('stoppedReason')
    c.write_json(OUT / (name + '-progress.json'), state)
    return 0 if state['finished'] else 2


def launch():
    plan = validate_plan()
    with (OUT / 'launch.json').open('x') as claim:
        json.dump({'pid': os.getpid(), 'planSha256': c.ev.file_hash(OUT / 'plan.json')}, claim)
        claim.write('\n')
    children = []
    def request_stop(signum, frame):
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    began = time.monotonic()
    try:
        for shard in (0, 1):
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', '--worker', str(shard),
                                      '--remaining-seconds', str(plan['deadlineElapsedSeconds'] - (time.monotonic() - began))], env=os.environ.copy())
            children.append(child)
        print(json.dumps({'continuationStarted': True, 'pid': os.getpid(), 'workerPids': [p.pid for p in children],
                          'scheduledAdditionalRuns': 2524, 'additionalCapUsd': plan['additionalCapUsd']}), flush=True)
        while any(child.poll() is None for child in children):
            if time.monotonic() - began >= plan['deadlineElapsedSeconds'] or any(child.poll() not in (None, 0) for child in children):
                request_stop(None, None)
            time.sleep(5)
    finally:
        request_stop(None, None)
        for child in children:
            child.wait()
    outcome = {'finished': all(p.returncode == 0 for p in children), 'exitCodes': [p.returncode for p in children]}
    c.write_json(OUT / 'outcome.json', outcome)
    print(json.dumps(outcome), flush=True)
    return 0 if outcome['finished'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    sub.add_parser('run')
    work = sub.add_parser('worker')
    work.add_argument('--worker', type=int, choices=[0, 1], required=True)
    work.add_argument('--remaining-seconds', type=float, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        plan = build_plan()
        assert not (OUT / 'plan.json').exists()
        OUT.mkdir(exist_ok=True)
        c.write_json(OUT / 'plan.json', plan)
        print(json.dumps({k: plan[k] for k in ('scheduledAdditionalRuns', 'estimatedAdditionalUsd', 'additionalCapUsd', 'remainingWorkerCapsUsd')}))
        return 0
    return worker(args) if args.command == 'worker' else launch()


if __name__ == '__main__':
    raise SystemExit(main())
