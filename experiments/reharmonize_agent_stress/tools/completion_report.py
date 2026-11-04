"""Offline union of the preserved partial campaign and authorized unstarted rows."""
import argparse
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('continuation', HERE / 'continue_meta.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
c, r = m.c, m.r


def place_row(rows, batch, run, api, path):
    key = (run['caseId'], batch['originalRepeat'])
    old = rows[key]
    assert old['status'] == 'not_started', 'Never replace a started outcome'
    assert old['jobId'] == batch['originalJobId']
    assert run['caseId'] in batch['caseIds'] and run['repeat'] == 1
    if run['status'] == 'not_started':
        return
    item = {k: run[k] for k in ('caseId', 'cohort', 'status', 'elapsedSeconds', 'within100Seconds',
                              'billing', 'extraAttemptsWithinToolTurns', 'error') if k in run}
    item.update(repeat=batch['originalRepeat'], mode=old['mode'], jobId=old['jobId'],
                rawTrace=str(path.relative_to(m.BASE)), rawRepeat=1, continuationJobId=batch['id'],
                checks=run.get('audit', {}).get('checks', {}),
                threeSearchPatchesAvailable=old['threeSearchPatchesAvailable'],
                traceObservations=r.observe(api, run),
                requestIds=[e.get('request_id') for e in run['apiUsage']],
                httpErrors=[{'attempt': i + 1, **a['error']} for i, a in enumerate(run['httpAttempts']) if a.get('error')],
                modelApproximationCount=len(run.get('response', {}).get('modelApproximations', [])))
    rows[key] = item


def refresh_aggregates(output, case_map):
    rows = output['runs']
    arms = {p: r.arm_summary(v) for p, v in rows.items()}
    output.update(arms=arms, scheduledRuns=sum(a['scheduledRuns'] for a in arms.values()),
                  unstartedRuns=sum(a['scheduledRuns'] - a['startedRuns'] for a in arms.values()),
                  pairedStartedArms={p: r.arm_summary(v) for p, v in r.shared_started_rows(rows).items()},
                  inputCoverage={p: r.input_coverage(v, case_map) for p, v in rows.items()},
                  cohorts={name: {p: r.arm_summary([x for x in v if (x['cohort'] == 'regression' if name == 'regression'
                           else x['cohort'] == 'new' and x['mode'] == name)]) for p, v in rows.items()} for name in ['regression'] + c.MODES},
                  searchCapacityStrata={name: {p: r.arm_summary([x for x in v if x['threeSearchPatchesAvailable'] == flag])
                           for p, v in rows.items()} for name, flag in [('at_least_three', True), ('fewer_than_three', False)]},
                  repeatability={p: r.repeatability(v) for p, v in rows.items()},
                  accountedCostUsd=round(sum(a['accountedCostUsd'] for a in arms.values()), 8))
    output['failures'] = [{'provider': p, **x} for p, v in rows.items() for x in v if x['status'] not in ('passed', 'not_started')]
    output['failureCategories'] = dict(Counter((x.get('error') or {}).get('type', x['status']) for x in output['failures']))
    left = {(x['caseId'], x['repeat']): x for x in rows['baseten']}
    right = {(x['caseId'], x['repeat']): x for x in rows['meta']}
    assert left.keys() == right.keys()
    paired, overlap = Counter(), []
    for key, a in left.items():
        b = right[key]
        paired[f"open_{a['status']}__meta_{b['status']}"] += 1
        if a['status'] == b['status'] == 'passed':
            sa, sb = set(a['traceObservations']['musicalPatches']), set(b['traceObservations']['musicalPatches'])
            overlap.append({'caseId': key[0], 'repeat': key[1], 'sharedCandidates': len(sa & sb), 'jaccard': len(sa & sb) / len(sa | sb)})
    output.update(pairedOutcomes=dict(paired), pairedSuccessfulCandidateOverlap=overlap)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing', action='store_true')
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    plan = m.validate_plan()
    progress = {worker: c.read_json(m.OUT / ('meta-' + str(worker) + '-progress.json')) for worker in (0, 1)}
    assert all('finished' in p for p in progress.values()), 'Wait for both workers to exit'
    assert (m.OUT / 'outcome.json').is_file(), 'Wait for coordinator settlement'
    # Reproduce the already-published report, including all original raw audits.
    subprocess.run([sys.executable, str(HERE / 'report.py'), '--allow-incomplete', '--verify-existing'],
                   check=True, stdout=subprocess.DEVNULL)
    previous = c.read_json(m.BASE / 'summary.json')
    output = copy.deepcopy(previous)
    original_plan = c.read_json(m.BASE / 'execution-plan.json')
    design = c.read_json(m.BASE / 'design.json')
    case_map = {x['id']: x for x in c.read_json(m.BASE / 'inputs.json')['cases']}
    api = c.ev.load_backend(c.ROOT / 'backend')
    entries = {'baseten': [], 'meta': []}
    for artifact in previous['artifacts']:
        entries[artifact['provider']].extend(c.read_json((m.BASE / artifact['results']).with_name('ledger.json'))['entries'])
    rows = {(x['caseId'], x['repeat']): x for x in output['runs']['meta']}
    worker_used = {worker: 0 for worker in (0, 1)}
    worker_started = Counter()
    worker_passed = Counter()
    for batch in plan['jobs']:
        path = m.OUT / 'runs/meta' / batch['id'] / 'results.json.gz'
        if not path.exists():
            assert args.allow_incomplete, 'Missing continuation batch: ' + batch['id']
            continue
        report = r.verify_job(api, m.job_for(batch, case_map), path, original_plan, design)
        assert report['provider'] == 'meta'
        output['artifacts'].append({'provider': 'meta', 'jobId': batch['id'], 'originalJobId': batch['originalJobId'],
                                   'originalRepeat': batch['originalRepeat'], 'results': str(path.relative_to(m.BASE)),
                                   'resultsSha256': c.ev.file_hash(path), 'ledgerSha256': c.ev.file_hash(path.with_name('ledger.json')),
                                   'allocatedCapUsd': report['approvedMaxUsd'], 'stoppedReason': report.get('stoppedReason')})
        worker_used[batch['worker']] += report['ledgerTotals']['accountedCostUsd']
        worker_started[batch['worker']] += report['summary']['startedRuns']
        worker_passed[batch['worker']] += report['summary']['passedRuns']
        for run in report['runs']:
            place_row(rows, batch, run, api, path)
            entries['meta'].extend(run.get('apiUsage', []))
    output['runs']['meta'] = list(rows.values())
    assert output['runs']['baseten'] == previous['runs']['baseten']
    original_started = {(x['caseId'], x['repeat']): x for x in previous['runs']['meta'] if x['status'] != 'not_started'}
    assert all(rows[key] == value for key, value in original_started.items())
    for worker in (0, 1):
        name = 'meta-' + str(worker)
        used = round(worker_used[worker], 8)
        assert abs(used - progress[worker]['accountedCostUsd']) < 1e-7
        assert worker_started[worker] == progress[worker]['startedRuns']
        assert worker_passed[worker] == progress[worker]['passedRuns']
        assert used <= plan['remainingWorkerCapsUsd'][name] + 1e-8
        old_used = previous['workerAccounting'][name]['usedUsd']
        output['workerAccounting'][name].update(usedUsd=round(old_used + used, 8),
                                               previousUsedUsd=old_used, continuationUsedUsd=used)
        assert output['workerAccounting'][name]['usedUsd'] <= original_plan['workerCapsUsd'][name] + 1e-8
    refresh_aggregates(output, case_map)
    for provider, data in entries.items():
        billing = c.ev.billing(data)
        assert billing['outstandingUsd'] == 0
        assert abs(billing['accountedCostUsd'] - output['arms'][provider]['accountedCostUsd']) < 1e-7
        output['providerDetails'][provider] = {
            'tokens': {key: sum((e.get('usage') or {}).get(key, 0) for e in data) for key in ('prompt_tokens', 'cached_tokens', 'completion_tokens', 'reasoning_tokens')},
            'requestIdsRecorded': sum(bool(e.get('request_id')) for e in data),
            'requestIdsDistinct': len({e['request_id'] for e in data if e.get('request_id')}),
            'unknownRequestIds': sum(not e.get('request_id') for e in data), 'billing': billing}
    assert output['scheduledRuns'] == 8480
    assert output['accountedCostUsd'] <= output['approvedMaxUsd'] == 120
    if not args.allow_incomplete:
        assert output['unstartedRuns'] == 0
        assert all(p['finished'] for p in progress.values())
    output['earlierStopDecision'] = output.pop('stopDecision')
    output['earlierStopDecisionSha256'] = output.pop('stopDecisionSha256')
    output['stopDecision'] = ({'reason': 'Continuation ended before all original rows started. Worker reasons: ' +
                                        json.dumps({str(k): v.get('stoppedReason') for k, v in progress.items()}),
                               'decisionTiming': 'This is not a statistical stopping rule.'} if output['unstartedRuns'] else None)
    output['continuation'] = {'planSha256': c.ev.file_hash(m.OUT / 'plan.json'),
                              'previousSummarySha256': plan['previousSummarySha256'],
                              'additionalStartedRuns': sum(worker_started.values()),
                              'additionalAccountedUsd': round(sum(worker_used.values()), 8),
                              'originalStartedRowsPreserved': True, 'originalRepeatMappingVerified': True}
    output['limitations'].append('A user-authorized continuation followed an operator stop; the temporal break and smaller accounting batches can affect timing and provider caching.')
    text = r.render(output)
    text = text.replace('**Partial campaign, deliberately ended after scope review.**', '**Incomplete continuation.**')
    text = text.replace('[Stop decision](stop-decision.json).', '[Continuation outcome](continuation/outcome.json).')
    note = ('The participant explicitly requested finishing the original Spark 1.3 schedule after the operator stop. '
            'Only originally unstarted rows were scheduled; the earlier failure and cancellation records are unchanged. '
            'The [partial report](summary.md), [earlier stop decision](stop-decision.json) and '
            '[continuation plan and row mapping](continuation/README.md) remain available. '
            'The temporal break and smaller accounting batches limit comparisons of timing and caching.\n\n')
    text = text.replace('\n\n', '\n\n' + note, 1)
    output_path = m.BASE / 'completion-summary.json'
    text_path = m.BASE / 'completion-summary.md'
    if args.verify_existing:
        assert c.read_json(output_path) == output
        assert text_path.read_text() == text
    else:
        assert not output_path.exists() and not text_path.exists(), 'Never overwrite an existing report'
        c.write_json(output_path, output)
        text_path.write_text(text)
    print(json.dumps({'verified': True, 'networkCalls': 0, 'scheduledRuns': output['scheduledRuns'],
                      'unstartedRuns': output['unstartedRuns'], 'arms': output['arms'],
                      'accountedCostUsd': output['accountedCostUsd']}, indent=2))


if __name__ == '__main__':
    main()
