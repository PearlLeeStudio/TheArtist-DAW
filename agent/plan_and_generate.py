"""Evaluation harness for the song planner: the fixed requests through the real service.

Every request in a folder goes through app.services.planner.complete_form in-process (no
server): with --planner meta, Muse Spark plans the form, the validator checks it and sends
its issues back, the chord model writes every section and the judge decides; with
--planner rules, the genre-default form goes through the same validator and generation
with no LLM call (the "before"). --effort sets the planning effort (revisions and the
judge keep the planner's own efforts), so the effort comparison changes one thing.

One results file per invocation, <out>/<planner>[-<effort>].json, rewritten after every
run so an interrupted invocation keeps what it finished. A run records the first-pass
validator result, the revisions, the final validity, the judge decisions and the
regenerated sections, plan-only and total latency, cost, request ids and the whole
trace; never a key, never an absolute local path (the file is checked before it is
written). The invocation stops before a run that could pass --max-usd (a run reserves
at most planner.MAX_RUN_USD) and after a failure every later run would repeat (Meta
disabled, missing configuration, the ledger cap); the product ledger's caps still apply
underneath. --report prints the summary tables from the results written so far.

    bash scripts/dev.sh py agent/plan_and_generate.py --requests experiments/agent_eval/requests \\
        --out experiments/agent_eval/results --planner meta [--effort low|medium|high] [--max-usd 6]
    ... --planner rules                      no Meta call
    ... --planner meta --effort high --subset   the fixed effort-comparison subset only
    ... --report --out experiments/agent_eval/results

(`uv run --directory backend python ../agent/plan_and_generate.py …` from a checkout.)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))  # the app package; this script is run by path, not with -m

from app.models.plan import PLANNERS, PlanRequest, PlanTrace  # noqa: E402
from app.services import planner  # noqa: E402
from app.services.llm import LLMError  # noqa: E402

DEFAULT_MAX_USD = 6.0
EFFORTS = ("low", "medium", "high")
KINDS = ("new", "complete", "tight")  # a request file's prefix: new song, completion, tight completion
# The fixed subset of the plan-effort comparison: two new songs, the minor-key sketch, three tight requests
EFFORT_SUBSET = ("new_pop_32", "new_jazz_64", "complete_hiphop_amin_8bar_32", "tight_blues_e_12bar_48_outro",
                 "tight_folk_g_14bar_16_outro", "tight_pop_c_10bar_32_high")
# Failure kinds every later run would repeat, so the invocation stops after one
STOP_KINDS = ("disabled", "config", "budget")
# Consecutive failed runs without a single request id (the provider never answered: unreachable,
# or every call timed out) after which the invocation stops instead of settling more reservations
UNANSWERED_STOP = 2
KEY_VARS = ("MODEL_API_KEY", "BASETEN_API_KEY", "FIREWORKS_API_KEY", "LLM_API_KEY", "LLM_JUDGE_API_KEY")
_FILE_ORDER = ("rules", "meta-low", "meta-medium", "meta-high")


def _kind(name: str) -> str:
    kind = name.split("_", 1)[0]
    if kind not in KINDS:
        raise ValueError(f"{name}: a request file starts with one of {', '.join(KINDS)} and an underscore")
    return kind


def load_requests(folder: Path, names: tuple[str, ...] | None = None) -> list[tuple[str, dict[str, Any]]]:
    """(name, request body) for every *.json in the folder, in name order; each body is checked
    against the request model so a broken fixture fails here, not in the middle of a billed run."""
    paths = sorted(folder.glob("*.json"))
    if names is not None:
        missing = [name for name in names if not (folder / f"{name}.json").is_file()]
        if missing:
            raise FileNotFoundError(f"no request file for {', '.join(missing)} in {folder}")
        paths = [folder / f"{name}.json" for name in names]
    if not paths:
        raise FileNotFoundError(f"no *.json request files in {folder}")
    requests = []
    for path in paths:
        body = json.loads(path.read_text(encoding="utf-8"))
        _kind(path.stem)
        PlanRequest.model_validate(body)
        requests.append((path.stem, body))
    return requests


# --- One run ---


def run_one(name: str, body: dict[str, Any], planner_name: str) -> dict[str, Any]:
    """complete_form over one request, as the API would run it, reduced to the numbers the
    summary needs plus the whole trace."""
    request = PlanRequest.model_validate({**body, "planner": planner_name})
    events: list[tuple[str, int]] = []
    trace = planner.complete_form(request, lambda event, payload: events.append((event, payload["t_ms"])))
    return record(name, request, trace, events)


def record(name: str, request: PlanRequest, trace: PlanTrace, events: list[tuple[str, int]]) -> dict[str, Any]:
    first = trace.validation[0] if trace.validation else None
    plan_calls = [call for call in trace.calls if call.step == "plan_song"]
    # The plan phase ends at its last validation; the event clock starts with the run
    plan_ms = next((t for event, t in reversed(events) if event == "validate"), None)
    return {
        "request": name, "kind": _kind(name), "genre": request.genre, "key": request.key,
        "sketchBars": len(request.measures), "targetBars": request.targetBars,
        "wantOutro": request.wantOutro, "contrast": request.contrast,
        "status": trace.status, "error": trace.error.model_dump() if trace.error else None,
        "firstPass": {"ok": first.ok, "errors": [issue.code for issue in first.errors]} if first else None,
        "revisions": max(0, len(trace.validation) - 1),
        "planValid": bool(trace.validation) and trace.validation[-1].ok,
        "plan": [[s.type, s.bars, s.cadence] for s in trace.plan.sections] if trace.plan else None,
        "cites": sum(len(s.cites) for s in trace.plan.sections) if trace.plan else 0,
        "citeErrorsFirstPass": sum(1 for issue in first.errors if issue.code.startswith("cite")) if first else 0,
        "sections": [[s.sectionType, s.bars, s.source, s.modelUsed, s.regenerated] for s in trace.sections],
        "judge": [decision.decision for decision in trace.judge],
        "regenerated": sum(1 for s in trace.sections if s.regenerated),
        "planMs": plan_ms, "totalMs": trace.elapsedMs, "metaMs": trace.metaMs, "generationMs": trace.generationMs,
        "costUsd": trace.spendUsd, "planCostUsd": round(sum(call.costUsd for call in plan_calls), 8),
        "reservedUsd": trace.reservedUsd, "calls": len(trace.calls),
        "requestIds": [call.requestId for call in trace.calls if call.requestId],
        "events": events, "trace": trace.model_dump(mode="json"),
    }


def _line(index: int, total: int, run: dict[str, Any]) -> str:
    first = run["firstPass"]
    first_text = "-" if first is None else ("ok" if first["ok"] else ",".join(first["errors"]) or "rejected")
    plan_s = "-" if run["planMs"] is None else f"{run['planMs'] / 1000:.1f} s"
    outcome = "ok " if run["status"] == "ok" else f"ERR {run['error']['kind']}: {run['error']['message']}"
    return (f"{index:2d}/{total} {run['request']:32s} first-pass {first_text:14s} rev {run['revisions']} "
            f"plan {'valid' if run['planValid'] else 'invalid':7s} judge {','.join(run['judge']) or '-':20s} "
            f"regen {run['regenerated']}  plan {plan_s:>7s}  total {run['totalMs'] / 1000:5.1f} s  "
            f"${run['costUsd']:.4f}  ids {len(run['requestIds'])}  {outcome}")


# --- The invocation ---


def _client_facts(role: str) -> dict[str, Any]:
    """What the role's client is, without its key; the failure text when it cannot be built."""
    try:
        config = planner.get_client(role).config
    except LLMError as exc:
        return {"error": planner._message(exc)}
    return {"provider": config.provider, "model": config.model, "priceSource": config.price_source,
            "keySource": config.key_source, "keySet": bool(config.api_key)}


