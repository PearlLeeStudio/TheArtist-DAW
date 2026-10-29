"""Run one engine over the synthetic dataset, one private real score, or the private real songs.

Run from backend/:
    uv run python -m scripts.harmony_eval.run --engine local|meta|auto|openweight [--max-usd 4]
    uv run python -m scripts.harmony_eval.run --engine meta --real SCORE.pdf --private-dir DIR
    uv run python -m scripts.harmony_eval.run --engine meta --songs SONGS.jsonl [--private-dir DIR]

The synthetic run writes per-bar outputs to experiments/harmony_eval/results-<engine>.json.
The real run (--real) scores the bars of one vector-PDF score that carry both printed
chords and notes, with the chords hidden from the engine; the public file gets only
aggregate rows, and the per-bar outputs go to --private-dir, which must be outside
the repo. The two sections share the file, so each run keeps the other's section.

The real-song run (--songs) cuts excerpts from the owner's private songs and realizes
them as the synthetic scores are realized. Only aggregates (overall, per variant, per
genre, the calls) go to experiments/harmony_eval/results-real-songs-<engine>.json, checked
before writing; the realized dataset and the per-bar outputs go to --private-dir (default
../.tooling/score-inspection/harmony-eval), and nothing else derived from the songs is
written inside the repository.

Both ledgers' spent_usd (Meta, and the open-weight run's own Baseten ledger) are printed
before and after. --max-usd covers every run recorded for the same provider in the same
family of files (synthetic and real score, or real songs; meta and auto together); a run
stops cleanly before a call that could pass it and writes what it has, marked incomplete.
An engine that cannot be built (no key, Meta switched off) exits 1 and, when its results
file does not exist yet, leaves one that says why it was not run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Collection
from datetime import datetime, timezone
from pathlib import Path

from app.services.harmony_analysis import estimate_key
from app.services.llm import PROVIDERS, BudgetExceeded, Ledger, LLMConnectionError, LLMError
from app.services.score_analysis import _score_events
from app.services.score_pdf import parse_vector_score
from scripts.harmony_eval import (
    DATASET_PATH, EXPERIMENTS_DIR, PRIVATE_DIR, REAL_SONGS_DATASET_NAME, REPO_ROOT, PrivateDataError, outside_repo,
    repo_relative,
)
from scripts.harmony_eval.chords import align, normalize
from scripts.harmony_eval.dataset import SEED, VARIANTS, build_real_dataset, dumps, load_dataset, load_songs
from scripts.harmony_eval.engines import (
    ENGINES, OPENWEIGHT_CAP_USD, OPENWEIGHT_LEDGER_PATH, SpendLimit, build_engine, hide_chords,
    measures_from_record,
)
from scripts.harmony_eval.metrics import Tally, call_stats, score_bar

DEFAULT_MAX_USD = {"meta": 4.0, "auto": 4.0, "openweight": OPENWEIGHT_CAP_USD}
REAL_SONGS_MAX_USD = {"meta": 4.0, "auto": 4.0, "openweight": 6.0}
REAL_LABEL = "one private real score"
EVIDENCE_CHARS = 240
ENGINE_PROVIDERS = {"local": "local", "meta": "meta", "auto": "meta", "openweight": "baseten"}
# Fields only per-bar or per-song data has; an aggregate real-song results file carries none of them
PRIVATE_KEYS = frozenset({"title", "id", "song", "start", "key", "fileKey", "chords", "truth", "truth_slots",
                          "notes", "pitch", "spelling", "evidence", "records"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def results_path(engine: str, out_dir: Path = EXPERIMENTS_DIR) -> Path:
    return out_dir / f"results-{engine}.json"


def real_songs_results_path(engine: str, out_dir: Path = EXPERIMENTS_DIR) -> Path:
    return out_dir / f"results-real-songs-{engine}.json"


def load_results(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def prior_spend(out_dir: Path, provider: str, exclude: tuple[str, str]) -> float:
    """USD recorded in this folder for the provider, except the section this run replaces.

    The real-song files have their own limit, so a real-song run counts only those and
    the other runs count only the synthetic and real-score files.
    """
    real_songs = exclude[1] == "real_songs"
    sections = ("real_songs",) if real_songs else ("synthetic", "real")
    total = 0.0
    for name in ENGINES:
        results = load_results((real_songs_results_path if real_songs else results_path)(name, out_dir)) or {}
        if results.get("provider") != provider:
            continue
        for section in sections:
            if (results.get("engine"), section) != exclude and results.get(section):
                total += results[section].get("cost_usd") or 0.0
    return round(total, 8)


def _stop_reason(exc: BaseException) -> str:
    """Why a run stopped, without the ledger's local path that BudgetExceeded's message carries."""
    if isinstance(exc, BudgetExceeded):
        return (f"BudgetExceeded: spent ${exc.spent_usd:.4f} + outstanding ${exc.outstanding_usd:.4f} + this "
                f"request ${exc.request_usd:.4f} would pass the ledger cap ${exc.cap_usd:.2f}")
    return f"{type(exc).__name__}: {exc}"


def _bar_entry(truth: list, result) -> dict:
    entry = result.to_dict()
    entry["truth"] = truth
    entry["evidence"] = entry["evidence"][:EVIDENCE_CHARS]
    return entry


def _score_records(engine, records: list[dict], section: dict, keep: Callable[[dict, list[dict]], None],
                   log) -> Tally:
    """Runs the engine record by record, handing each record's per-bar entries to keep; a stop keeps
    what was gathered and marks the section incomplete. Returns the overall tally."""
    tally = Tally()
    try:
        for number, record in enumerate(records, 1):
            results = engine.analyze(measures_from_record(record), record["key"])
            bars = [_bar_entry(bar["chords"], result) for bar, result in zip(record["bars"], results)]
            for entry in bars:
                tally.add_bar(entry["truth"], entry["chords"], entry["confidence"])
            keep(record, bars)
            cost = sum(call.cost_usd for call in engine.calls)
            proposed = sum(bool(result.chords) for result in results)
            log(f"[{number}/{len(records)}] {record['id']}: {proposed}/{len(results)} bars proposed, "
                f"exact so far {tally.summary()['all']['exact']}, spend ${cost:.4f}")
        section["complete"] = True
    except (SpendLimit, BudgetExceeded, LLMConnectionError, KeyboardInterrupt) as exc:
        section["stopped"] = _stop_reason(exc)
        log(f"stopped: {section['stopped']}")
    calls = [call.to_dict() for call in engine.calls]
    section.update(calls=calls, call_stats=call_stats(calls), cost_usd=round(sum(c["cost_usd"] for c in calls), 6))
    return tally


def run_synthetic(engine, records: list[dict], log=print) -> dict:
    """Per-bar outputs over the dataset; a stop keeps what was gathered and marks the section incomplete."""
    section = {"created": _now(), "complete": False, "stopped": None, "records": []}

    def keep(record: dict, bars: list[dict]) -> None:
        section["records"].append({key: record[key] for key in ("id", "source", "genre", "key", "variant")}
                                  | {"bars": bars})

    tally = _score_records(engine, records, section, keep, log)
    section.update(bars=sum(len(record["bars"]) for record in section["records"]), metrics=tally.summary())
    return section


def run_real_songs(engine, records: list[dict], log=print) -> tuple[dict, list[dict]]:
    """(public aggregate section, private per-excerpt outputs) over the realized real-song excerpts."""
    section = {"created": _now(), "complete": False, "stopped": None}
    outputs: list[dict] = []
    groups: dict[str, dict[str, Tally]] = {"by_variant": {}, "by_genre": {}}

    def keep(record: dict, bars: list[dict]) -> None:
        outputs.append({key: record[key] for key in ("id", "song", "start", "genre", "variant", "key")}
                       | {"bars": bars})
        for group, name in (("by_variant", record["variant"]), ("by_genre", record["genre"])):
            tally = groups[group].setdefault(name, Tally())
            for entry in bars:
                tally.add_bar(entry["truth"], entry["chords"], entry["confidence"])

    tally = _score_records(engine, records, section, keep, log)
    section.update(excerpts=len(outputs), bars=sum(len(item["bars"]) for item in outputs), metrics=tally.summary(),
                   by_variant={name: groups["by_variant"][name].summary()
                               for name in VARIANTS if name in groups["by_variant"]},
                   by_genre={name: tallies.summary() for name, tallies in sorted(groups["by_genre"].items())})
    return section, outputs


def real_songs_facts(songs: list[dict], dropped: Counter, left_out: Counter, records: list[dict],
                     seed: int) -> dict:
    """What the realized real-song set is, in counts: no song, title, chord or note."""
    in_file = len(songs) + sum(dropped.values())
    variants = Counter(record["variant"] for record in records)
    return {"label": f"{in_file}-song test split of the training corpora, private; excerpts realized with "
                     "the product's voicing code",
            "sha256": hashlib.sha256(dumps(records).encode("utf-8")).hexdigest(), "seed": seed,
            "songs_in_file": in_file, "songs_dropped": dict(dropped), "bars_left_out": dict(left_out),
            "songs_used": len({record["song"] for record in records}), "excerpts": len(records),
            "bars": sum(len(record["bars"]) for record in records),
            "slots": sum(len(score_bar(bar["chords"], [], None)) for record in records for bar in record["bars"]),
            "genres": dict(sorted(Counter(record["genre"] for record in records).items())),
            "variants": {name: variants[name] for name in VARIANTS if variants[name]},
            "meters": dict(Counter("/".join(map(str, record["timeSignature"])) for record in records)),
            "key_sources": dict(Counter(record["keySource"] for record in records))}


def private_strings(songs: list[dict], records: list[dict], outputs: list[dict]) -> set[str]:
    """Every song id, title and chord symbol of the private set, the engines' proposals included."""
    strings = {value for song in songs for value in (song["id"], song["title"]) if isinstance(value, str) and value}
    strings |= {symbol for song in songs for bar in song["bars"] if bar for symbol in bar if symbol}
    strings |= {symbol for record in records for bar in record["bars"] for symbol in bar["chords"] if symbol}
    strings |= {symbol for item in outputs for bar in item["bars"] for symbol in bar["chords"] if symbol}
    return strings


