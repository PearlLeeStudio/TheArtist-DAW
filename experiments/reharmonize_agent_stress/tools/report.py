"""Verify saved traces and create a separate report; never call a provider."""
import argparse
from collections import Counter,defaultdict
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('campaign',HERE/'campaign.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def percentile(values,q):
    values=sorted(values)
    return values[max(0,math.ceil(len(values)*q)-1)] if values else None


def musical_patch(api,candidate):
    return c.ev.canonical(sorted([change['address']['measureIndex'],change['address']['slotIndex'],
        api.search.chord(change['after'])[0],sorted(api.search.chord(change['after'])[1]),api.search.chord(change['after'])[2]]
        for change in candidate['changes']))


def observe(api,run):
    pools={}
    calls=Counter()
    families=Counter()
    for turn in run.get('turns',[]):
        for call in turn.get('reply',{}).get('data',{}).get('calls',[]):
            calls[call['name']]+=1
            if call['name']=='search_substitutions':
                families[' + '.join(sorted(call.get('arguments',{}).get('families',[])))]+=1
        for msg in turn.get('messages',[]):
            if msg.get('role')!='tool': continue
            body=json.loads(msg['content'])
            if isinstance(body,dict) and isinstance(body.get('candidates'),list):
                pools[msg['tool_call_id']]=body['candidates']
    feedback={c.ev.canonical(item) for pool in pools.values() for item in pool}
    pool={item['id']:item for candidates in pools.values() for item in candidates}
    candidates=run.get('response',{}).get('candidates',[])
    scores=[item['modelScore'] for item in pool.values() if isinstance(item.get('modelScore'),(int,float)) and math.isfinite(item['modelScore'])]
    ranks=[1+sum(score>item['modelScore'] for score in scores) for item in candidates
           if isinstance(item.get('modelScore'),(int,float)) and math.isfinite(item['modelScore'])]
    return {'searchFeedbackPresent':bool(feedback),'completeOfferBackedBySearch':bool(candidates) and all(c.ev.canonical(item) in feedback for item in candidates),
            'offeredCandidates':len(candidates),'finiteF1Scores':len(ranks),'offeredF1RanksWithinObservedPool':ranks,
            'offeredFamilies':dict(Counter(item['family'] for item in candidates)),
            'modelRequestedCalls':dict(calls),'requestedFamilySets':dict(families),
            'musicalPatches':sorted({musical_patch(api,item) for item in candidates})}


def verify_job(api,job,path,plan,design):
    report=c.read_json(path)
    provider=report['provider']
    assert report['jobId']==job['id'] and report['model']==c.ev.MODELS[provider]
    assert report['reasoningEffort']=='low'
    assert report['identity']=={**{k:design[k] for k in ('inputsSha256','serviceSha256','checkpointSha256','frozenEvaluatorSha256')},'runnerSha256':plan['runnerSha256']}
    expected=[(case['id'],case['cohort'],repeat,case['request']) for repeat in range(1,job['repeats']+1) for case in job['cases']]
    assert [(r['caseId'],r['cohort'],r['repeat'],r['request']) for r in report['runs']]==expected
    assert report['summary']==c.summarize(report['runs'])
    ledger=c.read_json(path.with_name('ledger.json'))
    entries=[entry for run in report['runs'] for entry in run.get('apiUsage',[])]
    assert entries==ledger['entries']
    assert c.ev.billing(entries)==report['ledgerTotals']
    assert report['ledgerTotals']['outstandingUsd']==0
    assert report['ledgerTotals']['accountedCostUsd']<=report['approvedMaxUsd']<=6
    for run in report['runs']:
        if run['status']=='not_started': continue
        assert run['billing']==c.ev.billing(run['apiUsage'])
        assert run['billing']['accountedCostUsd']<=.15+1e-8
        assert all('ts' not in entry for entry in run['apiUsage'])
        assert len(run['httpAttempts'])==len(run['apiUsage']), 'Transport/reservation discrepancy must be reviewed explicitly'
        if 'response' in run:
            assert 'audit' in run or run['status']=='failed'
            if 'audit' in run:
                assert c.audit(api,run['request'],run['response'],run['audit']['checks']['inputUnchanged'],report['model'])==run['audit']
                assert (run['status']=='passed')==run['audit']['passed']
            req=api.Request.model_validate(run['request'])
            assert run['response']['contextMeasures']==[bar.measure for bar in api.search.context_window(req)]
        else: assert run['status']!='passed'
    prices=report['pricesPerMillion']
    measured=sum(((e['usage']['prompt_tokens']-e['usage']['cached_tokens'])*prices['input']+e['usage']['cached_tokens']*prices['cached']+e['usage']['completion_tokens']*prices['output'])/1e6 for e in entries if e.get('usage'))
    assert abs(measured-report['ledgerTotals']['returnedUsageCostUsd'])<1e-7
    body=json.dumps(report)
    for key in ('MODEL_API_KEY','BASETEN_API_KEY'):
        assert not os.environ.get(key) or os.environ[key] not in body
    return report


def repeatability(rows):
    groups=defaultdict(list)
    for r in rows: groups[r['caseId']].append(r)
    output=[]
    for case_id,runs in sorted(groups.items()):
        successful=[r for r in runs if r['status']=='passed']
        sets=[set(r['traceObservations']['musicalPatches']) for r in successful]
        overlaps=[len(a&b)/len(a|b) for a,b in itertools.combinations(sets,2) if a|b]
        versions={tuple(sorted(s)) for s in sets}
        output.append({'caseId':case_id,'scheduledRepeats':len(runs),'passedRepeats':len(successful),
                       'allRepeatsPassed':len(successful)==len(runs),'distinctSuccessfulOfferSets':len(versions),
                       'sameOfferEveryScheduledRepeat':len(successful)==len(runs) and len(versions)==1,
                       'meanSuccessfulPairJaccard':statistics.mean(overlaps) if overlaps else None})
    return {'passages':len(groups),'allScheduledRepeatsPassed':sum(r['allRepeatsPassed'] for r in output),
            'sameOfferEveryScheduledRepeat':sum(r['sameOfferEveryScheduledRepeat'] for r in output),
            'meanPassageJaccardWhereTwoSuccesses':statistics.mean(r['meanSuccessfulPairJaccard'] for r in output if r['meanSuccessfulPairJaccard'] is not None)
                if any(r['meanSuccessfulPairJaccard'] is not None for r in output) else None,'cases':output}


def arm_summary(rows):
    started=[r for r in rows if r['status']!='not_started']
    elapsed=[r['elapsedSeconds'] for r in started]
    return {'scheduledRuns':len(rows),'startedRuns':len(started),'passedRuns':sum(r['status']=='passed' for r in rows),
            'statusCounts':dict(Counter(r['status'] for r in rows)),
            'latencySecondsAllStarted':{'n':len(elapsed),'p50':percentile(elapsed,.5),'p95':percentile(elapsed,.95),'p99':percentile(elapsed,.99),'maximum':max(elapsed,default=None)},
            'checks':{name:{'passed':sum(r.get('checks',{}).get(name,False) for r in rows),'denominator':len(rows)} for name in (*c.ev.AUDIT_CHECKS,'explicitModeCompatible')},
            'accountedCostUsd':round(sum(r.get('billing',{}).get('accountedCostUsd',0) for r in rows),8),
            'returnedUsageCostUsd':round(sum(r.get('billing',{}).get('returnedUsageCostUsd',0) for r in rows),8),
            'unknownUsageReservationUsd':round(sum(r.get('billing',{}).get('unknownUsageReservationUsd',0) for r in rows),8),
            'httpAttempts':sum(r.get('billing',{}).get('attempts',0) for r in rows),
            'extraAttemptsWithinToolTurns':sum(r.get('extraAttemptsWithinToolTurns',0) for r in rows),
            'offeredCandidates':sum(r.get('traceObservations',{}).get('offeredCandidates',0) for r in rows),
            'offeredCandidatesWithFiniteF1Scores':sum(r.get('traceObservations',{}).get('finiteF1Scores',0) for r in rows),
            'runsWhoseEntireOfferMatchesSavedSearchFeedback':sum(r.get('traceObservations',{}).get('completeOfferBackedBySearch',False) for r in rows)}


def shared_started_rows(rows):
    keys=[{(r['caseId'],r['repeat']) for r in runs if r['status']!='not_started'} for runs in rows.values()]
    common=set.intersection(*keys) if keys else set()
    return {provider:[r for r in runs if (r['caseId'],r['repeat']) in common] for provider,runs in rows.items()}


def input_coverage(rows,case_map):
    counts=Counter(r['caseId'] for r in rows if r['status']!='not_started')
    def cell(case):
        req=case['request']
        return req.get('mode','auto'),req['key'].split()[-1],case['complexity'],req['maxChanges']
    cells=Counter(cell(case_map[cid]) for cid in counts if case_map[cid]['cohort']=='new')
    repeated=Counter(cell(case_map[cid]) for cid,n in counts.items() if n>=2 and case_map[cid]['cohort']=='new')
    return {'distinctStartedInputs':len(counts),'inputsWithAtLeastTwoStartedRuns':sum(n>=2 for n in counts.values()),
            'plannedConditionCells':len({cell(case) for case in case_map.values() if case['cohort']=='new'}),
            'observedConditionCells':len(cells),'conditionCellsWithTwoInputs':sum(n>=2 for n in cells.values()),
            'conditionCellsWithTwoRepeatedInputs':sum(n>=2 for n in repeated.values())}


def render(report):
    arms=report['arms']
    lines=['# Expanded Reharmonize product-agent results','',
        '**Scope: existing product tool loop, real F1 weights and actual provider calls. Product code, UX, prompts and runtime configuration were unchanged.**','',
        f"Frozen schedule: 640 new authored passages × 6 repeats and 40 existing regression passages × 10 repeats, per provider. {report['scheduledRuns']:,} total scheduled executions. Repeats are not new songs. The original 880-run campaign remains separate.",'']
    if report['stopDecision']:
        lines += ['**Partial campaign, deliberately ended after scope review.** '+report['stopDecision']['reason']+' '+report['stopDecision']['decisionTiming'],
                  '',f"**{report['unstartedRuns']:,} planned executions were not started.** They remain in the original schedule and are not counted as model failures. The unequal full-arm totals below are not a head-to-head success-rate comparison. [Stop decision](stop-decision.json).",'']
    lines += [
        '| Measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |','|---|---:|---:|']
    for label,fn in [
        ('Passed / scheduled',lambda a:f"{a['passedRuns']:,} / {a['scheduledRuns']:,}"),
        ('Started',lambda a:f"{a['startedRuns']:,}"),
        ('Passed / started',lambda a:f"{a['passedRuns']:,} / {a['startedRuns']:,}"),
        ('Not started',lambda a:f"{a['scheduledRuns']-a['startedRuns']:,}"),
        ('HTTP attempts / extra attempts',lambda a:f"{a['httpAttempts']:,} / {a['extraAttemptsWithinToolTurns']:,}"),
        ('p50 / p95 / p99 seconds',lambda a:' / '.join(str(a['latencySecondsAllStarted'][q]) for q in ('p50','p95','p99'))),
        ('Configured-price estimate from returned usage',lambda a:f"${a['returnedUsageCostUsd']:.8f}"),
        ('Unknown-usage reservation',lambda a:f"${a['unknownUsageReservationUsd']:.8f}"),
        ('Offers backed by saved tool feedback',lambda a:f"{a['runsWhoseEntireOfferMatchesSavedSearchFeedback']:,}"),
        ('Offered candidates / finite F1 scores',lambda a:f"{a['offeredCandidates']:,} / {a['offeredCandidatesWithFiniteF1Scores']:,}")]:
        lines.append('| '+label+' | '+' | '.join(fn(arms[p]) if p in arms else 'Not scheduled' for p in ('baseten','meta'))+' |')
    lines += ['','## Comparable started rows and input coverage','',
              'The following subset retains every outcome for each case/repeat row started by both providers, including failures and operator cancellations. It is selected by execution status, not by success. It remains a partial, non-random prefix of the frozen schedule; it is not evidence of musical superiority.','',
              '| Shared case/repeat rows | Open | Spark 1.3 |','|---|---:|---:|']
    for label,field in [('Started on both providers','startedRuns'),('Passed','passedRuns')]:
        lines.append('| '+label+' | '+' | '.join(str(report['pairedStartedArms'][p][field]) for p in ('baseten','meta'))+' |')
    lines += ['','| Coverage of authored inputs | Open | Spark 1.3 |','|---|---:|---:|']
    for label,field in [('Distinct started inputs','distinctStartedInputs'),('Inputs with at least two started runs','inputsWithAtLeastTwoStartedRuns'),('Observed mode × key mode × complexity × change-limit cells (128 planned)','observedConditionCells'),('Cells with two distinct inputs','conditionCellsWithTwoInputs'),('Cells with two distinct inputs each started at least twice','conditionCellsWithTwoRepeatedInputs')]:
        lines.append('| '+label+' | '+' | '.join(str(report['inputCoverage'][p][field]) for p in ('baseten','meta'))+' |')
    lines+=['','## Cohorts and requested modes','',
            '| Cohort / mode | Open passed / scheduled | Spark 1.3 passed / scheduled |','|---|---:|---:|']
    for name in ['regression']+c.MODES:
        group=report['cohorts'][name]
        lines.append('| '+name+' | '+' | '.join(f"{group[p]['passedRuns']} / {group[p]['scheduledRuns']}" if p in group else 'Not scheduled' for p in ('baseten','meta'))+' |')
    lines+=['','The frozen offline search inspection found fewer than three distinct bounded patches for nine inputs. These cases remain in the full schedule and denominator. Capacity-conditioned counts below describe this limitation; they do not replace the complete-schedule result.','',
            '| Search capacity | Open passed / scheduled | Spark 1.3 passed / scheduled |','|---|---:|---:|']
    for name in ('at_least_three','fewer_than_three'):
        group=report['searchCapacityStrata'][name]
        lines.append('| '+name.replace('_',' ')+' | '+' | '.join(f"{group[p]['passedRuns']} / {group[p]['scheduledRuns']}" if p in group else 'Not scheduled' for p in ('baseten','meta'))+' |')
    lines+=['','## Repeated choices and failures','']
    for provider,value in report['repeatability'].items():
        lines.append(f"- {provider}: {value['allScheduledRepeatsPassed']}/{value['passages']} passages passed all scheduled repeats; {value['sameOfferEveryScheduledRepeat']} returned the same musical offer set on every scheduled repeat. Mean per-passage successful-pair Jaccard overlap: {value['meanPassageJaccardWhereTwoSuccesses']}.")
    lines+=['',f"Recorded failed, cancelled, or non-passing started executions: **{len(report['failures'])}**. Unstarted executions: **{report['unstartedRuns']}**. All are retained. No failed result was replaced by a paid rerun.",'',
            'Failure categories, each scheduled row, paired outcomes, request IDs, usage totals and raw-artifact hashes are in [the numeric report](summary.json). Original full requests, provider replies and tool feedback are in the linked compressed JSON trace files. The gzip headers contain no work timestamp.','',
            f"Combined budget accounting: **${report['accountedCostUsd']:.8f}**, against the **${report['approvedMaxUsd']:.2f}** combined cap. Returned token usage is multiplied by the configured rates; unknown usage retains its reservation. These are nominal cost estimates, not confirmed charges, paid invoices or measured credit deductions. Provider credits, sponsorships or discounts are not reconciled here. Meta and Baseten usage is recorded separately.",'',
            'Hackathon support guidance supplied by the participant places the Baseten key in a separate hackathon workspace with $100 credit expiring November 9 and no provider-side usage or balance view. Personal-dashboard figures therefore do not measure this key. See [credit attribution](README.md#hackathon-credit-attribution); local token accounting does not establish the remaining credit.','',
            '## Interpretation and limits','',
            'Muse requests searches; the unchanged tools construct candidates and the author\'s F1 Music Transformer scores their surrounding context. Muse chooses its final three from saved search feedback. The user chooses what to apply in the product. The evaluator stops at the returned offer.','',
            'The data are authored engineering fixtures using related templates. The 40 regression passages include a deliberately targeted earlier timeout and are post-hoc evidence. Input-level and repeat-level denominators remain separate. This is not a population estimate over independent songs.','',
            'Two evaluation processes per provider, existing adapter differences, local contention and uncontrolled provider caching affect time and cost. These are observed execution measurements, not isolated model speed or musical-quality rankings. Automatic validity, candidate overlap and F1 scores do not establish listening preference. Listening research is planned separately for a paper.','',
            'The campaign does not exercise browser interaction, hosted HTTP admission, user application, MIDI export or DAW playback. Full requests reach 512 bars; the existing agent/scorer window remains at most 24 bars. Product code and settings were not changed to improve results.','',
            '[Frozen protocol and inputs](README.md) · [Offline verifier](tools/report.py) · [Previous 880-run study](../reharmonize_agent_eval/extended-summary.md)','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing',action='store_true')
    parser.add_argument('--allow-incomplete',action='store_true')
    args=parser.parse_args()
    design=c.validate_identity()
    plan=c.read_json(c.OUT/'execution-plan.json')
    stop_path=c.OUT/'stop-decision.json'
    stop_decision=c.read_json(stop_path) if stop_path.exists() else None
    for provider in plan['providers']:
        for shard in (0,1):
            assert 'finished' in c.read_json(c.OUT/f'{provider}-{shard}-progress.json'), 'Wait for worker exit before reporting'
    assert c.ev.file_hash(HERE/'campaign.py')==plan['runnerSha256']
    assert c.ev.file_hash(c.OUT/'design.json')==plan['designSha256']
    api=c.ev.load_backend(c.ROOT/'backend')
    cases=c.read_json(c.OUT/'inputs.json')['cases']
    case_map={case['id']:case for case in cases}
    capacity={row['caseId']:row for row in c.read_json(c.OUT/'preflight.json')['cases']}
    rows=defaultdict(list)
    artifacts=[]
    details={}
    for provider in plan['providers']:
        all_entries=[]
        for job in c.jobs(cases):
            path=c.OUT/'runs'/provider/job['id']/'results.json.gz'
            if not path.exists():
                assert args.allow_incomplete, f'Missing scheduled batch: {provider}/{job["id"]}'
                runs=[{'caseId':case['id'],'cohort':case['cohort'],'repeat':repeat,'request':case['request'],'status':'not_started'} for repeat in range(1,job['repeats']+1) for case in job['cases']]
            else:
                report=verify_job(api,job,path,plan,design)
                runs=report['runs']
                artifacts.append({'provider':provider,'jobId':job['id'],'results':str(path.relative_to(c.OUT)),
                                  'resultsSha256':c.ev.file_hash(path),'ledgerSha256':c.ev.file_hash(path.with_name('ledger.json')),
                                  'allocatedCapUsd':report['approvedMaxUsd'],'stoppedReason':report.get('stoppedReason')})
            for run in runs:
                item={k:run[k] for k in ('caseId','cohort','repeat','status','elapsedSeconds','within100Seconds','billing','extraAttemptsWithinToolTurns','error') if k in run}
                item['mode']=run['request']['mode']
                item['jobId']=job['id']
                item['rawTrace']=str(path.relative_to(c.OUT)) if path.exists() else None
                item['checks']=run.get('audit',{}).get('checks',{})
                item['threeSearchPatchesAvailable']=capacity[run['caseId']]['threeAvailable']
                if run['status']!='not_started':
                    item['traceObservations']=observe(api,run)
                    item['requestIds']=[e.get('request_id') for e in run['apiUsage']]
                    item['httpErrors']=[{'attempt':i+1,**a['error']} for i,a in enumerate(run['httpAttempts']) if a.get('error')]
                    item['modelApproximationCount']=len(run.get('response',{}).get('modelApproximations',[]))
                    all_entries.extend(run['apiUsage'])
                rows[provider].append(item)
        details[provider]={'tokens':{key:sum((e.get('usage') or {}).get(key,0) for e in all_entries) for key in ('prompt_tokens','cached_tokens','completion_tokens','reasoning_tokens')},
                           'requestIdsRecorded':sum(bool(e.get('request_id')) for e in all_entries),
                           'requestIdsDistinct':len({e['request_id'] for e in all_entries if e.get('request_id')}),
                           'unknownRequestIds':sum(not e.get('request_id') for e in all_entries),
                           'billing':c.ev.billing(all_entries)}
    arms={p:arm_summary(v) for p,v in rows.items()}
    cohorts={name:{p:arm_summary([r for r in v if (r['cohort']=='regression' if name=='regression' else r['cohort']=='new' and r['mode']==name)]) for p,v in rows.items()} for name in ['regression']+c.MODES}
    capacity_strata={name:{p:arm_summary([r for r in v if r['threeSearchPatchesAvailable']==flag]) for p,v in rows.items()} for name,flag in [('at_least_three',True),('fewer_than_three',False)]}
    repeats={p:repeatability(v) for p,v in rows.items()}
    failures=[{'provider':p,**r} for p,v in rows.items() for r in v if r['status'] not in ('passed','not_started')]
    paired=Counter()
    overlap=[]
    if len(rows)==2:
        left={(r['caseId'],r['repeat']):r for r in rows['baseten']}
        right={(r['caseId'],r['repeat']):r for r in rows['meta']}
        assert left.keys()==right.keys()
        for key in left:
            a,b=left[key],right[key]
            paired[f"open_{a['status']}__meta_{b['status']}"]+=1
            if a['status']==b['status']=='passed':
                sa=set(a['traceObservations']['musicalPatches']); sb=set(b['traceObservations']['musicalPatches'])
                overlap.append({'caseId':key[0],'repeat':key[1],'sharedCandidates':len(sa&sb),'jaccard':len(sa&sb)/len(sa|sb)})
    accounted=round(sum(a['accountedCostUsd'] for a in arms.values()),8)
    assert accounted<=plan['approvedMaxUsd']+1e-8
    worker_accounting={}
    for provider in plan['providers']:
        for shard in (0,1):
            names={j['id'] for j in c.assign_jobs(c.jobs(cases),shard)}
            used=round(sum(c.read_json(c.OUT/'runs'/provider/name/'results.json.gz')['ledgerTotals']['accountedCostUsd'] for name in names if (c.OUT/'runs'/provider/name/'results.json.gz').exists()),8)
            key=f'{provider}-{shard}'
            assert used<=plan['workerCapsUsd'][key]+1e-8
            worker_accounting[key]={'usedUsd':used,'capUsd':plan['workerCapsUsd'][key]}
    output={'protocol':design['protocol'],'inputsSha256':design['inputsSha256'],'executionPlanSha256':c.ev.file_hash(c.OUT/'execution-plan.json'),
            'stopDecision':stop_decision,'stopDecisionSha256':c.ev.file_hash(stop_path) if stop_decision else None,
            'pairedStartedArms':{p:arm_summary(v) for p,v in shared_started_rows(rows).items()},
            'inputCoverage':{p:input_coverage(v,case_map) for p,v in rows.items()},
            'newPassages':640,'existingRegressionPassages':40,'scheduledRuns':sum(a['scheduledRuns'] for a in arms.values()),
            'unstartedRuns':sum(a['scheduledRuns']-a['startedRuns'] for a in arms.values()),'arms':arms,'cohorts':cohorts,
            'searchCapacityStrata':capacity_strata,'repeatability':repeats,'providerDetails':details,'pairedOutcomes':dict(paired),
            'pairedSuccessfulCandidateOverlap':overlap,'accountedCostUsd':accounted,'approvedMaxUsd':plan['approvedMaxUsd'],
            'workerAccounting':worker_accounting,'failures':failures,'failureCategories':dict(Counter((r.get('error') or {}).get('type',r['status']) for r in failures)),
            'runs':dict(rows),'artifacts':artifacts,'verification':{'networkCalls':0,'serviceSha256':design['serviceSha256'],'frozenInputsMatch':True,'savedChecksRecomputed':True,'ledgersReconciled':True,'noOutstandingReservations':True},
            'limitations':['Authored related templates, not representative independent songs','Regression cohort selected after previous results','Parallel evaluation and provider cache differences affect timing','No listening preference or musical superiority measure','No browser, hosted admission, user application, MIDI export or DAW playback in this campaign']}
    if not args.allow_incomplete: assert output['unstartedRuns']==0
    elif output['unstartedRuns']: assert stop_decision, 'Document why the frozen schedule was not completed'
    md=render(output)
    if args.verify_existing:
        assert c.read_json(c.OUT/'summary.json')==output
        assert (c.OUT/'summary.md').read_text()==md
    else:
        assert not (c.OUT/'summary.json').exists() and not (c.OUT/'summary.md').exists()
        c.write_json(c.OUT/'summary.json',output)
        (c.OUT/'summary.md').write_text(md)
    print(json.dumps({'verified':True,'networkCalls':0,'scheduledRuns':output['scheduledRuns'],'unstartedRuns':output['unstartedRuns'],
                      'arms':arms,'failureCategories':output['failureCategories'],'accountedCostUsd':accounted},indent=2))


if __name__=='__main__': main()
