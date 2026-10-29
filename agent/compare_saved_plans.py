"""Compare saved rules/Meta planner traces without generating music or calling an API.

Reads the two result files and their request fixtures, validates their pairing and
rechecks plans with the product validator. Prints Markdown only; no files, dates,
keys or ledger contents are written. This is a structural and diagnostic comparison,
not a listening test or proof of musical quality.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.models.plan import PlanRequest, PlanSectionResult, SongPlan  # noqa: E402
from app.services.planner import DIATONIC_GENRES, section_report, validate_plan  # noqa: E402


def read_runs(path: Path, expected: str) -> dict[str, dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("planner") != expected:
        raise ValueError(f"Expected a {expected} planner result file")
    runs = document["runs"]
    names = [run["request"] for run in runs]
    if not names or len(set(names)) != len(names):
        raise ValueError("Result files must contain nonempty, uniquely named runs")
    return dict(zip(names, runs))


def chords(section: dict) -> list[str | None]:
    measures = section["suggestions"][0]["chords"]
    return [symbol for bar in sorted(measures, key=int) for symbol in measures[bar]]


def compare(rules: dict[str, dict], meta: dict[str, dict], requests: Path) -> tuple[dict, dict]:
    if rules.keys() != meta.keys():
        raise ValueError("The result files must contain the same request names")
    fixtures = {
        name: PlanRequest.model_validate(json.loads((requests / f"{name}.json").read_text(encoding="utf-8")))
        for name in rules
    }
    summaries = []
    for runs in (rules, meta):
        result = Counter()
        section_sources = Counter()
        distinct_types, pair_agreements, durations, costs = [], [], [], []
        diatonic_shares = {}
        not_accepted = []
        for name, run in runs.items():
            req = fixtures[name]
            trace = run["trace"]
            recorded = (run["genre"], run["key"], run["sketchBars"], run["targetBars"],
                        run["wantOutro"], run["contrast"])
            expected = (req.genre, req.key, len(req.measures), req.targetBars, req.wantOutro, req.contrast)
            if recorded != expected:
                raise ValueError(f"Recorded request metadata does not match fixture: {name}")
            plan = SongPlan.model_validate(trace["plan"]) if trace["plan"] is not None else None
            result["runs"] += 1
            result["completed"] += trace["status"] == "ok"
            result["valid"] += plan is not None and not validate_plan(plan, req)
            result["length"] += plan is not None and len(req.measures) + sum(s.bars for s in plan.sections) == req.targetBars
            distinct_types.append(len({s.type for s in plan.sections}) if plan else 0)
            durations.append(trace["elapsedMs"] / 1000)
            costs.append(trace["spendUsd"])
            result["calls"] += len(trace["calls"])
            result["regenerated_runs"] += any(s["regenerated"] for s in trace["sections"])
            if trace["judge"] and trace["judge"][-1]["decision"] != "accept":
                not_accepted.append(name)
            outside = model_slots = 0
            for index, raw in enumerate(trace["sections"]):
                section_sources[raw["source"]] += 1
                result["sections"] += 1
                result["chord_slots"] += raw["chordCount"]
                result["rule_slots"] += len(raw["rulesSlots"])
                result["regenerated_sections"] += raw["regenerated"]
                report = section_report(index, PlanSectionResult.model_validate(raw), [], trace["key"])
                model_slots += report.modelSlots
                # section_report rounds the share to 3 decimals; <=64 slots per
                # section makes rounding back to an integer count unambiguous.
                outside += round(report.outsideKey * (report.modelSlots - report.emptySlots))
                result["empty_slots"] += report.emptySlots
            if req.genre in DIATONIC_GENRES:
                result["diatonic_runs"] += 1
                result["diatonic_slots"] += model_slots
                result["diatonic_outside"] += outside
                diatonic_shares[name] = outside / model_slots if model_slots else 0
            for first, second in combinations(trace["sections"], 2):
                if (first["sectionType"], first["bars"]) != (second["sectionType"], second["bars"]):
                    continue
                a, b = chords(first), chords(second)
                result["repeat_pairs"] += 1
                result["identical_pairs"] += a == b
                pair_agreements.append(sum(x == y for x, y in zip(a, b)) / len(a))
        summaries.append({
            **result, "section_sources": dict(section_sources), "distinct_types": statistics.fmean(distinct_types),
            "median_s": statistics.median(durations), "cost_total": sum(costs), "cost_mean": statistics.fmean(costs),
            "pair_agreement": statistics.fmean(pair_agreements) if pair_agreements else 0,
            "diatonic_shares": diatonic_shares, "not_accepted": not_accepted,
        })
    return tuple(summaries)


def fraction(hits: int, total: int) -> str:
    return f"{hits}/{total} ({hits / total:.1%})" if total else "n/a"


def report(rules: dict, meta: dict) -> str:
    rows = [
        ("Recorded completed runs", *(fraction(s["completed"], s["runs"]) for s in (rules, meta))),
        ("Plans passing the current validator", *(fraction(s["valid"], s["runs"]) for s in (rules, meta))),
        ("Requested total bar count", *(fraction(s["length"], s["runs"]) for s in (rules, meta))),
        ("Mean distinct section types", *(f'{s["distinct_types"]:.2f}' for s in (rules, meta))),
        ("Sections recorded as AI generated", *(fraction(s["section_sources"].get("ai", 0), s["sections"]) for s in (rules, meta))),
        ("Rule-forced chord slots", *(fraction(s["rule_slots"], s["chord_slots"]) for s in (rules, meta))),
        ("Out-of-key model slots in diatonic genres", *(fraction(s["diatonic_outside"], s["diatonic_slots"]) for s in (rules, meta))),
        ("Empty model slots", *(str(s["empty_slots"]) for s in (rules, meta))),
        ("Identical sequences among same-type/length section pairs", *(fraction(s["identical_pairs"], s["repeat_pairs"]) for s in (rules, meta))),
        ("Mean symbol agreement in those pairs", *(f'{s["pair_agreement"]:.1%}' for s in (rules, meta))),
        ("Runs with regenerated sections", *(fraction(s["regenerated_runs"], s["runs"]) for s in (rules, meta))),
        ("Last judge still requested regeneration", "n/a (no judge)", fraction(len(meta["not_accepted"]), meta["runs"])),
        ("Recorded median total latency", *(f'{s["median_s"]:.3f} s' for s in (rules, meta))),
        ("Recorded mean Meta API cost per run", *(f'${s["cost_mean"]:.6f}' for s in (rules, meta))),
        ("Recorded total Meta API cost", *(f'${s["cost_total"]:.6f}' for s in (rules, meta))),
    ]
    lines = ["| Metric | Rules planner | Muse Spark planner (medium) |", "|---|---:|---:|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    before, after = rules["diatonic_shares"], meta["diatonic_shares"]
    lower = sum(after[name] < before[name] for name in before)
    equal = sum(after[name] == before[name] for name in before)
    higher = len(before) - lower - equal
    lines += ["", f"Paired diatonic requests ({len(before)}): Meta out-of-key share lower {lower}, equal {equal}, higher {higher}.",
              "", "Completed traces whose last judge requested regeneration:",
              *(f"- `{name}`" for name in meta["not_accepted"]), "",
              "Additional API calls: 0. Additional API cost: $0. No music generated; no listening test performed."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    args = parser.parse_args()
    print(report(*compare(read_runs(args.rules, "rules"), read_runs(args.meta, "meta"), args.requests)))


if __name__ == "__main__":
    main()