def ledger_totals() -> dict[str, Any]:
    """spent / cap of the ledger behind each role (one entry when the judge shares the default ledger)."""
    totals: dict[str, Any] = {}
    seen: set[str] = set()
    for role in ("default", "judge"):
        try:
            ledger = planner.get_client(role).ledger
            snapshot = ledger.snapshot()
        except LLMError as exc:
            totals[role] = {"error": planner._message(exc)}
            continue
        if snapshot["path"] in seen:
            totals[role] = {"sharedWith": "default"}
            continue
        seen.add(snapshot["path"])
        totals[role] = {"spentUsd": snapshot["spent_usd"], "capUsd": snapshot["cap_usd"],
                        "outstandingUsd": snapshot["outstanding_usd"]}
    return totals


def _ledger_line(totals: dict[str, Any]) -> str:
    parts = []
    for role, entry in totals.items():
        if "spentUsd" in entry:
            parts.append(f"{role} ${entry['spentUsd']:.4f} of ${entry['capUsd']:.2f}")
        elif "sharedWith" in entry:
            parts.append(f"{role} shares the {entry['sharedWith']} ledger")
        else:
            parts.append(f"{role} unavailable ({entry['error']})")
    return "; ".join(parts)


def scrubbed(text: str) -> str:
    """The results text with the local paths replaced; a key in it is a bug, so nothing is written."""
    for var in KEY_VARS:
        key = os.environ.get(var, "")
        if len(key) >= 8 and key in text:
            raise RuntimeError(f"the value of {var} appeared in the results; nothing was written")
    return text.replace(str(REPO_ROOT), "<repo>").replace(str(Path.home()), "~")


