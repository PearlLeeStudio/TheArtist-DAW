"""Freeze authored inputs before candidate search or paid outputs; never call a provider."""
import hashlib
import importlib.util
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = OUT.parents[1]
OLD = ROOT / 'experiments/reharmonize_agent_eval'
spec = importlib.util.spec_from_file_location('frozen_evaluator', OLD / 'tools/evaluate_reharmonize_agent.py')
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
api = ev.load_backend(ROOT / 'backend')
MODES = ['auto', 'ionian', 'dorian', 'phrygian', 'lydian', 'mixolydian', 'aeolian', 'locrian']
ROOTS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
METERS = [[4,4], [3,4], [6,8], [5,4], [2,4]]
PATTERNS = [
    [0, 5, 1, 4, 0, 3, 1, 4], [0, 2, 5, 1, 4, 0, 3, 4],
    [0, 3, 0, 4, 5, 2, 1, 4], [5, 3, 0, 4, 1, 5, 4, 0],
    [0, 6, 3, 4, 0, 5, 1, 4], [3, 0, 5, 2, 1, 4, 0, 4],
    [0, 1, 3, 0, 5, 4, 1, 0], [0, 4, 2, 5, 1, 3, 4, 0],
    [5, 1, 4, 0, 3, 2, 6, 4], [0, 3, 6, 2, 5, 1, 4, 0],
    [0, 5, 3, 6, 2, 4, 1, 0], [3, 6, 2, 5, 1, 4, 0, 0],
]


def signature(request):
    req = api.Request.model_validate(request)
    tonic = api.search.pitch(req.key.split()[0])
    return ev.canonical([[None if s is None else (
        (api.search.chord(s)[0]-tonic)%12,
        sorted((p-tonic)%12 for p in api.search.chord(s)[1]),
        (api.search.chord(s)[2]-tonic)%12,
    ) for s in b.chords] for b in api.search.context_window(req)])


