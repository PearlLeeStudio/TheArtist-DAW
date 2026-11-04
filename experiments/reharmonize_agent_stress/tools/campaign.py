"""Evaluation-only campaign: unchanged product entry point, bounded independent ledgers.

No server configuration, product prompt, model placement or search code is edited.
The preserved v1 evaluator supplies observation and mechanical audit primitives.
"""
import argparse
import copy
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
OUT=HERE.parent
ROOT=OUT.parents[1]
OLD=ROOT/'experiments/reharmonize_agent_eval'
spec=importlib.util.spec_from_file_location('frozen_evaluator',OLD/'tools/evaluate_reharmonize_agent.py')
ev=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
MODES=['auto','ionian','dorian','phrygian','lydian','mixolydian','aeolian','locrian']
SERVICE_HASH='bf861a6dc299e97796a396bb14a42252e785de2021ca4ebf3c4d022c1d55d681'


def read_json(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())


def write_json(path,data,secret=''):
    body=(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    if secret and secret.encode() in body:
        raise ValueError('Refusing to save credentials')
    if path.suffix=='.gz':
        body=gzip.compress(body,compresslevel=5,mtime=0)
    pending=path.with_name(path.name+'.pending')
    with pending.open('xb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending,path)


def validate_identity():
    design=read_json(OUT/'design.json')
    assert ev.file_hash(OUT/'inputs.json')==design['inputsSha256']
    sources={n:ev.file_hash(ROOT/'backend'/n) for n in ev.SERVICE_FILES}
    for n in ('model.py','tokenizer.py'):
        sources['ai/training/'+n]=ev.file_hash(ROOT/'ai/training'/n)
    assert ev.digest(sources)==design['serviceSha256']==SERVICE_HASH
    assert ev.file_hash(ROOT/'ai/checkpoints/ft_jazz_pop80/best.pt')==design['checkpointSha256']
    assert ev.file_hash(OLD/'tools/evaluate_reharmonize_agent.py')==design['frozenEvaluatorSha256']
    return design


def jobs(cases):
    # Round-robin across modes; two disjoint workers per provider receive even/odd
    # jobs. Every condition includes both workers instead of confounding mode with worker.
    result=[]
    for quarter in range(4):
        for mode in MODES:
            group=[c for c in cases if c['cohort']=='new' and c['request']['mode']==mode]
            result.append({'id':f'new-{mode}-{quarter}','repeats':6,'cases':group[quarter*20:(quarter+1)*20]})
    regression=[c for c in cases if c['cohort']=='regression']
    for half in range(2):
        result.append({'id':f'regression-{half}','repeats':10,'cases':regression[half*20:(half+1)*20]})
    assert len(result)==34 and sum(len(j['cases'])*j['repeats'] for j in result)==4240
    return result


def assign_jobs(all_jobs,worker):
    # Shift assignment at each quarter so every mode appears in both processes.
    return [j for i,j in enumerate(all_jobs) if (i+(i//8))%2==worker]


def audit(api,request,response,unchanged,model):
    result=ev.audit_response(api,request,response,unchanged,model)
    tonic=api.search.pitch(request['key'].split()[0])
    selected_mode=request['mode']
    compatible=True
    if selected_mode!='auto':
        scale={(tonic+p)%12 for p in api.search.MODES[selected_mode]}
        compatible=bool(response.get('candidates')) and all(
            api.search.chord(change['after'])[1]<=scale
            for c in response['candidates'] for change in c['changes'])
    result['checks']['explicitModeCompatible']=compatible
    result['passed']=all(result['checks'].values())
    return result


def summarize(records):
    summary=ev.summary(records)
    summary['allScheduledRepeatsPassed']=summary.pop('bothRepeatsPassed')
    summary['checksPassedOverAllScheduled']['explicitModeCompatible']={
        'passed':sum(r.get('audit',{}).get('checks',{}).get('explicitModeCompatible',False) for r in records),
        'denominator':len(records)}
    return summary


def terminal_provider_error(record):
    error=record.get('error',{})
    if error.get('statusCode') in (401,402,403) or error.get('type') in ('CreditExhausted','LedgerError'):
        return True
    if record.get('response',{}).get('metaUnavailable') in ('paused','unconfigured'):
        return True
    return any(a.get('error',{}).get('statusCode') in (401,402,403) for a in record.get('httpAttempts',[]))


def run_job(api,job,provider,cap,stop,deadline,identity):
    directory=OUT/'runs'/provider/job['id']
    directory.mkdir(parents=True,exist_ok=False)
    env={'MODEL_API_KEY':os.environ.get('MODEL_API_KEY',''),'LLM_AGENT_PROVIDER':'meta'} if provider=='meta' else {
        'LLM_AGENT_PROVIDER':'baseten','LLM_AGENT_API_KEY':os.environ.get('BASETEN_API_KEY','')}
    env['LLM_AGENT_REASONING_EFFORT']='low'
    config=api.llm.LLMConfig.from_env(env,role='agent')
    if not config.api_key or config.model!=ev.MODELS[provider]:
        raise ValueError('Selected credential/model is unavailable')
    ledger=ev.make_ledger(api,directory/'ledger.json',cap,stop)
    records=[{'caseId':c['id'],'cohort':c['cohort'],'repeat':repeat,
              'request':c['request'],'status':'not_started'}
             for repeat in range(1,job['repeats']+1) for c in job['cases']]
    report={'protocol':'reharmonize-agent-stress-v2','jobId':job['id'],'provider':provider,
            'model':config.model,'reasoningEffort':'low','identity':identity,'approvedMaxUsd':cap,
            'pricesPerMillion':{'input':config.price_input_per_m,'cached':config.price_cached_per_m,
                               'output':config.price_output_per_m,'source':config.price_source},'runs':records}
    def persist():
        report['summary']=summarize(records)
        report['ledgerTotals']=ev.billing(ledger.audit_state()['entries'])
        write_json(directory/'results.json.gz',report,config.api_key)
    persist()
    for record in records:
        if stop[0] or time.monotonic()>=deadline:
            stop[0]=True
            report['stoppedReason']='Stop requested or elapsed deadline reached'
            break
        state=ledger.audit_state()
        if state['spent_usd']+.15>cap+1e-8:
            report['stoppedReason']='Insufficient allocated budget for another complete run'
            break
        ledger.begin_run(12 if provider=='baseten' else 4)
        raw_attempts=[]
        transport=api.llm.OpenAITransport(config)
        def observed(body):
            if stop[0] or time.monotonic()>=deadline:
                stop[0]=True
                raise api.llm.LLMCancelled('Campaign stopped before transport')
            attempt={'request':copy.deepcopy(body)}
            raw_attempts.append(attempt)
            began=time.monotonic()
            try:
                response,headers=transport(body)
                attempt['response']={k:response[k] for k in ('id','model','choices','usage') if k in response}
                attempt['responseHeaders']={k:v for k,v in headers.items() if k.lower() in ('x-request-id','x-baseten-request-id')}
                return response,headers
            except Exception as exc:
                attempt['error']={'type':type(exc).__name__,'statusCode':getattr(exc,'status_code',None)}
                raise
            finally:
                attempt['elapsedSeconds']=round(time.monotonic()-began,6)
        client=ev.ObservedClient(api.llm.LLMClient(config=config,ledger=ledger,transport=observed))
        req=api.Request.model_validate(record['request'])
        before=req.model_dump(mode='json')
        began=time.monotonic()
        try:
            response=api.agent.propose(req,client=client).model_dump(mode='json')
            record['response']=response
            record['audit']=audit(api,record['request'],response,before==req.model_dump(mode='json'),config.model)
            record['status']='passed' if record['audit']['passed'] else 'local_selection' if response['selection']=='local' else 'failed_checks'
        except Exception as exc:
            record['status']='cancelled' if isinstance(exc,api.llm.LLMCancelled) else 'failed'
            record['error']={'type':type(exc).__name__,'kind':getattr(exc,'kind',None),
                             'statusCode':getattr(exc,'status_code',None),'requestId':getattr(exc,'request_id',None)}
        finally:
            record['elapsedSeconds']=round(time.monotonic()-began,6)
            record['within100Seconds']=record['elapsedSeconds']<=100
            entries=ledger.audit_state()['entries'][ledger.run_start_entries:]
            record['billing']=ev.billing(entries)
            record['apiUsage']=entries
            record['turns']=client.turns
            record['httpAttempts']=raw_attempts
            from collections import Counter
            labels=Counter(e['label'] for e in entries)
            record['extraAttemptsWithinToolTurns']=sum(max(0,n-1) for n in labels.values())
            persist()
        if terminal_provider_error(record):
            stop[0]=True
            report['stoppedReason']='Provider access, credit, or ledger failure'
            break
    persist()
    assert report['ledgerTotals']['outstandingUsd']==0, 'Unsettled reservation requires review'
    return report


def worker(args):
    design=validate_identity()
    plan=read_json(OUT/'execution-plan.json')
    assert ev.file_hash(Path(__file__).resolve())==plan['runnerSha256']
    assert ev.file_hash(OUT/'design.json')==plan['designSha256']
    assert args.provider in plan['providers']
    name=f'{args.provider}-{args.worker}'
    cap=plan['workerCapsUsd'][name]
    api=ev.load_backend(ROOT/'backend')
    assert not api.agent.meta_budget_unlimited()
    assert {n:getattr(api.agent,n) for n in ('MAX_USD','MAX_TURNS','MAX_TOOL_CALLS','MAX_SECONDS','MAX_COMPLETION_TOKENS')}=={
        'MAX_USD':.15,'MAX_TURNS':4,'MAX_TOOL_CALLS':6,'MAX_SECONDS':100,'MAX_COMPLETION_TOKENS':4096}
    selected=assign_jobs(jobs(read_json(OUT/'inputs.json')['cases']),args.worker)
    stop=[False]
    def request_stop(signum,frame): stop[0]=True
    for signum in (signal.SIGINT,signal.SIGTERM): signal.signal(signum,request_stop)
    deadline=time.monotonic()+args.remaining_seconds
    state={'worker':name,'capUsd':cap,'completedJobs':[],'accountedCostUsd':0,'startedRuns':0,'passedRuns':0}
    identity={k:design[k] for k in ('inputsSha256','serviceSha256','checkpointSha256','frozenEvaluatorSha256')}
    identity['runnerSha256']=plan['runnerSha256']
    for job in selected:
        if stop[0] or time.monotonic()>=deadline or cap-state['accountedCostUsd']<.15:
            state['stopped']=True
            break
        allocated=round(min(6,cap-state['accountedCostUsd']),8)
        report=run_job(api,job,args.provider,allocated,stop,deadline,identity)
        state['accountedCostUsd']=round(state['accountedCostUsd']+report['ledgerTotals']['accountedCostUsd'],8)
        state['startedRuns']+=report['summary']['startedRuns']
        state['passedRuns']+=report['summary']['passedRuns']
        state['completedJobs'].append({'id':job['id'],'allocatedCapUsd':allocated,'summary':report['summary'],
                                      'stoppedReason':report.get('stoppedReason')})
        assert state['accountedCostUsd']<=cap+1e-8
        write_json(OUT/(name+'-progress.json'),state)
        print(json.dumps({'worker':name,'job':job['id'],'startedRuns':state['startedRuns'],
                          'passedRuns':state['passedRuns'],'accountedCostUsd':state['accountedCostUsd']}),flush=True)
        if report.get('stoppedReason'):
            state['stopped']=True
            break
    state['finished']=len(state['completedJobs'])==len(selected) and not state.get('stopped')
    write_json(OUT/(name+'-progress.json'),state)
    return 0 if state['finished'] else 2


def launch(args):
    design=validate_identity()
    assert args.inputs_sha256==design['inputsSha256']
    assert 0<args.approved_max_usd<=120
    assert not (OUT/'execution-plan.json').exists(), 'No paid restart or replacement is permitted'
    providers=['baseten','meta'] if args.providers=='both' else [args.providers]
    caps=({'baseten-0':20,'baseten-1':20,'meta-0':40,'meta-1':40} if len(providers)==2 else
          {providers[0]+'-0':60,providers[0]+'-1':60})
    scale=args.approved_max_usd/sum(caps.values())
    caps={k:round(v*scale,8) for k,v in caps.items()}
    assert sum(caps.values())<=args.approved_max_usd+1e-8
    plan={'protocol':'reharmonize-agent-stress-v2','providers':providers,'workerCapsUsd':caps,
          'approvedMaxUsd':args.approved_max_usd,'scheduledRuns':4240*len(providers),
          'designSha256':ev.file_hash(OUT/'design.json'),'runnerSha256':ev.file_hash(Path(__file__).resolve()),
          'deadlineElapsedSeconds':design['stopAfterElapsedSeconds'],'globalCapProof':'Independent non-overlapping worker caps sum to the total cap. A worker allocates each fresh batch only from its unsettled-free remaining amount.',
          'scope':'Existing product agent and F1 scorer; four evaluation processes at most. No server, UI, provider deployment or prompt changes.'}
    with (OUT/'execution-plan.json').open('x') as stream: stream.write(json.dumps(plan,indent=2)+'\n')
    children=[]
    stopped=[False]
    def request_stop(signum,frame):
        stopped[0]=True
        for child in children:
            if child.poll() is None: child.send_signal(signal.SIGTERM)
    for signum in (signal.SIGINT,signal.SIGTERM): signal.signal(signum,request_stop)
    began=time.monotonic()
    for provider in providers:
        for shard in (0,1):
            child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'worker','--provider',provider,
                                    '--worker',str(shard),'--remaining-seconds',str(design['stopAfterElapsedSeconds']-(time.monotonic()-began))],env=os.environ.copy())
            children.append(child)
    while any(child.poll() is None for child in children):
        if time.monotonic()-began>=design['stopAfterElapsedSeconds'] or any(child.poll() not in (None,0) for child in children):
            request_stop(None,None)
        time.sleep(5)
    print(json.dumps({'campaignFinished':all(c.returncode==0 for c in children),'exitCodes':[c.returncode for c in children],
                      'elapsedSeconds':round(time.monotonic()-began,3)}),flush=True)
    return 0 if all(c.returncode==0 for c in children) else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run')
    run.add_argument('--providers',choices=['both','meta','baseten'],required=True)
    run.add_argument('--approved-max-usd',type=float,required=True)
    run.add_argument('--inputs-sha256',required=True)
    work=sub.add_parser('worker')
    work.add_argument('--provider',choices=['meta','baseten'],required=True)
    work.add_argument('--worker',type=int,choices=[0,1],required=True)
    work.add_argument('--remaining-seconds',type=float,required=True)
    args=parser.parse_args()
    return worker(args) if args.command=='worker' else launch(args)


if __name__=='__main__':
    raise SystemExit(main())
