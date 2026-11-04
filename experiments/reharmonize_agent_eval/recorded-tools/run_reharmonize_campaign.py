"""Run the approved remaining evaluation batches sequentially, without product edits.

The already-started meta-a batch must be complete. Existing reports are never
rerun or overwritten. Every child uses the unchanged evaluator and its own $6
ledger; 19 new batches including meta-a reserve at most $114 in total.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

WRAPPER = "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/scripts/dev.sh"
EVALUATOR = "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/agent/evaluate_reharmonize_agent.py"
BACKEND = "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/backend"
COMPARISON = Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/comparison-plan.json")
EXPANSION = Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/expansion-plan.json")
META_A = Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-a/results.json")
INPUTS = {
    "b": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-b.json",
    "c": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-c.json",
    "d": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-d.json",
    "e": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-e.json",
    "f": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-f.json",
    "g": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-g.json",
    "h": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-h.json",
    "i": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-i.json",
    "j": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-j.json",
    "k": "/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases-k.json",
}
WORK = [
    ("b","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-b"),
    ("c","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-c"),
    ("d","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-d"),
    ("d","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-d"),
    ("e","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-e"),
    ("e","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-e"),
    ("f","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-f"),
    ("f","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-f"),
    ("g","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-g"),
    ("g","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-g"),
    ("h","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-h"),
    ("h","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-h"),
    ("i","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-i"),
    ("i","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-i"),
    ("j","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-j"),
    ("j","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-j"),
    ("k","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-k"),
    ("k","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-k"),
]


def compact(report):
    return {k:report["summary"][k] for k in ("scheduledRuns","startedRuns","passedRuns","statusCounts","accountedCostUsd","httpAttempts","extraAttemptsWithinToolTurns")}


def main():
    comparison=json.loads(COMPARISON.read_text())
    expansion=json.loads(EXPANSION.read_text())
    assert (len(WORK)+1)*6 == comparison["totalCapUsd"]+expansion["expansionAllocationUsd"] == 114 <= 120
    assert hashlib.sha256(Path(EVALUATOR).read_bytes()).hexdigest()==comparison["evaluatorSha256"]==expansion["evaluatorSha256"]
    hashes={b["id"]:b["sha256"] for b in comparison["batches"]+expansion["batches"]}
    for batch,path in INPUTS.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==hashes[batch]
    initial=json.loads(META_A.read_text())
    if len(initial["runs"])!=40 or any(r["status"]=="not_started" for r in initial["runs"]) or initial["ledgerTotals"]["outstandingUsd"]:
        raise ValueError("Finish and settle meta-a before starting the remaining campaign")
    if any(Path(out).exists() for _,_,out in WORK):
        raise ValueError("Refusing to rerun any existing output directory")
    spent=initial["ledgerTotals"]["accountedCostUsd"]
    completed=40
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",UV_NO_SYNC="1",UV_OFFLINE="1")
    active=[None]
    stop=[False]
    def stop_campaign(signum, frame):
        stop[0]=True
        if active[0] is not None and active[0].poll() is None:
            active[0].send_signal(signal.SIGTERM)
    signal.signal(signal.SIGINT,stop_campaign)
    signal.signal(signal.SIGTERM,stop_campaign)
    for batch,provider,out in WORK:
        if stop[0]:
            raise RuntimeError("Campaign stopped before the next batch")
        command=["bash",WRAPPER,"py",EVALUATOR,"run","--backend",BACKEND,"--cases",INPUTS[batch],
                 "--provider",provider,"--out",out,"--approved-max-usd","6","--cases-sha256",hashes[batch],
                 "--service-sha256",comparison["serviceSha256"],"--checkpoint-sha256",comparison["checkpointSha256"]]
        print(json.dumps({"starting":Path(out).name,"completedNewRuns":completed,"accountedNewCostUsd":round(spent,8)}),flush=True)
        child=subprocess.Popen(command,env=env)
        active[0]=child
        report_path=Path(out)/"results.json"
        while child.poll() is None:
            time.sleep(20)
            if report_path.exists():
                report=json.loads(report_path.read_text())
                print(json.dumps({"active":Path(out).name,**compact(report)}),flush=True)
        if child.returncode not in (0,1) or not report_path.exists():
            raise RuntimeError("Evaluator did not create a reviewable result; stopping future batches")
        report=json.loads(report_path.read_text())
        active[0]=None
        if report["ledgerTotals"]["outstandingUsd"] or report.get("stoppedReason"):
            raise RuntimeError("An interrupted or unsettled evaluator requires review; no replacement run is made")
        spent+=report["ledgerTotals"]["accountedCostUsd"]
        completed+=report["summary"]["startedRuns"]
        assert spent<=114
        permanent=[r for r in report["runs"] if (r.get("error") or {}).get("statusCode") in (401,402,403) or (r.get("error") or {}).get("type")=="CreditExhausted"]
        if permanent:
            raise RuntimeError("Provider access or credits failed; stopping future paid batches")
        print(json.dumps({"finished":Path(out).name,"completedNewRuns":completed,"accountedNewCostUsd":round(spent,8),**compact(report)}),flush=True)
    print(json.dumps({"campaignFinished":True,"scheduledNewRuns":760,"startedNewRuns":completed,"accountedNewCostUsd":round(spent,8),"reservedCeilingUsd":114}),flush=True)


if __name__=="__main__":
    main()
