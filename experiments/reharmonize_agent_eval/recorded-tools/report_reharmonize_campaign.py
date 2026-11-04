"""Offline verification and paired reporting; never issues model requests."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import runpy
from collections import Counter

SPEC=importlib.util.spec_from_file_location("evaluation","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/agent/evaluate_reharmonize_agent.py")
ev=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)
BACKEND=Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/backend")
RUNNER=runpy.run_path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/agent/run_reharmonize_campaign.py")
INPUTS={"a":"/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/cases.json",**RUNNER["INPUTS"]}
WORK=[
    ("a","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-a"),
    ("b","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-b"),
    ("c","baseten","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/open-c"),
    ("a","meta","/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/meta-a"),
    *RUNNER["WORK"],
]
OUT_JSON=Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/extended-summary.json")
OUT_MD=Path("/Volumes/LeeSSD/PearlLeeDocs/2026_MakeItHappen/raw/TheArtist/MetaAIHackathon/experiments/reharmonize_agent_eval/extended-summary.md")


def trace_summary(runs):
    """Describe saved decisions and feedback without replaying any search."""
    requested,executed,family_sets=Counter(),Counter(),Counter()
    feedback_runs=backed_offers=offered=scored_offers=0
    for run in runs:
        feedback={}
        for turn in run.get("turns",[]):
            for call in turn.get("reply",{}).get("data",{}).get("calls",[]):
                requested[call["name"]]+=1
                if call["name"]=="search_substitutions":
                    families=call.get("arguments",{}).get("families",[])
                    family_sets[" + ".join(sorted(families)) or "default"]+=1
            for message in turn.get("messages",[]):
                if message.get("role")=="tool":
                    try:
                        body=json.loads(message["content"])
                    except (ValueError,TypeError):
                        continue
                    if isinstance(body,dict) and isinstance(body.get("candidates"),list):
                        feedback[message["tool_call_id"]]=body["candidates"]
        feedback_runs+=bool(feedback)
        response=run.get("response",{})
        executed.update(response.get("toolCalls",[]))
        candidates=response.get("candidates",[])
        offered+=len(candidates)
        scored_offers+=sum(isinstance(c.get("modelScore"),(int,float)) and math.isfinite(c["modelScore"]) for c in candidates)
        # Compare full candidate bodies as well as IDs: duplicate IDs alone are
        # insufficient evidence that an offered version came from tool feedback.
        seen={ev.canonical(c) for pool in feedback.values() for c in pool}
        backed_offers+=bool(candidates) and all(ev.canonical(c) in seen for c in candidates)
    return {"runs":len(runs),"modelRequestedToolCalls":dict(requested),"returnedProductToolCalls":dict(executed),
        "requestedSearchFamilySets":dict(family_sets),"runsWithSearchFeedbackInModelRequest":feedback_runs,
        "runsWhoseEntireOfferMatchesSavedSearchFeedback":backed_offers,"offeredCandidates":offered,
        "offeredCandidatesWithFiniteF1Score":scored_offers,
        "scope":"Descriptive saved-trace counts, not additional pass criteria or evidence of musical preference. Requested calls may include calls that failed; returned product calls cover returned responses."}


def verify(api,path,expected_identity,expected_requests,provider):
    report=json.loads(path.read_text())
    assert report["identity"]==expected_identity
    assert report["provider"]==provider and report["model"]==ev.MODELS[provider]
    assert report["reasoningEffort"]=="low" and report["approvedMaxUsd"]==6
    runs=report["runs"]
    assert [(r["caseId"],r["repeat"],r["request"]) for r in runs]==expected_requests
    assert not any(r["status"]=="not_started" for r in runs), "Unstarted rows remain; report the incomplete campaign explicitly"
    assert ev.summary(runs)==report["summary"]
    ledger_path=path.with_name("ledger.json")
    ledger=json.loads(ledger_path.read_text())
    entries=[entry for r in runs for entry in r.get("apiUsage",[])]
    assert ledger["entries"]==entries
    assert ev.billing(entries)==report["ledgerTotals"]
    assert report["ledgerTotals"]["outstandingUsd"]==0
    assert report["ledgerTotals"]["accountedCostUsd"]<=6
    for r in runs:
        assert len(r["httpAttempts"])==len(r["apiUsage"])
        if "response" in r:
            if "audit" in r:
                assert ev.audit_response(api,r["request"],r["response"],r["audit"]["checks"]["inputUnchanged"],report["model"])==r["audit"]
                assert (r["status"]=="passed")==r["audit"]["passed"]
            else:
                assert r["status"]=="failed" and r.get("error"), "A missing audit must remain a recorded failure"
            request=api.Request.model_validate(r["request"])
            assert r["response"]["contextMeasures"]==[b.measure for b in api.search.context_window(request)]
        elif r["status"]=="passed":
            raise AssertionError("A passed run must retain its response and audit")
        for entry in r["apiUsage"]:
            assert "ts" not in entry
    for artifact in (path,ledger_path):
        body=artifact.read_text()
        assert not any(os.environ.get(key) and os.environ[key] in body for key in ("BASETEN_API_KEY","MODEL_API_KEY"))
    prices=report["pricesPerMillion"]
    cost=sum(((e["usage"]["prompt_tokens"]-e["usage"]["cached_tokens"])*prices["input"]+e["usage"]["cached_tokens"]*prices["cached"]+e["usage"]["completion_tokens"]*prices["output"])/1000000 for e in entries if e.get("usage"))
    assert abs(cost-report["ledgerTotals"]["returnedUsageCostUsd"])<1e-7
    return report


def main():
    if OUT_JSON.exists() or OUT_MD.exists():
        raise ValueError("Refusing to replace an existing completed report")
    api=ev.load_backend(BACKEND)
    plans=[json.loads(RUNNER["COMPARISON"].read_text()),json.loads(RUNNER["EXPANSION"].read_text())]
    frozen={b["id"]:b["sha256"] for plan in plans for b in plan["batches"]}
    identities,requests,fixtures={},{},{}
    for batch,filename in INPUTS.items():
        path=Path(filename)
        cases,identity=ev.inspect_inputs(api,BACKEND,path)
        assert identity["casesSha256"]==frozen[batch]
        for key in ("serviceSha256","checkpointSha256","evaluatorSha256"):
            assert identity[key]==plans[0][key]==plans[1][key]
        identities[batch]=identity
        requests[batch]=[(c["id"],repeat,c["request"]) for repeat in (1,2) for c in cases]
        for c in json.loads(path.read_text())["cases"]:
            assert c["id"] not in fixtures
            fixtures[c["id"]]=c
    reports,paths={},{}
    artifacts=[]
    for batch,provider,directory in WORK:
        path=Path(directory)/"results.json"
        report=verify(api,path,identities[batch],requests[batch],provider)
        reports[batch,provider]=report; paths[batch,provider]=path
        artifacts.append({"batch":batch,"provider":provider,"inputSha256":identities[batch]["casesSha256"],
            "results":path.parent.name+"/results.json","resultsSha256":ev.file_hash(path),
            "ledgerSha256":ev.file_hash(path.with_name("ledger.json"))})
    all_runs={provider:[r for batch in INPUTS for r in reports[batch,provider]["runs"]] for provider in ("baseten","meta")}
    assert len(fixtures)==220 and all(len(runs)==440 for runs in all_runs.values())
    arms={provider:ev.summary(runs) for provider,runs in all_runs.items()}
    paired={}
    for batch in INPUTS:
        paired[batch]=ev.compare(paths[batch,"baseten"],paths[batch,"meta"])
    paired_outcomes=Counter()
    for left,right in zip(all_runs["baseten"],all_runs["meta"]):
        assert (left["caseId"],left["repeat"],left["request"])==(right["caseId"],right["repeat"],right["request"])
        paired_outcomes[("open_pass" if left["status"]=="passed" else "open_fail")+"_"+("meta_pass" if right["status"]=="passed" else "meta_fail")]+=1
    failures=[{"provider":provider,"caseId":r["caseId"],"repeat":r["repeat"],"status":r["status"],"error":r.get("error"),
               "failedChecks":[k for k,v in r.get("audit",{}).get("checks",{}).items() if not v],"elapsedSeconds":r["elapsedSeconds"],
               "httpErrors":[{"attempt":i+1,"error":a["error"],"elapsedSeconds":a.get("elapsedSeconds")} for i,a in enumerate(r.get("httpAttempts",[])) if a.get("error")],
               "returnedUsageCostUsd":r["billing"]["returnedUsageCostUsd"],"unknownUsageReservationUsd":r["billing"]["unknownUsageReservationUsd"]}
              for provider,runs in all_runs.items() for r in runs if r["status"]!="passed"]
    details={}
    for provider,runs in all_runs.items():
        entries=[e for r in runs for e in r["apiUsage"]]
        ids=[e.get("request_id") for e in entries]
        details[provider]={"billing":ev.billing(entries),"requestIds":{"recorded":sum(bool(i) for i in ids),"distinct":len({i for i in ids if i}),"attempts":len(entries)},
            "tokens":{key:sum((e.get("usage") or {}).get(key,0) for e in entries) for key in ("prompt_tokens","cached_tokens","completion_tokens","reasoning_tokens")},
            "modelApproximationRuns":sum(bool(r.get("response",{}).get("modelApproximations")) for r in runs),
            "errorTypes":dict(Counter((r.get("error") or {}).get("type",r["status"]) for r in runs if r["status"]!="passed")),
            "traceObservations":trace_summary(runs)}
    strata={}
    for name,getter in (("mode",lambda c:c["key"].split()[1]),("complexity",lambda c:c["complexity"]),("changeLimit",lambda c:str(c["maxChanges"])),
                        ("meter",lambda c:"/".join(map(str,c["meter"]))),("contextBars",lambda c:str(len(c["bars"])))):
        strata[name]={value:{provider:ev.summary([r for r in runs if getter(fixtures[r["caseId"]])==value]) for provider,runs in all_runs.items()}
                      for value in sorted({getter(c) for c in fixtures.values()})}
    cohorts={name:{provider:ev.summary([r for batch in batches for r in reports[batch,provider]["runs"]]) for provider in all_runs}
             for name,batches in (("original_sixty","abc"),("systematic_expansion","defghijk"))}
    old_spend=sum(reports[b,"baseten"]["ledgerTotals"]["accountedCostUsd"] for b in "abc")
    total_spend=sum(arm["accountedCostUsd"] for arm in arms.values())
    new_spend=round(total_spend-old_spend,8)
    new_returned=round(sum(arm["returnedUsageCostUsd"] for arm in arms.values())-sum(reports[b,"baseten"]["ledgerTotals"]["returnedUsageCostUsd"] for b in "abc"),8)
    new_unknown=round(sum(arm["unknownUsageReservationUsd"] for arm in arms.values())-sum(reports[b,"baseten"]["ledgerTotals"]["unknownUsageReservationUsd"] for b in "abc"),8)
    assert abs(new_spend-new_returned-new_unknown)<1e-7
    assert new_spend<=114<=120
    report={"campaign":"reharmonize-agent-paired-expanded-v1","state":"completed","distinctAuthoredPassages":220,"repeatsPerProvider":2,
        "scheduledRunsAllProviders":880,"newRuns":760,"arms":arms,"pairedOutcomes":dict(paired_outcomes),"pairedBatches":paired,
        "cohorts":cohorts,"strata":strata,"providerDetails":details,"failures":failures,"artifacts":artifacts,
        "budget":{"approvedNewUsd":120,"allocatedMaximumNewUsd":114,"accountedNewUsd":new_spend,
                  "returnedUsageNewUsd":new_returned,"unknownUsageNewReservationUsd":new_unknown,
                  "previousOpenUsd":old_spend,"accountedAllUsd":round(total_spend,8)},
        "identity":{"evaluatorSha256":plans[0]["evaluatorSha256"],"serviceSha256":plans[0]["serviceSha256"],"checkpointSha256":plans[0]["checkpointSha256"]},
        "verification":{"allFrozenInputsMatched":True,"allSavedResponseChecksRecomputed":True,"allLedgersReconciled":True,"usageCostsRecomputed":True,"credentialsAbsent":True,"noPaidReplacementRuns":True},
        "limitations":["Authored engineering fixtures with related harmonic templates; not representative corpus samples or independent songs.",
                       "Two repeated runs per passage and provider remain grouped; automatic measurements do not establish listening preference or musical superiority.",
                       "In-process unchanged product paths. Browser UX, user application, hosted admission/availability, MIDI export and DAW playback were not exercised.",
                       "Existing Baseten JSON-tool and Meta native-tool adapters differ. Timing and cost are observations of those paths, not an isolated capability comparison.",
                       "Sequential, non-concurrent runs; original Open observations precede the comparison. Cache state and provider conditions were not randomized or equalized.",
                       "Up to 512 bars in the full request; the unchanged product exposes at most the selected eight bars plus eight surrounding bars per side to its agent/scorer.",
                       "Usage-based costs use configured published rates and are not reconciled invoices or account-balance measurements."]}
    ev.safe_write(OUT_JSON,report)
    lines=["# Expanded product-agent reliability: paired Meta paths","",
           "The unchanged Reharmonize agent was exercised on **220 authored passages, twice per provider: 880 scheduled executions**. This combines the preserved first 120 Muse Spark Open runs with 760 newly approved executions. Results below describe execution and constraints, not musical preference.","",
           "| Measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |","|---|---:|---:|"]
    for label,key in (("Started / scheduled","startedRuns"),("All execution and constraint checks passed","passedRuns"),("Passages passing both repeats","bothRepeatsPassed"),("HTTP attempts","httpAttempts"),("Extra attempts within tool turns","extraAttemptsWithinToolTurns")):
        denom=" / 440" if key in ("startedRuns","passedRuns") else " / 220" if key=="bothRepeatsPassed" else ""
        lines.append(f"| {label} | {arms['baseten'][key]}{denom} | {arms['meta'][key]}{denom} |")
    lines.extend([f"| p50 / p95 latency, all started runs | {arms['baseten']['latencySecondsAllStarted']['p50']:.3f} / {arms['baseten']['latencySecondsAllStarted']['p95']:.3f} s | {arms['meta']['latencySecondsAllStarted']['p50']:.3f} / {arms['meta']['latencySecondsAllStarted']['p95']:.3f} s |",
        f"| Returned-usage cost | $ {arms['baseten']['returnedUsageCostUsd']:.8f} | $ {arms['meta']['returnedUsageCostUsd']:.8f} |",
        f"| Unknown-usage reservations | $ {arms['baseten']['unknownUsageReservationUsd']:.8f} | $ {arms['meta']['unknownUsageReservationUsd']:.8f} |",
        f"| Accounted usage and unknown-usage reservations | $ {arms['baseten']['accountedCostUsd']:.8f} | $ {arms['meta']['accountedCostUsd']:.8f} |","",
        f"New execution accounting: **${new_spend:.8f}**, within the $114 allocation and $120 authorization. The previous Open run cost was ${old_spend:.8f}. Unknown-usage reservations are recorded separately in the machine-readable report; they are not measured provider spend.","",
        "## Per-batch results","","Each row contains 20 passages and 40 scheduled runs per provider. Batches A–C are the original 60 fixtures; D–K are the later systematic expansion, fixed before those batches produced model outputs.","",
        "| Batch / input focus | Open passed / 40 | Meta passed / 40 | Both paths passed / 40 |","|---|---:|---:|---:|"])
    axes={b["id"]:b["axis"] for b in plans[1]["batches"]}
    for batch in INPUTS:
        lines.append(f"| {batch.upper()} / {axes.get(batch,'original frozen inputs')} | {paired[batch]['arms']['baseten']['passedRuns']} | {paired[batch]['arms']['meta']['passedRuns']} | {paired[batch]['bothArmsPassed']} |")
    lines.extend(["","## Model role visible in the saved traces","",
        "These descriptive counts were derived offline from the existing records. They are not additional pass criteria and do not require new model calls. Tool messages are deduplicated within each run before checking whether full offered candidate bodies appeared in the search feedback.","",
        "| Trace observation | Open | Meta Standard |","|---|---:|---:|"])
    for label,key in (("Runs with search feedback in a model request","runsWithSearchFeedbackInModelRequest"),("Runs whose whole offer matches saved search feedback","runsWhoseEntireOfferMatchesSavedSearchFeedback"),("Offered candidates","offeredCandidates"),("Offered candidates with a finite F1 model score","offeredCandidatesWithFiniteF1Score")):
        lines.append(f"| {label} | {details['baseten']['traceObservations'][key]} | {details['meta']['traceObservations'][key]} |")
    lines.extend(["","The machine-readable report also lists the model's requested search-family combinations and tool names. This makes the division of work inspectable: Meta requests searches and selects the offer, the unchanged search tools produce bounded candidates, and the author's F1 model supplies contextual scores. These observations establish recorded execution, not that a chosen candidate sounds better."])
    lines.extend(["","## Failures and scope","",f"**Runs that did not pass every check: {len(failures)}.** Every one remains in the denominator and in [the failure list](extended-summary.json); no replacement run was used to improve the reported result.",""])
    if failures:
        lines.extend(["| Provider | Passage / repeat | Recorded error or failed checks | Run seconds | Unknown-usage reservation |","|---|---|---|---:|---:|"])
        for failure in failures:
            reason=(failure["error"] or {}).get("type") or ", ".join(failure["failedChecks"]) or failure["status"]
            lines.append(f"| {failure['provider']} | {failure['caseId']} / {failure['repeat']} | {reason} | {failure['elapsedSeconds']:.3f} | $ {failure['unknownUsageReservationUsd']:.8f} |")
        lines.extend(["","A request timeout leaves completion unproven and counts as a failed run. When a failed HTTP attempt returns no usage or request ID, those values remain unknown; its conservative reservation is reported separately from returned-usage cost. HTTP error types, attempt positions and durations remain in the JSON failure list and raw traces.",""])
    for provider in all_runs:
        label="Muse Spark Open" if provider=="baseten" else "Muse Spark 1.3 Standard"
        errors=", ".join(f"{name}: {count}" for name,count in details[provider]["errorTypes"].items()) or "no recorded errors"
        lines.append(f"- {label}: {errors}. Existing F1 chord-scoring approximations were disclosed in {details[provider]['modelApproximationRuns']} returned runs.")
    lines.append("")
    lines.extend("- "+s for s in report["limitations"])
    lines.extend(["","The separate offline boundary checks rejected **660/660 malformed inputs** without a model call. These are not included in the 880 paid-agent executions. Listening evaluation is planned separately for a research paper.","",
        "## Evidence","","- [Full combined summary, paired outcomes, strata, failures and artifact hashes](extended-summary.json).",
        "- [Original Open-only report](summary.md), preserved as its own completed cohort.",
        "- [Comparison plan](comparison-plan.json), [expansion plan](expansion-plan.json), and [offline validation checks](validation-boundaries.json).",
        "- Every full request, tool turn, response and per-attempt ledger remains in the corresponding `open-a` through `open-k` and `meta-a` through `meta-k` result folders.",
        "- Prices: [Baseten](https://www.baseten.co/pricing/) and [Meta Standard](https://dev.meta.ai/docs/pricing-rate-limits).",
        "","Input hashes, product code, evaluator and F1 checkpoint matched the frozen plans. Saved response-derived constraints were recomputed offline; per-attempt records were reconciled with each ledger and usage costs recalculated. The live input-immutability observations remain in the raw records. No API call was needed for reporting.",
        "","The earlier three Amazing Grace hosted Reharmonize runs and the separate 60 Second-ear reviews remain separate evidence. They are not pooled into this paired execution rate.",""])
    with OUT_MD.open("x") as stream:
        stream.write("\n".join(lines))
    print(json.dumps({"arms":arms,"pairedOutcomes":dict(paired_outcomes),"budget":report["budget"],"failureCount":len(failures)},indent=2))


if __name__=="__main__":
    main()