def fixture(mode_index, index, salt):
    rng = random.Random(709163 + mode_index*1000003 + index*1009 + salt*99991)
    minor = index % 2 == 1
    complex_chords = (index//2) % 2 == 1
    tonic = (index*5 + mode_index*7) % 12
    key_mode = 'minor' if minor else 'major'
    scale = [0,2,3,5,7,8,10] if minor else [0,2,4,5,7,9,11]
    qualities = ['m','dim','','m','','',''] if minor else ['','m','m','','','m','dim']
    extended = ['m9','m7b5','maj9','m11','7b9','maj7','7'] if minor else ['maj9','m9','m7','maj7','13','m11','m7b5']
    shape = (index//4) % 10
    count = [4,8,16,24,32,64,128,512,12,6][shape]
    offset = 0 if count == 512 else [0,7,32,128,512-count][(index+mode_index)%5]
    span = min(8,count)
    start = [0,(count-span)//2,count-span][(index//8+mode_index)%3]
    available = [(m,s) for m in range(start,start+span) for s in (0,1)]
    selection_count = min(len(available),[1,2,4,6,8,16,2,4,8,16][shape])
    selected = sorted(rng.sample(available,selection_count))
    pattern = PATTERNS[(index+mode_index+salt)%len(PATTERNS)]
    bars=[]
    for measure in range(count):
        values=[]
        for slot in (0,1):
            pos=measure*2+slot
            degree=pattern[(pos+index)%len(pattern)]
            if pos%5==2 or pos%11==7:
                degree=rng.randrange(7)
            root=(tonic+scale[degree])%12
            quality=(extended if complex_chords else qualities)[degree]
            if shape in (2,4,8) and pos%7==3:
                root=(tonic+[1,3,6,8,10][rng.randrange(5)])%12
                quality=rng.choice(['7','maj7','m7','dim7']) if complex_chords else rng.choice(['','m','dim'])
            if complex_chords and shape in (3,6,9) and pos%5==1:
                quality=['maj13','mMaj9','13sus4','m(add9)','7(no3)','7(b9,#11)','6/9'][(pos+index)%7]
            symbol=ROOTS[root]+quality
            if complex_chords and pos%4==1:
                symbol+='/'+ROOTS[(root+(3 if quality.startswith('m') and not quality.startswith('maj') else 4))%12]
            if shape in (1,5,7) and (measure,slot) not in selected and pos%3==0:
                symbol=None
            values.append(symbol)
        bars.append({'measure':measure+offset,'chords':values})
    request={'key':ROOTS[tonic]+' '+key_mode,'timeSignature':METERS[(index+mode_index)%5],
             'context':bars,'selectedSlots':[{'measureIndex':m+offset,'slotIndex':s} for m,s in selected],
             'maxChanges':(index//4)%4+1,'mode':MODES[mode_index],'modelKey':'ft_f1'}
    return {'id':f'new-{MODES[mode_index]}-{index+1:03d}','cohort':'new',
            'complexity':'complex' if complex_chords else 'simple','shape':shape,
            'authoredFamily':(index+mode_index+salt)%len(PATTERNS),'fixtureVariation':salt,'request':request}


def write_new(path,data):
    with path.open('x') as stream:
        stream.write(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def main():
    assert not (OUT/'inputs.json').exists(), 'Frozen inputs must never be overwritten'
    assert not (OUT/'design.json').exists()
    previous=[]
    for batch in 'abcdefghijk':
        path=OLD/('cases.json' if batch=='a' else f'cases-{batch}.json')
        for c in ev.requests_from(json.loads(path.read_text())):
            previous.append(c)
    seen={signature(c['request']) for c in previous}
    cases=[]
    for mi in range(8):
        for i in range(80):
            for salt in range(1000):
                case=fixture(mi,i,salt)
                req=api.Request.model_validate(case['request'])
                api.search.validate_context(req)
                sig=signature(case['request'])
                if sig not in seen: break
            else: raise ValueError('Cannot create a distinct fixture')
            seen.add(sig)
            cases.append(case)
    # Input-hash ordering is fixed, independent of the prior outcome. The known
    # timeout is included explicitly as a targeted regression case, not a new song.
    targeted=next(c for c in previous if c['id']=='g-minor-03')
    ordered=sorted([c for c in previous if c['id']!=targeted['id']],key=lambda c:ev.digest(c['request']))
    sentinels=[targeted]+ordered[:39]
    for c in sentinels:
        cases.append({**c,'cohort':'regression','targetedPreviousTimeout':c['id']==targeted['id']})
    data={'protocol':'reharmonize-agent-stress-v2','origin':'Authored engineering fixtures; no corpus or source score is reproduced.',
          'design':'All inputs are frozen before search or paid outputs. Related harmonic templates are not independent sampled songs.',
          'cases':cases}
    write_new(OUT/'inputs.json',data)
    sources={n:ev.file_hash(ROOT/'backend'/n) for n in ev.SERVICE_FILES}
    for n in ('model.py','tokenizer.py'):
        sources['ai/training/'+n]=ev.file_hash(ROOT/'ai/training'/n)
    design={'protocol':data['protocol'],'newPassages':640,'existingRegressionPassages':40,
            'prepaidDesignRevision':'The preserved input-only preparation coupled key mode and complexity with change allowance. Before any paid outputs, allowance allocation was corrected to cross these factors: five cases per key-mode/complexity/allowance cell within each request mode. Chords, selections and case membership were not filtered or replaced. Preparation files are not executed evidence.',
            'repeats':{'new':6,'regression':10},'scheduledRunsPerProvider':4240,
            'scheduledPairedRuns':8480,'plannedProviders':['baseten','meta'],
            'authorizationCeilingUsd':128,'plannedCombinedCapUsd':120,
            'plannedWorkerCapsUsd':{'baseten-0':20,'baseten-1':20,'meta-0':40,'meta-1':40},
            'estimatedCostUsdFromPriorCampaign':round(4240*(3.4159304+6.73578275)/440,2),
            'maximumWorkers':4,'maximumWorkersPerProvider':2,'stopAfterElapsedSeconds':75600,
            'stopPolicy':'No replacements. Stop before new paid attempts at caps, provider authorization/credit failures, requested stop, or elapsed deadline. Preserve failures and unstarted rows.',
            'inputsSha256':ev.file_hash(OUT/'inputs.json'),'serviceSha256':ev.digest(sources),'sourceFiles':sources,
            'checkpointSha256':ev.file_hash(ROOT/'ai/checkpoints/ft_jazz_pop80/best.pt'),
            'frozenEvaluatorSha256':ev.file_hash(OLD/'tools/evaluate_reharmonize_agent.py'),
            'generatorSha256':ev.file_hash(Path(__file__).resolve()),
            'priorEvidence':'../reharmonize_agent_eval/extended-summary.json',
            'timingScope':'Parallel evaluation processes with independent clients and ledgers; not hosted throughput or isolated model capability.',
            'inputSelection':'Schema and harmonic-window uniqueness only. No candidate count, learned score or paid result was used to select new inputs.',
            'regressionSelection':'The earlier g-minor-03 timeout plus the first 39 other prior inputs ordered by request SHA-256. Explicitly post-hoc repeatability evidence.'}
    assert design['serviceSha256']=='bf861a6dc299e97796a396bb14a42252e785de2021ca4ebf3c4d022c1d55d681'
    write_new(OUT/'design.json',design)
    print(json.dumps({k:design[k] for k in ('newPassages','existingRegressionPassages','scheduledPairedRuns','plannedCombinedCapUsd','estimatedCostUsdFromPriorCampaign','inputsSha256','serviceSha256')}))


if __name__=='__main__':
    main()