def write_results(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scrubbed(json.dumps(document, indent=1, ensure_ascii=False)) + "\n", encoding="utf-8")


def results_name(planner_name: str, effort: str | None) -> str:
    """rules.json, or meta-<plan effort>.json with the planner's own effort when none was given."""
    if planner_name != "meta":
        return f"{planner_name}.json"
    return f"meta-{effort or planner.PLAN_EFFORT}.json"


def run_all(requests: list[tuple[str, dict[str, Any]]], planner_name: str, effort: str | None,
            max_usd: float, out_path: Path, say=print) -> dict[str, Any]:
    """Every request in order under the spend limit; the results document, also written to out_path."""
    limits = {"maxUsd": max_usd, "maxRunUsd": planner.MAX_RUN_USD, "maxRequestUsd": planner.MAX_REQUEST_USD,
              "maxMetaCalls": planner.MAX_META_CALLS, "maxRevisions": planner.MAX_REVISIONS,
              "maxJudgments": planner.MAX_JUDGMENTS, "runBudgetS": planner.RUN_BUDGET_S,
              "metaBudgetS": planner.META_BUDGET_S, "ownModelBudgetS": planner.OWN_MODEL_BUDGET_S}
    plan_effort = effort or planner.PLAN_EFFORT
    document: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "planner": planner_name,
        "effort": plan_effort if planner_name == "meta" else None,
        "efforts": {"plan": plan_effort, "revise": planner.REVISE_EFFORT, "judge": planner.JUDGE_EFFORT},
        "limits": limits, "clients": {role: _client_facts(role) for role in ("default", "judge")},
        "ledger": {"before": ledger_totals(), "after": None},
        "requests": len(requests), "spentUsd": 0.0, "stopped": None, "runs": [],
    }
    say(f"planner {planner_name}" + (f", plan effort {plan_effort}" if planner_name == "meta" else "")
        + f", {len(requests)} requests, --max-usd ${max_usd:.2f}")
    say(f"ledger before: {_ledger_line(document['ledger']['before'])}")
    previous_effort = planner.PLAN_EFFORT
    planner.PLAN_EFFORT = plan_effort
    unanswered = 0
    try:
        for index, (name, body) in enumerate(requests, 1):
            if planner_name == "meta" and document["spentUsd"] + planner.MAX_RUN_USD > max_usd + 1e-9:
                document["stopped"] = (f"spent ${document['spentUsd']:.4f} + one run's cap ${planner.MAX_RUN_USD:.2f} "
                                       f"would pass --max-usd ${max_usd:.2f}; {len(requests) - index + 1} requests not run")
                break
            run = run_one(name, body, planner_name)
            document["runs"].append(run)
            document["spentUsd"] = round(document["spentUsd"] + run["costUsd"], 8)
            document["ledger"]["after"] = ledger_totals()
            write_results(out_path, document)
            say(_line(index, len(requests), run))
            if run["error"] and run["error"]["kind"] in STOP_KINDS:
                document["stopped"] = (f"{run['error']['kind']} failure every later run would repeat; "
                                       f"{len(requests) - index} requests not run")
                break
            unanswered = unanswered + 1 if run["error"] and run["calls"] and not run["requestIds"] else 0
            if unanswered >= UNANSWERED_STOP:
                document["stopped"] = (f"{unanswered} runs in a row got no answer from the provider; "
                                       f"{len(requests) - index} requests not run")
                break
    finally:
        planner.PLAN_EFFORT = previous_effort
    document["ledger"]["after"] = ledger_totals()
    write_results(out_path, document)
    failed = sum(1 for run in document["runs"] if run["status"] != "ok")
    say(f"{len(document['runs'])} runs, {failed} failed, spent ${document['spentUsd']:.4f} on this invocation"
        + (f"; stopped: {document['stopped']}" if document["stopped"] else ""))
    say(f"ledger after: {_ledger_line(document['ledger']['after'])}")
    return document


# --- The report ---


