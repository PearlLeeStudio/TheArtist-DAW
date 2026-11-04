"""Create fixed evaluation inputs without searching candidates or calling a model."""
import hashlib
import importlib.util
import json
import random
from collections import Counter
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("evaluation", "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/agent/evaluate_reharmonize_agent.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)
BACKEND = Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/backend")
api = evaluation.load_backend(BACKEND)
OUTPUTS = [
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-d.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-e.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-f.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-g.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-h.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-i.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-j.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-k.json"),
]
PRIOR_INPUTS = [
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-b.json"),
    Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-c.json"),
]
PLAN = Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/expansion-plan.json")
AXES = ["short-boundaries", "empty-unselected-slots", "sixteen-selected-slots", "full-surrounding-window",
        "long-score-preservation", "notation-and-slash-bass", "chromatic-mixture", "meter-and-ending-selection"]
ROOTS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARPS = ["B#", "C#", "D", "D#", "Fb", "E#", "F#", "G", "G#", "A", "A#", "Cb"]
TONICS = ["C", "G", "D", "A", "E", "B", "Gb", "Db", "Ab", "Eb", "Bb", "F"]
METERS = [[4,4],[3,4],[6,8],[5,4],[2,4]]
PATTERNS = {
    "major": [[0,5,1,4,2,5,1,4], [0,3,0,4,5,3,1,4], [0,2,3,4,5,1,4,0],
              [0,6,2,5,1,3,4,0], [0,4,5,3,1,5,4,0], [3,2,1,4,0,5,3,4],
              [0,1,2,3,5,3,4,0], [5,2,3,0,1,4,5,4]],
    "minor": [[0,3,6,2,5,1,4,0], [0,5,3,4,0,2,6,4], [0,6,5,4,3,1,4,0],
              [0,2,5,1,4,0,3,4], [3,0,5,6,2,1,4,0], [0,4,3,6,2,5,4,0],
              [0,1,3,4,5,3,6,0], [5,6,0,3,1,4,0,4]],
}


def signature(req, effective=False):
    tonic = api.search.pitch(req.key.split()[0])
    bars = api.search.context_window(req) if effective else req.context
    return evaluation.canonical([[None if symbol is None else (
        (api.search.chord(symbol)[0]-tonic)%12,
        sorted((pc-tonic)%12 for pc in api.search.chord(symbol)[1]),
        (api.search.chord(symbol)[2]-tonic)%12,
    ) for symbol in bar.chords] for bar in bars])


def make_case(batch, index, salt):
    rng = random.Random(311 + batch*100003 + index*1009 + salt*104729)
    mode = "major" if index < 10 else "minor"
    complex_chords = index % 10 >= 5
    tonic_name = TONICS[(index*5+batch*3)%12]
    tonic = api.search.pitch(tonic_name)
    count = ([1,2,3,2,3][index%5] if batch==0 else
             [4,6,8,10,12][index%5] if batch==1 else
             [8,12,16,20,24][index%5] if batch==2 else
             24 if batch==3 else
             [32,64,128,512][index%4] if batch==4 else
             [6,8,10,12,16][index%5] if batch in (5,6) else
             [5,7,9,13,17][index%5])
    scale = [0,2,4,5,7,9,11] if mode=="major" else [0,2,3,5,7,8,10]
    qualities = ["","m","m","","","m","dim"] if mode=="major" else ["m","dim","","m","","",""]
    extended = ["maj7","m7","m9","maj9","7","m11","m7b5"] if mode=="major" else ["m7","m7b5","maj7","m9","7b9","maj9","7"]
    pattern = PATTERNS[mode][(index+batch+salt)%8]
    flat=[]
    for pos in range(count*2):
        degree = pattern[(pos+index+salt)%len(pattern)]
        if pos%5==3:
            degree = rng.randrange(7)
        root = (tonic+scale[degree])%12
        quality = extended[degree] if complex_chords else qualities[degree]
        if batch==6 and pos%3==1:
            root=(tonic+[1,3,6,8,10][(pos+index)%5])%12
            quality = ["7","maj7","m7","dim7","7#9"][(pos+index)%5] if complex_chords else ["","m","dim"][(pos+index)%3]
        if batch==5 and complex_chords and pos%3==0:
            quality=["maj13","mMaj9","13sus4","m(add9)","7(no3)","7(b9,#11)","6/9"][(pos+index)%7]
        names = SHARPS if batch==5 and (pos+index)%2 else ROOTS
        symbol = names[root]+quality
        if complex_chords and (pos+index)%4==2:
            symbol += "/"+names[(root+(3 if quality.startswith("m") and not quality.startswith("maj") else 4))%12]
        flat.append(symbol)
    bars=[flat[p:p+2] for p in range(0,len(flat),2)]
    span=min(8,count)
    start=(8 if batch==3 else count-span if batch==7 or (batch==4 and index%2) else (count-span)//2)
    available=[[m,s] for m in range(start,start+span) for s in (0,1)]
    if batch==2:
        selected=available
    else:
        n=min(len(available),[1,2,4,6,8][(index+batch)%5])
        selected=sorted(rng.sample(available,n))
        if batch==3:
            selected=sorted({tuple(x) for x in selected}|{(8,0),(15,1)})
            selected=[list(x) for x in selected]
    if batch==1:
        unselected=[[m,s] for m in range(count) for s in (0,1) if [m,s] not in selected]
        for m,s in unselected[::2]:
            bars[m][s]=None
    return {"id":chr(100+batch)+"-"+mode+"-"+str(index%10+1).zfill(2),
            "key":tonic_name+" "+mode,"complexity":"complex" if complex_chords else "simple",
            "meter":METERS[(index+batch)%5],"maxChanges":index%4+1,
            "selected":selected,"bars":bars,"stressAxis":AXES[batch],
            "authoredFamily":(index+batch+salt)%8,"fixtureVariation":salt}


def main():
    if PLAN.exists() or any(p.exists() for p in OUTPUTS):
        raise ValueError("Refusing to replace frozen inputs or plan")
    seen, windows, ids = set(), set(), set()
    for path in PRIOR_INPUTS:
        for item in evaluation.requests_from(json.loads(path.read_text())):
            req=api.Request.model_validate(item["request"])
            seen.add(signature(req)); windows.add(signature(req,True)); ids.add(item["id"])
    datasets=[]
    for batch in range(8):
        cases=[]
        for index in range(20):
            for salt in range(1000):
                case=make_case(batch,index,salt)
                raw={"key":case["key"],"timeSignature":case["meter"],"context":[{"measure":m,"chords":b} for m,b in enumerate(case["bars"])],
                     "selectedSlots":[{"measureIndex":m,"slotIndex":s} for m,s in case["selected"]],"maxChanges":case["maxChanges"],"modelKey":"ft_f1","mode":"auto"}
                req=api.Request.model_validate(raw)
                api.search.validate_context(req)
                full,window=signature(req),signature(req,True)
                if full not in seen and window not in windows:
                    break
            else:
                raise ValueError("Unable to produce distinct fixture without model output")
            assert case["id"] not in ids
            seen.add(full); windows.add(window); ids.add(case["id"]); cases.append(case)
        data={"protocol":evaluation.PROTOCOL,"origin":"Systematic engineering fixtures from authored degree patterns, frozen before new-batch model outputs; related patterns are not independent songs.",
              "design":{"axis":AXES[batch],"seed":311,"selection":"Input schema and full/effective-window uniqueness only; no candidate search or model outcome filtering."},
              "modelKey":"ft_f1","mode":"auto","repeats":2,"cases":cases}
        evaluation.requests_from(data)
        datasets.append(data)
    assert len(seen)==len(windows)==len(ids)==220
    for path,data in zip(OUTPUTS,datasets):
        with path.open("x") as stream:
            stream.write(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
    batches=[]
    for batch,path in enumerate(OUTPUTS):
        cases,identity=evaluation.inspect_inputs(api,BACKEND,path)
        batches.append({"id":chr(100+batch),"axis":AXES[batch],"input":path.name,"sha256":identity["casesSha256"],"passages":20,"runsPerProvider":40,"capPerProviderUsd":6})
    plan={"campaign":"reharmonize-agent-input-expansion-v1","approvedOverallNewSpendCeilingUsd":120,
          "comparisonAllocationUsd":18,"expansionAllocationUsd":96,"totalAllocatedUsd":114,
          "newPassages":160,"repeatsPerPassage":2,"providers":["baseten","meta"],"scheduledNewRuns":640,
          "modelKey":"ft_f1","searchMode":"auto","batches":batches,
          "evaluatorSha256":identity["evaluatorSha256"],"serviceSha256":identity["serviceSha256"],"checkpointSha256":identity["checkpointSha256"],
          "generatorSha256":evaluation.file_hash(Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/agent/build_reharmonize_expansion.py")),
          "executionOrder":"d through k; baseten then meta within each batch; two rounds in each unchanged evaluator invocation; no concurrent model executions.",
          "noReplacementRuns":True,"denominator":"All 640 scheduled expansion rows, including failures and unstarted runs; two repeats grouped under each passage.",
          "interpretation":"Systematic authored fixtures, not corpus samples. Full-score lengths up to 512 bars do not imply 512-bar model prompts: the unchanged product uses the selection plus eight surrounding bars on each side, at most 24 bars.",
          "offlineChecks":{"uniqueFullPassagesAcrossOldAndNew":220,"uniqueEffectiveWindowsAcrossOldAndNew":220,"networkCalls":0}}
    with PLAN.open("x") as stream:
        stream.write(json.dumps(plan,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"newPassages":160,"newRuns":640,"newCapUsd":96,"combinedNewCapUsd":114,"uniqueEffectiveWindows":len(windows),"batches":batches},indent=2))


if __name__=="__main__":
    main()