def assert_aggregate(results: object, private: Collection[str] = ()) -> None:
    """PrivateDataError unless the object is aggregates only: no per-bar field, no string that reads
    as a chord symbol or names a private song, title or symbol, and no local path."""
    private = set(private)
    local_root = str(REPO_ROOT.parent)

    def check(node: object, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in PRIVATE_KEYS:
                    raise PrivateDataError(f"aggregate results carry the per-bar field {where}{key}")
                check(key, where)
                check(value, f"{where}{key}.")
        elif isinstance(node, list):
            for item in node:
                check(item, where)
        elif isinstance(node, str) and (node in private or normalize(node) is not None or local_root in node):
            raise PrivateDataError(f"aggregate results carry a chord symbol, a private name or a local path "
                                   f"at {where.rstrip('.') or 'the top level'}")

    check(results, "")


def _write_private(path: Path, text: str) -> None:
    path = outside_repo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def real_score(data: bytes) -> tuple[list, str | None, dict]:
    """The score's measures that carry both printed chords and notes, the product's key estimate, and
    the counts of bars left out (no printed chords, N.C., no notes, more than two printed chords)."""
    score = parse_vector_score(data)
    estimated = any(not bar.rhythm_exact for bar in score.measures)
    estimate = estimate_key(_score_events(score), key=score.key, key_signature=score.key_signature,
                            time_signature=score.time_signature or (4, 4), timing_is_estimated=estimated)
    excluded: Counter[str] = Counter()
    scored = []
    for bar in score.measures:
        if bar.no_chord:
            excluded["no_chord_sign"] += 1
        elif not bar.chords:
            excluded["no_printed_chords"] += 1
        elif not bar.notes:
            excluded["no_notes"] += 1
        elif len(bar.chords) > 2:
            excluded["more_than_two_printed_chords"] += 1
        else:
            scored.append(bar)
    facts = {"bars_total": len(score.measures), "bars_scored": len(scored), "excluded": dict(excluded),
             "timing_estimated_bars": sum(not bar.rhythm_exact for bar in scored),
             "bars_with_reader_warnings": sum(bool(bar.warnings) for bar in scored),
             "meters": dict(Counter(f"{bar.time_signature[0]}/{bar.time_signature[1]}" for bar in scored)),
             "key": estimate.key, "key_source": estimate.source, "key_confidence": round(estimate.confidence, 3)}
    return scored, estimate.key, facts


def run_real(engine, data: bytes, log=print) -> tuple[dict, dict]:
    """(public aggregate section, private per-bar record) for one real score."""
    bars, key, facts = real_score(data)
    log(f"real score: {facts['bars_total']} bars, {facts['bars_scored']} scored, key {key} ({facts['key_source']})")
    section = {"label": REAL_LABEL, "created": _now(), "complete": False, "stopped": None, **facts}
    private = {"engine": engine.name, "created": section["created"], "key": key, "bars": []}
    tally = Tally()
    try:
        results = engine.analyze([hide_chords(bar) for bar in bars], key)
        for bar, result in zip(bars, results):
            truth = [chord.symbol for chord in bar.chords]
            scores = tally.add_bar(truth, result.chords, result.confidence)
            private["bars"].append({"index": bar.index, "page": bar.page, "system": bar.system, "number": bar.number,
                                    "truth": truth, "truth_slots": list(align(truth)), **result.to_dict(),
                                    "scores": [score.__dict__ for score in scores]})
        section["complete"] = True
    except (SpendLimit, BudgetExceeded, LLMConnectionError, KeyboardInterrupt) as exc:
        section["stopped"] = _stop_reason(exc)
        log(f"stopped: {section['stopped']}")
    calls = [call.to_dict() for call in engine.calls]
    section.update(calls=calls, call_stats=call_stats(calls), cost_usd=round(sum(c["cost_usd"] for c in calls), 6),
                   metrics=tally.summary())
    return section, private


def _dataset_facts(path: Path, records: list[dict]) -> dict:
    return {"path": repo_relative(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "records": len(records), "bars": sum(len(record["bars"]) for record in records),
            "variants": dict(Counter(record["variant"] for record in records))}


def _ledgers() -> list[tuple[str, Ledger]]:
    """The Meta ledger the product spends from and the open-weight run's own Baseten ledger."""
    return [("meta", Ledger.from_env()), ("baseten", Ledger(OPENWEIGHT_LEDGER_PATH, OPENWEIGHT_CAP_USD))]


def _print_ledgers(ledgers: list[tuple[str, Ledger]], before: list[dict] | None = None) -> list[dict]:
    snapshots = [ledger.snapshot() for _, ledger in ledgers]
    for index, ((name, _), snapshot) in enumerate(zip(ledgers, snapshots)):
        change = "" if before is None else f" (+${snapshot['spent_usd'] - before[index]['spent_usd']:.4f})"
        print(f"ledger {name} ({repo_relative(Path(snapshot['path']))}): spent ${snapshot['spent_usd']:.4f} of "
              f"${snapshot['cap_usd']:.2f} {'before' if before is None else 'after'}{change}")
    return snapshots


def _record_not_run(path: Path, engine: str, reason: str) -> None:
    """A results file that says why the engine was not run, written only where none exists yet."""
    if path.exists():
        return
    provider = ENGINE_PROVIDERS[engine]
    model = PROVIDERS[provider].model if provider in PROVIDERS else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"engine": engine, "provider": provider, "model": model, "not_run": reason,
                                "attempted": _now()}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {repo_relative(path)} recording that {engine} was not run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score one engine on the synthetic dataset, one real score or "
                                     "the private real songs.")
    parser.add_argument("--engine", required=True, choices=ENGINES)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--real", type=Path, metavar="SCORE.pdf",
                        help="score this vector PDF instead of the dataset; aggregates only go public")
    source.add_argument("--songs", type=Path, metavar="SONGS.jsonl",
                        help="the owner's private real songs, outside the repository: score excerpts realized "
                             "from them; aggregates only go public")
    parser.add_argument("--private-dir", type=Path,
                        help="folder outside the repo for per-bar outputs (required with --real; with --songs "
                             "default ../.tooling/score-inspection/harmony-eval)")
    parser.add_argument("--max-usd", type=float, help="stop before this provider's recorded spend could pass it "
                        "(default: 4 for meta and auto together, 8 for openweight; with --songs 4 and 6)")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--seed", type=int, default=SEED, help="excerpt choice and realization seed (with --songs)")
    parser.add_argument("--out-dir", type=Path, default=EXPERIMENTS_DIR)
    args = parser.parse_args(argv)
    if args.real and (args.private_dir is None or args.private_dir.resolve().is_relative_to(REPO_ROOT)):
        parser.error("--real needs --private-dir, a folder outside the repository")
    if args.songs:
        try:
            songs_path, private_dir = outside_repo(args.songs), outside_repo(args.private_dir or PRIVATE_DIR)
        except PrivateDataError as exc:
            parser.error(str(exc))

    section_name = "real_songs" if args.songs else "real" if args.real else "synthetic"
    out_path = (real_songs_results_path if args.songs else results_path)(args.engine, args.out_dir)
    existing = load_results(out_path) or {}
    limits = REAL_SONGS_MAX_USD if args.songs else DEFAULT_MAX_USD
    max_usd = args.max_usd if args.max_usd is not None else limits.get(args.engine)
    provider = ENGINE_PROVIDERS[args.engine]
    try:
        ledgers = _ledgers()
        before = _print_ledgers(ledgers)
        prior = prior_spend(args.out_dir, provider, (args.engine, section_name)) if max_usd is not None else 0.0
        engine, _ = build_engine(args.engine, max_usd=max_usd, prior_usd=prior)
    except LLMError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        _record_not_run(out_path, args.engine, str(exc))
        return 1
    if max_usd is not None:
        print(f"prior {provider} spend recorded for this set ${prior:.4f}; limit ${max_usd:.2f}")

    if args.songs:
        songs, dropped, left_out = load_songs(songs_path)
        records = build_real_dataset(songs, args.seed)
        if not records:
            print("no song has an eight-bar run that fits the editor's two slots", file=sys.stderr)
            return 1
        _write_private(private_dir / REAL_SONGS_DATASET_NAME, dumps(records))
        section, outputs = run_real_songs(engine, records)
        _write_private(private_dir / f"real-songs-{args.engine}.jsonl", dumps(outputs))
        print(f"wrote the realized dataset and the per-bar outputs ({len(outputs)} excerpts) to {private_dir}")
        results = {"engine": args.engine, "provider": engine.provider, "model": engine.model,
                   "settings": engine.describe(), "dataset": real_songs_facts(songs, dropped, left_out, records,
                                                                               args.seed),
                   "real_songs": section}
        try:
            assert_aggregate(results, private_strings(songs, records, outputs))
        except PrivateDataError as exc:
            print(f"refusing to write {repo_relative(out_path)}: {exc}", file=sys.stderr)
            _print_ledgers(ledgers, before)
            return 1
    else:
        if args.real:
            section, private = run_real(engine, args.real.read_bytes())
            args.private_dir.mkdir(parents=True, exist_ok=True)
            # Named after the PDF, so no score's title is written into this code
            private_path = args.private_dir / f"harmony-eval-{args.real.stem}-{args.engine}.json"
            private_path.write_text(json.dumps(private, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"wrote the per-bar outputs to the private folder ({len(private['bars'])} bars)")
            dataset_facts = existing.get("dataset")
        else:
            records = load_dataset(args.dataset)
            section = run_synthetic(engine, records)
            dataset_facts = _dataset_facts(args.dataset, records)
        results = {"engine": args.engine, "provider": engine.provider, "model": engine.model,
                   "settings": engine.describe(), "dataset": dataset_facts,
                   "synthetic": existing.get("synthetic"), "real": existing.get("real")}
        results[section_name] = section

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = section["metrics"]
    print(f"{args.engine} {section_name}: {summary['slots']} slots, coverage {summary['coverage']}, "
          f"exact {summary['all']['exact']} (all) / {summary['on_covered']['exact']} (covered), "
          f"cost ${section['cost_usd']:.4f}, calls {section['call_stats']['calls']}")
    print(f"wrote {repo_relative(out_path)}")
    _print_ledgers(ledgers, before)
    return 0 if section["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
