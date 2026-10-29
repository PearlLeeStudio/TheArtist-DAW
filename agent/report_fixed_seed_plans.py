"""Validate and pool saved fixed-seed rules/Meta pairs without calling any API.

Pass each seed directory with --results and the public fixture directory with
--requests. Incomplete pairs, missing generation provenance, changed controls,
and inconsistent cost records fail closed. --out writes the Markdown report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from compare_saved_plans import DIATONIC_GENRES, compare, fraction
from plan_and_generate import load_requests, scrubbed
from app.models.plan import PlanRequest
from app.models.schemas import MAX_SEED

MODEL = "ft_f1"
META_MODEL = "muse-spark-1.3"
SEED_DERIVATION = "sha256(request name)[0:4]+base seed; section +1009*i; regen +1000003; candidate +i"
COUNT_FIELDS = (
    "runs", "completed", "valid", "length", "calls", "regenerated_runs", "sections", "chord_slots",
    "rule_slots", "regenerated_sections", "empty_slots", "diatonic_runs", "diatonic_slots",
    "diatonic_outside", "repeat_pairs", "identical_pairs",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def money(value: object, label: str) -> float:
    require(isinstance(value, (float, int)) and not isinstance(value, bool), f"{label}: missing numeric cost")
    require(math.isfinite(value) and value >= 0, f"{label}: cost must be finite and nonnegative")
    return float(value)


def same_cost(actual: object, expected: float, label: str, terms: int = 1) -> None:
    require(math.isclose(money(actual, label), expected, abs_tol=max(1, terms) * 1e-8, rel_tol=0),
            f"{label}: costs do not reconcile")


def derived_seed(seed: int, name: str) -> int:
    return (seed + int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big")) & MAX_SEED


def validate_run(run: dict, fixture: dict, arm: str, seed: int, seen_ids: set[str]) -> None:
    name = run["request"]
    label = f"seed {seed}, {arm}, {name}"
    expected = PlanRequest.model_validate({**fixture, "planner": arm, "modelKey": MODEL,
                                          "seed": derived_seed(seed, name)}).model_dump(mode="json")
    require(run.get("requestBody") == expected, f"{label}: request differs from the fixture or seed/model controls")
    require(run.get("samplingSeed") == expected["seed"], f"{label}: samplingSeed differs from requestBody")
    require(not run.get("evaluationError"), f"{label}: saved evaluationError")
    trace = run["trace"]
    require(run.get("status") == trace["status"], f"{label}: status differs from trace")
    for field in ("planner", "genre", "key", "bpm", "timeSignature"):
        require(trace[field] == expected[field], f"{label}: trace {field} differs from request")
    sections = trace["sections"]
    attempts = run.get("generationAttempts")
    require(isinstance(attempts, list), f"{label}: missing generationAttempts; pilot results are excluded")
    initial = [a for a in attempts if not a["regenerated"]]
    regenerated = [a for a in attempts if a["regenerated"]]
    require([a["index"] for a in initial] == list(range(len(sections))),
            f"{label}: initial generation provenance does not cover every final section")
    require(len({a["index"] for a in regenerated}) == len(regenerated),
            f"{label}: a section was regenerated more than once")
    latest = {}
    for attempt in attempts:
        require(attempt["source"] == "ai" and attempt["modelUsed"] == MODEL,
                f"{label}: a generation attempt did not use {MODEL}")
        require(type(attempt["index"]) is int and 0 <= attempt["index"] < len(sections),
                f"{label}: generation index is outside final sections")
        latest[attempt["index"]] = attempt
    for index, section in enumerate(sections):
        require(section["source"] == "ai" and section["modelUsed"] == MODEL,
                f"{label}: a final section did not use {MODEL}")
        for field in ("source", "modelUsed", "regenerated", "sectionType", "bars"):
            require(latest[index][field] == section[field], f"{label}: final section differs from provenance")
    require(sum(bool(s["regenerated"]) for s in sections) == len(regenerated),
            f"{label}: regeneration count differs from provenance")
    if trace["status"] == "ok":
        require(trace["plan"] is not None and len(sections) == len(trace["plan"]["sections"]),
                f"{label}: completed trace is missing planned sections")

    usage = run.get("apiUsage")
    require(isinstance(usage, list), f"{label}: missing apiUsage")
    api_cost = 0.0
    local_ids = set()
    for entry in usage:
        require(entry["provider"] == "meta" and entry["model"] == META_MODEL,
                f"{label}: unexpected API provider or model")
        require(entry["status"] in ("settled", "failed"), f"{label}: unsettled API reservation")
        api_cost += money(entry.get("settled_usd"), label)
        request_id = entry.get("request_id")
        if request_id:
            require(request_id not in seen_ids, f"{label}: API request ID attributed to more than one entry/run")
            seen_ids.add(request_id)
            local_ids.add(request_id)
        tokens = entry.get("usage")
        if entry["status"] == "settled":
            require(isinstance(tokens, dict), f"{label}: settled API call has no token usage")
        if tokens is not None:
            require(isinstance(tokens, dict) and all(type(v) is int and v >= 0 for v in tokens.values()),
                    f"{label}: invalid token usage")
    calls = trace["calls"]
    for call in calls:
        require(call["provider"] == "meta" and call["model"] == META_MODEL,
                f"{label}: unexpected trace provider/model")
        require(not call["requestId"] or call["requestId"] in local_ids,
                f"{label}: trace API request ID is missing from its usage records")
    require(arm != "rules" or not usage and not calls, f"{label}: rules arm called an API")
    same_cost(trace["spendUsd"], sum(money(c["costUsd"], label) for c in calls), label, len(calls))
    same_cost(trace["spendUsd"], api_cost, label, len(usage))
    same_cost(run["costUsd"], trace["spendUsd"], label)


def validate_documents(documents: tuple[dict, dict], fixtures: dict[str, dict],
                       seen_ids: set[str]) -> tuple[int, dict, tuple[dict, dict]]:
    rules_doc, meta_doc = documents
    seed = rules_doc.get("samplingSeed")
    require(type(seed) is int and 0 <= seed <= MAX_SEED, "Result samplingSeed must be uint32")
    controls = rules_doc.get("controls")
    require(isinstance(controls, dict), f"seed {seed}: missing controls")
    required_controls = {"temperatures": [0.7, 0.9, 1.1], "rag": False, "metaSeeded": False,
                         "sourceRequired": "ai", "seedDerivation": SEED_DERIVATION}
    require(all(controls.get(key) == value for key, value in required_controls.items()),
            f"seed {seed}: missing or unexpected generation controls")
    require(type(controls.get("voiceLeading")) is bool, f"seed {seed}: missing voice-leading control")
    arms = []
    for arm, document in zip(("rules", "meta"), documents):
        require(document.get("planner") == arm, f"seed {seed}: incorrect planner document")
        require(document.get("samplingSeed") == seed, f"seed {seed}: paired base seeds differ")
        require(document.get("chordModel") == MODEL, f"seed {seed}: chord checkpoint must be {MODEL}")
        require(document.get("effort") == ("medium" if arm == "meta" else None), f"seed {seed}: unexpected effort")
        require(document.get("controls") == controls, f"seed {seed}: paired controls differ")
        require(document.get("requests") == len(fixtures), f"seed {seed}: declared request count differs")
        runs = document["runs"]
        names = [run["request"] for run in runs]
        require(len(names) == len(set(names)) and set(names) == set(fixtures),
                f"seed {seed}, {arm}: requires all 20 unique fixtures; incomplete results are not pooled")
        indexed = dict(zip(names, runs))
        for name, run in indexed.items():
            validate_run(run, fixtures[name], arm, seed, seen_ids)
        same_cost(document["spentUsd"], sum(run["costUsd"] for run in runs),
                  f"seed {seed}, {arm}: document total", len(runs))
        arms.append(indexed)
    for name in fixtures:
        bodies = [{k: v for k, v in arm[name]["requestBody"].items() if k != "planner"} for arm in arms]
        require(bodies[0] == bodies[1], f"seed {seed}, {name}: paired request bodies differ")
    return seed, controls, tuple(arms)


def pool(batches: list[dict], arm: int) -> dict:
    summaries = [batch["summaries"][arm] for batch in batches]
    result = {key: sum(s.get(key, 0) for s in summaries) for key in COUNT_FIELDS}
    result["section_sources"] = dict(sum((Counter(s["section_sources"]) for s in summaries), Counter()))
    result["distinct_types"] = sum(s["distinct_types"] * s["runs"] for s in summaries) / result["runs"]
    pairs = result["repeat_pairs"]
    result["pair_agreement"] = sum(s["pair_agreement"] * s.get("repeat_pairs", 0) for s in summaries) / pairs if pairs else 0
    runs = [run for batch in batches for run in batch["arms"][arm].values()]
    result["median_s"] = statistics.median(run["trace"]["elapsedMs"] / 1000 for run in runs)
    result["cost_total"] = sum(run["trace"]["spendUsd"] for run in runs)
    result["cost_mean"] = result["cost_total"] / result["runs"]
    result["generation_attempts"] = sum(len(run["generationAttempts"]) for run in runs)
    result["api_entries"] = sum(len(run["apiUsage"]) for run in runs)
    result["prompt_tokens"] = sum((entry.get("usage") or {}).get("prompt_tokens", 0) for run in runs for entry in run["apiUsage"])
    result["completion_tokens"] = sum((entry.get("usage") or {}).get("completion_tokens", 0) for run in runs for entry in run["apiUsage"])
    result["diatonic_shares"] = {(batch["seed"], name): share for batch in batches
                                  for name, share in batch["summaries"][arm]["diatonic_shares"].items()}
    result["not_accepted"] = [(batch["seed"], name) for batch in batches
                              for name in batch["summaries"][arm]["not_accepted"]]
    result["judged"] = sum(bool(run["trace"]["judge"]) for run in runs)
    result["accepted"] = sum(bool(run["trace"]["judge"]) and run["trace"]["judge"][-1]["decision"] == "accept" for run in runs)
    return result


def wins(rules: dict, meta: dict) -> tuple[int, int, int]:
    before, after = rules["diatonic_shares"], meta["diatonic_shares"]
    require(before.keys() == after.keys(), "Diatonic diagnostic pairs differ")
    lower = sum(after[name] < before[name] for name in before)
    equal = sum(after[name] == before[name] for name in before)
    return lower, equal, len(before) - lower - equal


def table(rows: list[tuple[str, str, str]]) -> list[str]:
    return ["| Metric | Rules planner | Muse Spark planner (medium) |", "|---|---:|---:|",
            *("| " + " | ".join(row) + " |" for row in rows)]


def report(batches: list[dict]) -> str:
    rules, meta = pool(batches, 0), pool(batches, 1)
    both = (rules, meta)
    lines = ["# Fixed-seed paired planner evaluation", "",
             f"{len(batches)} chord-sampling seeds × 20 public fixtures = {rules['runs']} paired runs "
             f"({rules['runs'] + meta['runs']} total pipeline executions). Chord checkpoint: `{MODEL}` in both arms; "
             f"Meta model: `{META_MODEL}`, planning effort `medium`.", "",
             "## Controls and validation", "",
             "Each pair has exactly the same normalized request except `planner`, including its derived chord-sampling seed. "
             "All seeds cover the same 20 fixtures. The report checks both initial and regenerated section provenance, "
             "final section provenance, unique API request attribution, and reconciliation of run, trace, call, API usage, and document costs. "
             "The pilot without generation-attempt provenance is excluded; incomplete batches fail validation.", "",
             f"Both arms use temperatures `{batches[0]['controls']['temperatures']}`, RAG disabled, "
             f"and voice leading {'enabled' if batches[0]['controls']['voiceLeading'] else 'disabled'}. "
             "Request seeds are the base seed plus the first four SHA-256 bytes of the fixture name; section index adds 1009, "
             "regeneration adds 1000003, and candidate index adds its zero-based offset (all uint32). "
             "The Meta planner is not seeded. The rules arm runs first within each pair. "
             "Prompts and JSON schemas are fixed by the product, but their lengths vary with the sketch, plan, and diagnostic report. "
             "This compares the full rules pipeline with Meta planning plus judging and possible regeneration; "
             "different plans do not imply identical musical material at the same ordinal section seed. "
             "Fixing one chord checkpoint deliberately controls that variable; this does not evaluate the quality of genre-specific checkpoint/LoRA selection.", "",
             "## Per-seed results", "",
             "| Seed | Completed rules / Meta | Valid plans rules / Meta | Mean distinct types rules / Meta | "
             "Meta diatonic lower / equal / higher | Last judge regenerate | Meta API cost |",
             "|---|---|---|---|---|---|---:|"]
    for batch in batches:
        r, m = batch["summaries"]
        lower, equal, higher = wins(r, m)
        lines.append(f"| {batch['seed']} | {r['completed']}/{r['runs']} / {m['completed']}/{m['runs']} | "
                     f"{r['valid']}/{r['runs']} / {m['valid']}/{m['runs']} | {r['distinct_types']:.2f} / {m['distinct_types']:.2f} | "
                     f"{lower} / {equal} / {higher} | {len(m['not_accepted'])}/{m['runs']} | ${m['cost_total']:.6f} |")
    lines += ["", "## Hard contracts", "", *table([
        ("Completed traces (`status=ok`)", *(fraction(s["completed"], s["runs"]) for s in both)),
        ("Plans passing the current validator", *(fraction(s["valid"], s["runs"]) for s in both)),
        ("Requested total bar count", *(fraction(s["length"], s["runs"]) for s in both)),
        (f"All generation attempts using `{MODEL}`", *(fraction(s["generation_attempts"], s["generation_attempts"]) for s in both)),
        (f"Final sections using `{MODEL}`", *(fraction(s["section_sources"].get("ai", 0), s["sections"]) for s in both)),
    ]), "", "The validator checks form constraints such as total length, section/cadence vocabulary, outro placement, "
         "and sketch citations. Passing these contracts does not establish good chord choices or perceived musical quality.",
         "", "## Musical diagnostics (proxies, not quality scores)", "", *table([
        ("Mean distinct section types", *(f'{s["distinct_types"]:.2f}' for s in both)),
        ("Rule-forced chord slots", *(fraction(s["rule_slots"], s["chord_slots"]) for s in both)),
        ("Out-of-key model slots in diatonic genres", *(fraction(s["diatonic_outside"], s["diatonic_slots"]) for s in both)),
        ("Empty model slots", *(str(s["empty_slots"]) for s in both)),
        ("Identical same-type/length section pairs", *(fraction(s["identical_pairs"], s["repeat_pairs"]) for s in both)),
        ("Mean symbol agreement in those pairs", *(f'{s["pair_agreement"]:.1%}' if s["repeat_pairs"] else "n/a" for s in both)),
    ])]
    lower, equal, higher = wins(rules, meta)
    lines += ["", f"Paired diatonic diagnostic W/E/L (lower out-of-key share / equal / higher): **{lower} / {equal} / {higher}**, "
              f"over {len(rules['diatonic_shares'])} request-seed pairs. These are diagnostic wins, not musical-preference wins. "
              "Rule-forced slots are excluded from the out-of-key calculation. Its denominator includes all remaining model slots; "
              "empty slots are reported separately. Repeated-section agreement uses exact chord symbols in same-type/length pairs; "
              "higher repetition can represent consistency or monotony. More section types and fewer out-of-key chords are not universally better.",
              "", f"The diatonic subset uses the product's genres: {', '.join(DIATONIC_GENRES)}. "
              "For suggestion A, the analyzer removes slash bass and checks whether every parsed chord tone belongs to the key collection. "
              "Major uses its major-scale pitch classes; minor uses the union of natural, harmonic, and melodic minor pitch classes. "
              "A nonempty symbol the chord parser cannot interpret also counts as outside the collection. "
              "This is a strict pitch-collection diagnostic, not a test of functional harmony; borrowed chords and secondary dominants can be musically valid.",
              "", "Ratios pool their numerators and denominators. Distinct types are averaged across runs; repeated-pair agreement "
              "is weighted by the number of comparable section pairs. Each fixture repeats across seeds, so these observations "
              "are repeated measurements of 20 fixtures rather than independent musical tasks, and no significance claim is made.", "",
              "## Judge decisions and execution cost", "", *table([
        ("Runs with regenerated sections", *(fraction(s["regenerated_runs"], s["runs"]) for s in both)),
        ("Final judge accepted", "n/a (no judge)", fraction(meta["accepted"], meta["judged"])),
        ("Last judge still requested regeneration", "n/a (no judge)", fraction(len(meta["not_accepted"]), meta["judged"])),
        ("Pooled median total latency", *(f'{s["median_s"]:.3f} s' for s in both)),
        ("Recorded API calls (ledger entries)", *(str(s["api_entries"]) for s in both)),
        ("Recorded prompt / completion tokens", *(f'{s["prompt_tokens"]} / {s["completion_tokens"]}' for s in both)),
        ("Recorded mean Meta API cost per run", *(f'${s["cost_mean"]:.6f}' for s in both)),
        ("Recorded total Meta API cost", *(f'${s["cost_total"]:.6f}' for s in both)),
    ]), "", "`status=ok` means the bounded pipeline completed, not that the final judge accepted the song. "
         "The judge can still request regeneration after its allowed turns or after a section has already been regenerated. "
         "Its decisions come from diagnostic reports, not listening, and are not independent human quality judgments. "
         "Latency includes execution order, local model loading/cache effects, and network variability."]
    if meta["not_accepted"]:
        lines += ["", "Last judge still requested regeneration:", "",
                  *(f"- Seed {seed}: `{name}`" for seed, name in meta["not_accepted"])]
    lines += ["", f"The saved runs included here incurred **${rules['cost_total'] + meta['cost_total']:.6f}** in recorded Meta API cost. "
              "This excludes pilot and any other batches not supplied to this report. This offline report made **0 additional API calls**, "
              "cost **$0 additionally**, and generated no music. No listening test was performed; these results do not prove musical superiority.",
              "", "Sources: each supplied seed directory's `rules.json` and `meta-medium.json`, plus the public request fixtures. "
              "All validation and metrics are reproducible with `agent/report_fixed_seed_plans.py`."]
    return "\n".join(lines) + "\n"


def build_report(result_paths: list[Path], requests_path: Path) -> str:
    fixtures = dict(load_requests(requests_path))
    require(len(fixtures) == 20, "Expected exactly 20 public request fixtures")
    require(bool(result_paths), "At least one seed result directory is required")
    seen_ids: set[str] = set()
    seeds: set[int] = set()
    controls = None
    batches = []
    for path in result_paths:
        documents = tuple(json.loads((path / name).read_text(encoding="utf-8"))
                          for name in ("rules.json", "meta-medium.json"))
        seed, current_controls, arms = validate_documents(documents, fixtures, seen_ids)
        require(seed not in seeds, f"Duplicate sampling seed: {seed}")
        require(controls is None or current_controls == controls, "Generation controls differ across seeds")
        seeds.add(seed)
        controls = current_controls
        batches.append({"seed": seed, "controls": controls, "arms": arms,
                        "summaries": compare(*arms, requests_path)})
    return scrubbed(report(sorted(batches, key=lambda batch: batch["seed"])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, action="append", required=True, help="One saved seed directory; repeat for every seed")
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Optional Markdown destination")
    args = parser.parse_args()
    try:
        text = build_report(args.results, args.requests)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