def _percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * share
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _rate(hits: int, total: int) -> str:
    return "-" if total == 0 else f"{hits}/{total} ({100 * hits / total:.0f}%)"


def _seconds(values: list[int | float | None]) -> str:
    present = [value / 1000 for value in values if value is not None]
    if not present:
        return "-"
    return f"{_percentile(present, 0.5):.1f} / {_percentile(present, 0.95):.1f}"


def metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """The summary numbers over a set of runs; failed runs count as not valid, and their cost counts."""
    n = len(runs)
    tight = [run for run in runs if run["kind"] == "tight"]
    sketched = [run for run in runs if run["kind"] != "new" and run["plan"]]
    planned = [run for run in runs if run["plan"]]
    completed = [run for run in runs if run["status"] == "ok"]
    failures: dict[str, int] = {}
    for run in runs:
        if run["error"]:
            failures[run["error"]["kind"]] = failures.get(run["error"]["kind"], 0) + 1
    return {
        "n": n,
        "firstPass": _rate(sum(1 for run in runs if run["firstPass"] and run["firstPass"]["ok"]), n),
        "planValid": _rate(sum(1 for run in runs if run["planValid"]), n),
        "meanRevisions": f"{statistics.fmean(run['revisions'] for run in runs):.2f}" if runs else "-",
        "completed": _rate(len(completed), n),
        "regenerate": _rate(sum(1 for run in completed if "regenerate" in run["judge"]), len(completed)),
        "tightFirst": _rate(sum(1 for run in tight if run["firstPass"] and run["firstPass"]["ok"]), len(tight)),
        "tightFinal": _rate(sum(1 for run in tight if run["planValid"] and run["status"] == "ok"), len(tight)),
        "cites": f"{statistics.fmean(run['cites'] for run in sketched):.1f}" if sketched else "-",
        "citeErrors": _rate(sum(1 for run in sketched if run["citeErrorsFirstPass"]), len(sketched)),
        "distinctTypes": f"{statistics.fmean(len({s[0] for s in run['plan']}) for run in planned):.1f}" if planned else "-",
        "planLatency": _seconds([run["planMs"] for run in runs]),
        "totalLatency": _seconds([run["totalMs"] for run in runs]),
        "costPerRun": f"{statistics.fmean(run['costUsd'] for run in runs):.4f}" if runs else "-",
        "planCostPerRun": f"{statistics.fmean(run['planCostUsd'] for run in runs):.4f}" if runs else "-",
        "costTotal": f"{sum(run['costUsd'] for run in runs):.4f}",
        "failures": ", ".join(f"{kind} {count}" for kind, count in sorted(failures.items())) or "none",
    }


_COLUMNS = (
    ("N", "n"), ("first-pass valid", "firstPass"), ("valid after revision", "planValid"),
    ("mean revisions", "meanRevisions"), ("completed", "completed"), ("regenerate rate", "regenerate"),
    ("tight: first-pass / final", "tightFirstFinal"), ("cites / plan", "cites"), ("cite errors (first pass)", "citeErrors"),
    ("distinct types / plan", "distinctTypes"), ("plan p50 / p95 (s)", "planLatency"), ("total p50 / p95 (s)", "totalLatency"),
    ("USD / run", "costPerRun"), ("plan USD / run", "planCostPerRun"), ("USD total", "costTotal"), ("failures", "failures"),
)


def _row(label: str, values: dict[str, Any]) -> str:
    values = {**values, "tightFirstFinal": f"{values['tightFirst']} / {values['tightFinal']}"}
    return "| " + " | ".join([label, *(str(values[key]) for _, key in _COLUMNS)]) + " |"


def _table(rows: list[tuple[str, dict[str, Any]]]) -> str:
    header = "| run | " + " | ".join(name for name, _ in _COLUMNS) + " |"
    rule = "|---|" + "|".join("---:" if key not in ("failures",) else "---" for _, key in _COLUMNS) + "|"
    return "\n".join([header, rule, *(_row(label, values) for label, values in rows)])


def _label(document: dict[str, Any]) -> str:
    return "rules" if document["planner"] == "rules" else f"meta, plan effort {document['effort']}"


