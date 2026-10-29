"""Write experiments/harmony_eval/summary.md from the results files present.

Run from backend/:
    uv run python -m scripts.harmony_eval.report [--out-dir DIR]

The synthetic rows are recomputed from the per-bar outputs; the real-score and
real-song rows are the aggregates the runner stored, since their per-bar outputs
stay private. A real-song results file that carries anything but aggregates is
refused, and then nothing is written.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.harmony_eval import EXPERIMENTS_DIR, PrivateDataError, repo_relative
from scripts.harmony_eval.engines import ENGINES
from scripts.harmony_eval.metrics import CONFIDENCE_LEVELS, FIELDS, Tally, call_stats
from scripts.harmony_eval.run import REAL_LABEL, assert_aggregate, load_results, real_songs_results_path, results_path

ENGINE_NOTES = {
    "local": "the product's deterministic analyzer, no model",
    "meta": "Muse Spark over the same notes, 8-bar batches, key given, no printed chords",
    "auto": "local first, Meta only for bars local left without chords (the product's engine=auto rule)",
    "openweight": "Muse Spark Open on Baseten, effort high, own ledger",
}


def pct(value: float | None) -> str:
    return "–" if value is None else f"{100 * value:.1f}%"


def num(value: float | None, digits: int = 1) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def usd(value: float | None, digits: int = 4) -> str:
    return "–" if value is None else f"${value:.{digits}f}"


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def synthetic_tallies(section: dict) -> tuple[Tally, dict[str, Tally], dict[str, Tally]]:
    """Overall, per-variant and per-genre tallies recomputed from the per-bar outputs."""
    overall, by_variant, by_genre = Tally(), {}, {}
    for record in section["records"]:
        for bar in record["bars"]:
            for tally in (overall, by_variant.setdefault(record["variant"], Tally()),
                          by_genre.setdefault(record["genre"], Tally())):
                tally.add_bar(bar["truth"], bar["chords"], bar["confidence"])
    return overall, by_variant, by_genre


def _status(section: dict | None, result: dict | None = None) -> str:
    if not section:
        reason = (result or {}).get("not_run")
        return f"not run: {reason}" if reason else "not run"
    status = "complete" if section.get("complete") else f"incomplete ({section.get('stopped')})"
    failed = (section.get("call_stats") or {}).get("failed") or {}
    if failed:
        status += "; failed calls: " + ", ".join(f"{kind} {count}" for kind, count in failed.items())
    unscored = (section.get("metrics") or {}).get("unscored_truth")
    if unscored is not None:
        status += f"; truth slots left unscored: {unscored}"
    return status


def metric_row(name: str, summary: dict, stats: dict, bars: int, settings: dict) -> list[str]:
    on_all, covered = summary["all"], summary["on_covered"]
    return [name, str(summary["slots"]), pct(summary["coverage"]),
            *[pct(on_all[field]) for field in FIELDS], pct(covered["root"]), pct(covered["exact"]),
            num(stats["latency_ms_p50"]), num(stats["latency_ms_p95"]), str(stats["calls"]),
            usd(stats["cost_usd"]), usd(stats["cost_usd"] / bars, 5) if bars else "–",
            pct(stats["json_validity"]), pct(stats["retry_rate"]),
            f"{settings.get('provider')} / {settings.get('model')}"]


METRIC_HEADER = ["engine", "slots", "coverage", "root", "triad", "seventh", "bass", "exact", "root (covered)",
                 "exact (covered)", "p50 ms", "p95 ms", "calls", "cost", "USD/bar", "JSON valid", "retry rate",
                 "provider / model"]


def group_rows(by_engine: dict[str, dict[str, dict]], order: list[str]) -> list[list[str]]:
    """One row per group and engine from summaries, grouped by group, engines in report order."""
    rows = []
    for name, groups in by_engine.items():
        for key, summary in groups.items():
            rows.append([key, name, str(summary["slots"]), pct(summary["coverage"]),
                         *[pct(summary["all"][field]) for field in FIELDS], pct(summary["on_covered"]["exact"])])
    rows.sort(key=lambda row: (row[0], order.index(row[1])))
    return rows


def _points(value: float | None, base: float | None) -> float | None:
    """value - base in percentage points."""
    return None if value is None or base is None else round(100 * (value - base), 1)


def _signed(points: float | None) -> str:
    return "–" if points is None else f"{points:+.1f}"


def _calls(count: int) -> str:
    return f"{count} call{'' if count == 1 else 's'}"


def _seconds(milliseconds: float | None) -> str:
    return "–" if milliseconds is None else f"{milliseconds / 1000:.1f} s"


def _versus(summary: dict, base: dict, path: tuple[str, ...]) -> str:
    value, reference = summary, base
    for key in path:
        value, reference = value[key], reference[key]
    return f"{_signed(_points(value, reference))} ({pct(value)} vs {pct(reference)})"


def comparison(name: str, scope: str, summary: dict, base: dict, variants: dict[str, dict],
               base_variants: dict[str, dict], stats: dict) -> str:
    """One engine against local in percentage points, with its largest gain and loss by variant."""
    deltas = []
    for variant, variant_summary in variants.items():
        if variant in base_variants:
            points = _points(variant_summary["all"]["exact"], base_variants[variant]["all"]["exact"])
            if points is not None:
                deltas.append((points, variant))
    deltas.sort()
    if not deltas:  # a run stopped before its first record
        spread = "no variant scored"
    else:
        gain = f"largest gain {deltas[-1][1]} {_signed(deltas[-1][0])}" if deltas[-1][0] > 0 else "no variant gained"
        loss = f"largest loss {deltas[0][1]} {_signed(deltas[0][0])}" if deltas[0][0] < 0 else "no variant lost"
        spread = f"{gain}, {loss}"
    return (f"- **{name}**, {scope}: exact {_versus(summary, base, ('all', 'exact'))}, coverage "
            f"{_versus(summary, base, ('coverage',))}, exact on covered slots "
            f"{_versus(summary, base, ('on_covered', 'exact'))}; {spread}; {usd(stats['cost_usd'])} for "
            f"{_calls(stats['calls'])}, p50 {_seconds(stats['latency_ms_p50'])} per call")


def reading(results: dict[str, dict]) -> list[str]:
    """Each model engine against local, in percentage points, with its best and worst variant."""
    local = results.get("local") or {}
    base = local.get("synthetic")
    if not base:
        return []
    base_overall, base_variants, _ = synthetic_tallies(base)
    base_by_variant = {variant: tally.summary() for variant, tally in base_variants.items()}
    lines = ["Against local, in percentage points (all slots unless noted):", ""]
    for name, result in results.items():
        section = result.get("synthetic")
        if name == "local" or not section:
            continue
        overall, variants, _ = synthetic_tallies(section)
        lines.append(comparison(name, "synthetic", overall.summary(), base_overall.summary(),
                                {variant: tally.summary() for variant, tally in variants.items()}, base_by_variant,
                                call_stats(section["calls"])))
        real, base_real = result.get("real"), local.get("real")
        if real and base_real:
            lines.append(f"- **{name}**, real score ({real['bars_scored']} bars): coverage "
                         f"{_versus(real['metrics'], base_real['metrics'], ('coverage',))}, exact "
                         f"{_versus(real['metrics'], base_real['metrics'], ('all', 'exact'))}, exact on covered slots "
                         f"{_versus(real['metrics'], base_real['metrics'], ('on_covered', 'exact'))}; "
                         f"{usd(real['cost_usd'])} for {_calls(real['call_stats']['calls'])}")
    lines.append("")
    return lines


def _counts(counts: dict | None) -> str:
    return ", ".join(f"{name} {count}" for name, count in (counts or {}).items()) or "none"


def dataset_mismatch(results: dict[str, dict], section: str) -> str | None:
    """A warning line when the engines with a `section` ran on different datasets, else None."""
    hashes = {name: str((result.get("dataset") or {}).get("sha256", "–"))[:12]
              for name, result in results.items() if result.get(section)}
    if len(set(hashes.values())) <= 1:
        return None
    named = ", ".join(f"{name} `{digest}…`" for name, digest in hashes.items())
    return f"**Not comparable: these engines ran on different datasets ({named}).** Rerun them on one dataset."


def real_songs_lines(real_songs: dict[str, dict]) -> list[str]:
    """The real-song section: what was scored (counts only), each engine's row, its reading against
    local, and the per-variant and per-genre rows the runner aggregated."""
    lines = ["## Real songs", ""]
    facts = next((result["dataset"] for result in real_songs.values() if result.get("dataset")), None)
    if facts is None:
        lines.extend(["_no real-song results yet_", ""])
        return lines
    if mismatch := dataset_mismatch(real_songs, "real_songs"):
        lines.extend([mismatch, ""])
    sources = facts.get("key_sources") or {}
    lines.append(f"Source: {facts['label']}. N = {facts['excerpts']} excerpts from {facts['songs_used']} songs, "
                 f"{facts['bars']} bars, {facts['slots']} slots. An excerpt is eight consecutive bars of one song "
                 f"whose every bar holds one or two chords (bars left out of every excerpt: "
                 f"{_counts(facts.get('bars_left_out'))}; songs dropped: {_counts(facts.get('songs_dropped'))}), "
                 f"realized in one of the six variants of the synthetic set: {_counts(facts.get('variants'))}. "
                 f"Genres {_counts(facts.get('genres'))}; realized meters {_counts(facts.get('meters'))} (waltz "
                 f"excerpts are 3/4 whatever the song's meter). Key: the file's for {sources.get('file', 0)} "
                 f"excerpts; for {sources.get('estimated', 0)} the file holds C major, which the corpus "
                 "preprocessing also writes for a song without a key, so the key is the product's own estimate "
                 "over the excerpt's chords. The estimate is rough, and the Billboard and JHT files write every key "
                 "as major, so a minor song's key can be wrong; every engine got the same key, so the comparison "
                 f"stays fair. Seed {facts.get('seed')}, sha256 of the private realized dataset "
                 f"`{str(facts.get('sha256', '–'))[:12]}…`. Only these aggregates are public: the songs, their "
                 "chords and the realized notes stay outside the repository.")
    lines.append("")
    rows, status = [], []
    for name, result in real_songs.items():
        section = result.get("real_songs")
        status.append(f"- **{name}**: {ENGINE_NOTES.get(name, '')} — {_status(section, result)}")
        if section:
            rows.append(metric_row(name, section["metrics"], section["call_stats"], section["bars"],
                                   result.get("settings", {})))
    lines.append(table(METRIC_HEADER, rows) if rows else "_no real-song results yet_")
    lines.append("")
    lines.extend(status)
    lines.append("")
    base = (real_songs.get("local") or {}).get("real_songs")
    compared = []
    for name, result in real_songs.items():
        section = result.get("real_songs")
        if base and name != "local" and section:
            compared.append(comparison(name, "real songs", section["metrics"], base["metrics"],
                                       section["by_variant"], base["by_variant"], section["call_stats"]))
    if compared:
        lines.extend(["Against local, in percentage points (all slots unless noted):", "", *compared, ""])
    order = list(real_songs)
    for title, group in (("variant", "by_variant"), ("genre", "by_genre")):
        rows = group_rows({name: result["real_songs"][group] for name, result in real_songs.items()
                           if result.get("real_songs")}, order)
        lines.append(f"### By {title} (real songs, all slots)")
        lines.append("")
        lines.append(table([title, "engine", "slots", "coverage", *FIELDS, "exact (covered)"], rows)
                     if rows else "_none_")
        lines.append("")
    lines.append("Each genre has three or four excerpts in different variants and each variant about seven "
                 "genres, so compare engines within a row, not rows with each other.")
    lines.append("")
    return lines


def render(results: dict[str, dict], real_songs: dict[str, dict] | None = None) -> str:
    lines = ["# Harmony evaluation: does Meta read chords from notes better than the local analyzer?", ""]
    lines.append("Every engine saw the same notes and the same key, and never a chord symbol. A bar is scored on "
                 "the editor's two slots; a slot without a proposal is wrong in the all-slot columns and left out "
                 "of the covered ones. Matches are cumulative (triad needs root, seventh needs triad, exact needs "
                 "all four); bass stands alone. A truth slot whose symbol the scorer cannot read is left out of "
                 "every column and counted in each engine's status line.")
    lines.append("")
    lines.extend(real_songs_lines(real_songs or {}))

    lines.append("## Results (synthetic scores)")
    lines.append("")
    first = next((result for result in results.values() if result.get("dataset")), None)
    dataset = (first or {}).get("dataset") or {}
    lines.append(f"Synthetic dataset: `{dataset.get('path', '–')}` — {dataset.get('records', '–')} scores, "
                 f"{dataset.get('bars', '–')} bars, variants {dataset.get('variants', {})}, "
                 f"sha256 `{str(dataset.get('sha256', '–'))[:12]}…`.")
    lines.append("")
    if mismatch := dataset_mismatch(results, "synthetic"):
        lines.extend([mismatch, ""])
    rows, status = [], []
    for name, result in results.items():
        section = result.get("synthetic")
        status.append(f"- **{name}**: {ENGINE_NOTES.get(name, '')} — {_status(section, result)}")
        if not section:
            continue
        overall, _, _ = synthetic_tallies(section)
        rows.append(metric_row(name, overall.summary(), call_stats(section["calls"]), section["bars"],
                               result.get("settings", {})))
    lines.append(table(METRIC_HEADER, rows) if rows else "_no synthetic results yet_")
    lines.append("")
    lines.extend(status)
    lines.append("")
    lines.extend(reading(results))
    lines.append("Latency is wall-clock per call: per bar for local, per batch of up to 8 bars for the model "
                 "engines (auto: its Meta calls only). Cost is the ledger's settled USD; USD/bar divides it by "
                 "every dataset bar, also for auto, which sends only the bars local left open. JSON validity "
                 "counts replies that parsed as the schema over all attempts; the Meta API enforces the schema "
                 "server-side and never retries, so its retry rate is 0 by construction. Request ids are kept in "
                 "`results-<engine>.json` and `results-real-songs-<engine>.json` under `calls[].request_id`.")
    lines.append("")

    lines.append("## Confidence calibration (synthetic, covered slots)")
    lines.append("")
    rows = []
    for name, result in results.items():
        section = result.get("synthetic")
        if not section:
            continue
        calibration = synthetic_tallies(section)[0].summary()["calibration"]
        for level in CONFIDENCE_LEVELS:
            if level in calibration:
                counts = calibration[level]
                rows.append([name, level, str(counts["slots"]), pct(counts["root"]), pct(counts["exact"])])
    lines.append(table(["engine", "reported confidence", "slots", "root", "exact"], rows) if rows else "_none_")
    lines.append("")

    for title, group in (("variant", 1), ("genre", 2)):
        lines.append(f"## By {title} (synthetic, all slots)")
        lines.append("")
        by_engine = {name: {key: tally.summary()
                            for key, tally in synthetic_tallies(result["synthetic"])[group].items()}
                     for name, result in results.items() if result.get("synthetic")}
        rows = group_rows(by_engine, list(results))
        lines.append(table([title, "engine", "slots", "coverage", *FIELDS, "exact (covered)"], rows) if rows else "_none_")
        lines.append("")

    lines.append(f"## Real score ({REAL_LABEL})")
    lines.append("")
    rows, notes = [], []
    for name, result in results.items():
        section = result.get("real")
        if not section:
            notes.append(f"- **{name}**: {_status(None, result)}")
            continue
        summary, stats = section["metrics"], section["call_stats"]
        rows.append([f"{name} ({REAL_LABEL}, {section['bars_scored']} bars)", str(summary["slots"]),
                     pct(summary["coverage"]), *[pct(summary["all"][field]) for field in FIELDS],
                     pct(summary["on_covered"]["root"]), pct(summary["on_covered"]["exact"]),
                     num(stats["latency_ms_p50"]), num(stats["latency_ms_p95"]), str(stats["calls"]),
                     usd(stats["cost_usd"]), usd(stats["cost_usd"] / section["bars_scored"], 5),
                     pct(stats["json_validity"]), pct(stats["retry_rate"]),
                     f"{result.get('provider')} / {result.get('model')}"])
        excluded = ", ".join(f"{reason} {count}" for reason, count in section["excluded"].items())
        notes.append(f"- **{name}**: {_status(section, result)}; {section['bars_total']} bars in the score, "
                     f"{section['bars_scored']} scored (left out: {excluded}); key {section['key']} "
                     f"({section['key_source']}, confidence {section['key_confidence']}); timing estimated in "
                     f"{section['timing_estimated_bars']} scored bars, reader warnings in "
                     f"{section['bars_with_reader_warnings']}; meters {section['meters']}")
    lines.append(table(METRIC_HEADER, rows) if rows else "_no real-score results yet_")
    lines.append("")
    lines.extend(notes)
    lines.append("")
    lines.append("Aggregate rows only: the score, its notes and its per-bar outputs stay outside the repository. "
                 "A bar counts when it carries both printed chords and read notes; bars with more than two printed "
                 "chords have no two-slot truth and are left out. The key is the product's own estimate from the "
                 "read notes, given to every engine alike.")
    lines.append("")

    lines.append("## What the numbers do and do not show")
    lines.append("")
    lines.append("- The real songs are real progressions held out from training, but their notes are the "
                 "product's own voicings of the chord symbols, so they test reading real harmony, not a "
                 "musician's voicing or a PDF. In the Chordonomicon-derived genres a bar is two consecutive "
                 "chords as the corpus preprocessing grouped them, not a timed bar.")
    lines.append("- The synthetic scores are the product's own voicings of its own progressions with controlled "
                 "difficulty (rootless shells, slash inversions, melody passing and neighbor tones, sparse bars, "
                 "3/4). They show where an engine fails, not how often a musician's PDF fails.")
    lines.append("- Every engine got the key. Without it, the local analyzer estimates one and the model is told "
                 "none; neither case is measured here.")
    lines.append("- Notes only: no printed chords were visible to any engine, also where the product would send "
                 "a neighbor's printed symbol as context.")
    lines.append("- One real score is evidence, not a benchmark, and its timing is estimated in most bars, which "
                 "caps every engine's confidence at low by the product's rules.")
    lines.append("- A chord is right or wrong against one truth symbol; a musically defensible alternative "
                 "(Eb6 for Cm7, the relative minor of a rootless maj7) counts as wrong.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write summary.md from the results files present.")
    parser.add_argument("--out-dir", type=Path, default=EXPERIMENTS_DIR)
    args = parser.parse_args(argv)
    results, real_songs = {}, {}
    for name in ENGINES:
        loaded = load_results(results_path(name, args.out_dir))
        if loaded is not None:
            results[name] = loaded
        path = real_songs_results_path(name, args.out_dir)
        loaded = load_results(path)
        if loaded is not None:
            try:
                assert_aggregate(loaded)
            except PrivateDataError as exc:
                print(f"refusing to write the summary from {repo_relative(path)}: {exc}", file=sys.stderr)
                return 1
            real_songs[name] = loaded
    if not results and not real_songs:
        print(f"no results-*.json in {args.out_dir}", file=sys.stderr)
        return 1
    out = args.out_dir / "summary.md"
    out.write_text(render(results, real_songs), encoding="utf-8")
    print(f"wrote {repo_relative(out)} from {', '.join(results)}; real songs from {', '.join(real_songs) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
