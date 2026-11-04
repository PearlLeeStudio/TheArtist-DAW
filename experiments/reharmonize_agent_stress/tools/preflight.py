"""Inspect the already-frozen requests and unchanged search without provider calls."""
import importlib.util
import json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('campaign',HERE/'campaign.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def main():
    design=c.validate_identity()
    api=c.ev.load_backend(c.ROOT/'backend')
    cases=c.read_json(c.OUT/'inputs.json')['cases']
    rows=[]
    for item in cases:
        req=api.Request.model_validate(item['request'])
        api.search.validate_context(req)
        by_family={family:api.search.search(req,family) for family in api.agent.FAMILIES}
        pool={candidate.id:candidate for candidates in by_family.values() for candidate in candidates}
        signatures=set()
        for candidate in pool.values():
            signatures.add(c.ev.canonical(sorted((change.address.measureIndex,change.address.slotIndex,
                [api.search.chord(change.after)[0],sorted(api.search.chord(change.after)[1]),api.search.chord(change.after)[2]])
                for change in candidate.changes)))
        rows.append({'caseId':item['id'],'cohort':item['cohort'],'mode':req.mode,
                     'keyMode':req.key.split()[1],'complexity':item['complexity'],'maxChanges':req.maxChanges,
                     'fullBars':len(req.context),'effectiveBars':len(api.search.context_window(req)),
                     'selectedSlots':len(req.selectedSlots),'measureOffset':min(b.measure for b in req.context),
                     'candidateCounts':{f:len(v) for f,v in by_family.items()},'uniqueCandidateIds':len(pool),
                     'uniqueMusicalPatches':len(signatures),'threeAvailable':len(signatures)>=3})
    output={'protocol':design['protocol'],'inputsSha256':design['inputsSha256'],'networkCalls':0,
            'performedAfterInputFreeze':True,'doesNotFilterOrReplaceInputs':True,
            'scope':'Unchanged bounded mathematical search, without F1 ranking or provider inference. Capacity is descriptive, not a new pass denominator.',
            'validRequests':len(rows),'withAtLeastThreeSearchPatches':sum(r['threeAvailable'] for r in rows),
            'byMode':{mode:{'cases':sum(r['mode']==mode for r in rows),
                           'withAtLeastThreeSearchPatches':sum(r['mode']==mode and r['threeAvailable'] for r in rows)} for mode in c.MODES},
            'jointStrata':dict(Counter('|'.join(str(r[k]) for k in ('keyMode','complexity','maxChanges')) for r in rows if r['cohort']=='new')),
            'cases':rows}
    target=c.OUT/'preflight.json'
    assert not target.exists()
    c.write_json(target,output)
    print(json.dumps({k:output[k] for k in ('validRequests','networkCalls','withAtLeastThreeSearchPatches','byMode','jointStrata')},indent=2))


if __name__=='__main__': main()