def report(out_dir: Path) -> str:
    """Markdown tables over every results file in the folder: one row per invocation, the effort
    comparison on the fixed subset, the before/after pair, and the per-request outcomes."""
    documents = {}
    for path in sorted(out_dir.glob("*.json")):
        documents[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    if not documents:
        raise FileNotFoundError(f"no results files in {out_dir}")
    order = [name for name in _FILE_ORDER if name in documents] + [name for name in documents if name not in _FILE_ORDER]
    lines = ["## Invocations", "", _table([(f"`{name}.json` ({_label(documents[name])})", metrics(documents[name]["runs"]))
                                            for name in order]), ""]
    for name in order:
        document = documents[name]
        clients = "; ".join(f"{role}: {facts.get('provider')} {facts.get('model')}" if "provider" in facts
                            else f"{role}: {facts.get('error')}" for role, facts in document["clients"].items())
        lines.append(f"- `{name}.json`: {document['ts']}, {len(document['runs'])} of {document['requests']} requests"
                     + (f", stopped: {document['stopped']}" if document["stopped"] else "") + f"; clients {clients}; "
                     f"efforts plan {document['efforts']['plan']} / revise {document['efforts']['revise']} / judge "
                     f"{document['efforts']['judge']}; ledger before {_ledger_line(document['ledger']['before'])}, "
                     f"after {_ledger_line(document['ledger']['after'] or {})}")
    effort_rows = []
    for effort in EFFORTS:
        document = documents.get(f"meta-{effort}")
        if document:
            subset = [run for run in document["runs"] if run["request"] in EFFORT_SUBSET]
            if subset:
                effort_rows.append((f"plan effort {effort}", metrics(subset)))
    if effort_rows:
        lines += ["", f"## Plan effort on the fixed subset ({', '.join(EFFORT_SUBSET)})", "", _table(effort_rows)]
    if "rules" in documents and "meta-medium" in documents:
        lines += ["", "## Before / after on the full set", "",
                  _table([("rules (before)", metrics(documents["rules"]["runs"])),
                          ("meta, plan effort medium (after)", metrics(documents["meta-medium"]["runs"]))])]
    for name in order:
        lines += ["", f"## Per request: `{name}.json`", "",
                  "| request | kind | first pass | revisions | plan | judge | regenerated | plan (s) | total (s) | USD | status |",
                  "|---|---|---|---:|---|---|---:|---:|---:|---:|---|"]
        for run in documents[name]["runs"]:
            first = run["firstPass"]
            first_text = "-" if first is None else ("ok" if first["ok"] else ", ".join(first["errors"]))
            plan_text = ", ".join(f"{kind} {bars}" for kind, bars, _ in run["plan"]) if run["plan"] else "-"
            plan_s = "-" if run["planMs"] is None else f"{run['planMs'] / 1000:.1f}"
            status = run["status"] + (f" ({run['error']['kind']}: {run['error']['message']})" if run["error"] else "")
            lines.append(f"| {run['request']} | {run['kind']} | {first_text} | {run['revisions']} | {plan_text} | "
                         f"{', '.join(run['judge']) or '-'} | {run['regenerated']} | {plan_s} | "
                         f"{run['totalMs'] / 1000:.1f} | {run['costUsd']:.4f} | {status} |")
    return "\n".join(lines) + "\n"


# --- Entry point ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed planner requests through the planner service.")
    parser.add_argument("--requests", type=Path, default=REPO_ROOT / "experiments" / "agent_eval" / "requests",
                        help="folder of request files (*.json in the planner's request format)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "agent_eval" / "results",
                        help="folder of the results files")
    parser.add_argument("--planner", choices=PLANNERS,
                        help="meta: Muse Spark plans and judges; rules: the genre-default form, no Meta call")
    parser.add_argument("--effort", choices=EFFORTS, help="planning effort (meta only); default: the planner's own")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD,
                        help=f"stop before a run that could pass this spend (default {DEFAULT_MAX_USD:g})")
    parser.add_argument("--subset", action="store_true", help="only the fixed effort-comparison subset")
    parser.add_argument("--report", action="store_true", help="print the summary tables from --out and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s | %(message)s")

    if args.report:
        print(report(args.out), end="")
        return 0
    if args.planner is None:
        parser.error("--planner is required unless --report is given")
    if args.planner == "rules" and args.effort:
        parser.error("--effort applies to the meta planner only")
    if not (math.isfinite(args.max_usd) and args.max_usd > 0):
        parser.error("--max-usd must be a positive number")
    requests = load_requests(args.requests, EFFORT_SUBSET if args.subset else None)
    out = args.out / results_name(args.planner, args.effort)
    document = run_all(requests, args.planner, args.effort, args.max_usd, out)
    print(f"wrote {out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}")
    incomplete = document["stopped"] or any(run["status"] != "ok" for run in document["runs"])
    return 1 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
