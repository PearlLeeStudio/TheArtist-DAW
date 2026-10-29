"""Second-ear evaluation (row 3 of docs/evaluation.md): does the judge pick among A/B/C better than
the R1 order, and are its stated reasons true?

The inputs are the A/B/C lists of the first section of each of the 20 planner-evaluation runs
(experiments/agent_eval/results/meta-medium.json): real chord-model candidates, reused, so
nothing is generated again. Each list becomes the request the editor sends for a placed
section (frontend reviewStore.buildReviewRequest): the candidates as the editor writes their
chords, the section's empty bars as the original, its section type, and the section before it
(the sketch's last section) from the same offset. Every request goes through the product's
review_candidates three times, once in each cyclic order of the stored candidates (ABC, BCA,
CAB: the stored letters shown as A, B, C), so each candidate is shown once under every letter
and in every place. A judge that chooses by the chords picks the same stored candidate in all
three orders and, over all of them, each shown letter equally often; one that leans on a
letter or a place does neither.

judges    meta        the judge role as shipped: Muse Spark 1.3 on the Meta ledger
          openweight  the judge role as LLM_JUDGE_PROVIDER=baseten configures it: Muse Spark
                      Open on the judge's own ledger
R1 pick   the candidate with the lowest r1Roughness in the review's fact table, i.e. today's R1
          over the chords as they land on the score. The stored letters came from the rerank
          of the planner run, over the chords before voice leading and the song-form rules and
          before the R1 flat-root fix; agreement with stored A is shown beside it.

Each invocation writes <out>/results-<judge>.json after every review (replaced whole, so an
interrupted run keeps what it finished). It stops before a review that could pass --max-usd
(a review reserves at most review.REVIEW_MAX_USD), after a failure every later review would
repeat (Meta disabled, configuration, the ledger cap), after reviews in a row that no provider
answered or that all failed, and on Ctrl-C; the ledgers' caps still apply underneath. No key
and no local path is written. --report prints the tables of experiments/review_eval/summary.md.

    bash scripts/dev.sh py -m scripts.review_eval --judge meta|openweight [--max-usd 1.5] [--limit N]
    bash scripts/dev.sh py -m scripts.review_eval --report

(`uv run --directory backend python -m scripts.review_eval …` from a checkout.)
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.review import FACT_NAMES, MAX_CANDIDATES, ReviewRequest
from app.services import review
from app.services.llm import Ledger, LLMClient, LLMConfig, LLMConfigError, LLMError, OpenAITransport, Transport
from app.services.planner import DIATONIC_GENRES
from scripts.harmony_eval import REPO_ROOT, repo_relative
from scripts.harmony_eval.engines import CountingTransport
from scripts.harmony_eval.metrics import percentile

SOURCE_PATH = REPO_ROOT / "experiments" / "agent_eval" / "results" / "meta-medium.json"
REQUESTS_DIR = REPO_ROOT / "experiments" / "agent_eval" / "requests"
OUT_DIR = REPO_ROOT / "experiments" / "review_eval"
JUDGES = ("meta", "openweight")
# The stored letters in the order they are shown as A, B, C: the three cyclic shifts, so every
# stored candidate is shown once under every letter and in every place
ORDERS = ("ABC", "BCA", "CAB")
DEFAULT_MAX_USD = 1.5
# Failure kinds every later review would repeat, so the invocation stops after one
STOP_KINDS = ("disabled", "config", "budget")
# Failed reviews in a row without a request id (the provider never answered) after which it stops
UNANSWERED_STOP = 2
# Failed reviews in a row of any kind (an HTTP error the provider answered still settles a reservation)
FAILED_STOP = 3
KEY_VARS = ("MODEL_API_KEY", "BASETEN_API_KEY", "FIREWORKS_API_KEY", "LLM_API_KEY", "LLM_JUDGE_API_KEY")
CREATIVITIES = ("conservative", "balanced", "creative")
# The editor's chord symbol limit (models/review.py), which reviewStore.ts cuts a symbol to
MAX_SYMBOL_CHARS = 32
# How LLMClient words a reply that holds no JSON object of the schema: not JSON, off the schema,
# cut at the token limit, or empty
_NO_JSON = ("the message content", "the reply does not match the schema", "the output hit",
            "the response has no message content")
_SPEND_TOLERANCE_USD = 1e-9


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- The inputs ---


def editor_symbol(symbol: str | None) -> str | None:
    """The chord as the editor sends it to the review (chordParser.parseChordName, then
    reviewStore.reviewSymbol): 'Amaj' -> 'A', 'Amin' -> 'Am', the slash bass kept, extensions in
    parentheses. None for an empty slot or a symbol the editor cannot parse: it leaves that slot
    as it was, and a placed section's slots start empty."""
    text = (symbol or "").strip()
    if not text:
        return None
    head, bass = text, ""
    cut = text.rfind("/")
    if cut > 0 and text[cut + 1:] in review._NOTE_NAMES:
        head, bass = text[:cut], text[cut + 1:]
    root_len = 2 if len(head) >= 2 and head[1] in "#b" else 1
    root, rest = head[:root_len], head[root_len:]
    if root not in review._NOTE_NAMES:
        return None
    extensions: list[str] = []
    if match := review._EXTENSIONS.search(rest):
        extensions = [part.strip() for part in match[1].split(",")]
        rest = rest.replace(match[0], "", 1)
    quality = review._QUALITY_ALIASES.get(rest, rest or "maj")
    name = root + ("" if quality == "maj" else "m" if quality == "min" else quality)
    slash = f"/{bass}" if bass else ""
    full = f"{name}({','.join(extensions)}){slash}" if extensions else f"{name}{slash}"
    return full if len(full) <= MAX_SYMBOL_CHARS else f"{name}{slash}"[:MAX_SYMBOL_CHARS]


def _creativity(label: str) -> str | None:
    """'Option B — F1 + LoRA: rock (balanced)' -> 'balanced': the temperature that wrote it."""
    return next((name for name in CREATIVITIES if label.endswith(f"({name})")), None)


def _bars(suggestion: dict[str, Any], start: int, bars: int) -> list[list[str | None]]:
    """A stored suggestion over the section's measures, two editor slots per measure."""
    chords = suggestion["chords"]
    rows = []
    for measure in range(start, start + bars):
        slots = list(chords.get(str(measure), []))[:2]
        rows.append([editor_symbol(slot) for slot in slots + [None] * (2 - len(slots))])
    return rows


def previous_section(body: dict[str, Any], start: int, count: int) -> list[list[str | None]] | None:
    """The section before the one placed at `start`, from offset 0 for at most `count` bars, as
    reviewStore.previousSectionBars takes it from the score; None when the sketch has none."""
    before = [section for section in body.get("sections", []) if section["start"] + section["length"] <= start]
    if not before:
        return None
    previous = max(before, key=lambda section: section["start"])
    measures = body["measures"][previous["start"]:previous["start"] + min(count, previous["length"])]
    return [[editor_symbol(chord) for chord in measure["chords"]] for measure in measures] or None


def _lowest(values: list[tuple[str, float | None]]) -> list[str]:
    present = [(label, value) for label, value in values if value is not None]
    if not present:
        return []
    low = min(value for _, value in present)
    return [label for label, value in present if value == low]


def r1_pick(facts: list[dict[str, Any]]) -> list[str]:
    """The letters holding the lowest r1Roughness, in stored order (more than one on a tie);
    empty when no roughness was computed."""
    return _lowest([(row["label"], row["r1Roughness"]) for row in facts])


def raw_r1_pick(candidates: list[dict[str, Any]], rules_slots: list[int]) -> list[str]:
    """The lowest R1 over the chords closer to what the rerank scored: without the slash basses
    voice leading adds and without the slots the song-form rules wrote (the planner trace's)."""
    rules = set(rules_slots)
    values = []
    for candidate in candidates:
        slots = [chord for measure in candidate["chords"] for chord in measure]
        chords = [chord.split("/")[0] for index, chord in enumerate(slots) if chord and index not in rules]
        values.append((candidate["label"], review._mean_roughness(chords)))
    return _lowest(values)


def load_sections(source: Path = SOURCE_PATH, requests_dir: Path = REQUESTS_DIR) -> list[dict[str, Any]]:
    """One entry per planner run, in the results' order: the first section's stored A/B/C, the
    review request built from it and its fact table."""
    document = json.loads(source.read_text(encoding="utf-8"))
    entries = []
    for run in document["runs"]:
        sections = run["trace"]["sections"]
        if run["status"] != "ok" or not sections:
            raise ValueError(f"{run['request']}: the planner run has no first section to review")
        first = sections[0]
        if len(first["suggestions"]) != MAX_CANDIDATES:
            raise ValueError(f"{run['request']}: {len(first['suggestions'])} candidates; the three cyclic "
                             f"orders need {MAX_CANDIDATES}")
        body = json.loads((requests_dir / f"{run['request']}.json").read_text(encoding="utf-8"))
        start, bars = first["startMeasure"], first["bars"]
        candidates = [{"label": chr(65 + index), "chords": _bars(suggestion, start, bars)}
                      for index, suggestion in enumerate(first["suggestions"])]
        request = ReviewRequest(
            key=run["key"], genre=run["genre"], sectionType=first["sectionType"],
            original=[[None, None] for _ in range(bars)], candidates=candidates,
            previousSection=previous_section(body, start, bars),
        )
        facts = [row.model_dump() for row in review.candidate_facts(request)]
        planner_rules = sorted(first["rulesSlots"])
        entries.append({
            "request": run["request"], "kind": run["kind"], "genre": run["genre"], "key": run["key"],
            "sectionType": first["sectionType"], "bars": bars, "cadence": first["cadence"],
            "regenerated": first["regenerated"], "modelUsed": first["modelUsed"],
            "candidates": [{"letter": chr(65 + index), "label": suggestion["label"],
                            "creativity": _creativity(suggestion["label"])}
                           for index, suggestion in enumerate(first["suggestions"])],
            # A review request carries no cadence, so its rulesSlots are the section type's default;
            # the planner's cadence may have written other slots, which the judge then sees as the model's
            "plannerRulesSlots": planner_rules, "rulesSlotsMatch": planner_rules == facts[0]["rulesSlots"],
            "facts": facts, "r1Pick": r1_pick(facts), "rawR1Pick": raw_r1_pick(candidates, first["rulesSlots"]),
            "body": request.model_dump(mode="json"),
        })
    return entries


def source_facts(source: Path = SOURCE_PATH) -> dict[str, Any]:
    document = json.loads(source.read_text(encoding="utf-8"))
    return {"path": repo_relative(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "ts": document["ts"], "planner": document["planner"], "effort": document["effort"],
            "runs": len(document["runs"])}


def ordered(entry: dict[str, Any], order: str) -> tuple[ReviewRequest, dict[str, str]]:
    """The entry's request with its candidates in `order` (the stored letters shown as A, B, C),
    and the map from a shown letter to the stored one."""
    if order not in ORDERS:
        raise ValueError(f"unknown order {order!r}; expected one of {', '.join(ORDERS)}")
    by_letter = {candidate["label"]: candidate for candidate in entry["body"]["candidates"]}
    letters = {chr(65 + index): stored for index, stored in enumerate(order)}
    body = {**entry["body"], "candidates": [{"label": shown, "chords": by_letter[stored]["chords"]}
                                            for shown, stored in letters.items()]}
    return ReviewRequest(**body), letters


# --- The judges ---


class ReplyCountingTransport(CountingTransport):
    """Counts the requests sent and the replies that came back (a timeout, connection or HTTP
    error got none), so JSON validity is a share of replies."""

    def __init__(self, inner: Transport) -> None:
        super().__init__(inner)
        self.replies = 0

    def __call__(self, request: dict) -> tuple[dict, Mapping[str, str]]:
        result = super().__call__(request)
        self.replies += 1
        return result


def judge_client(judge: str, env: Mapping[str, str] | None = None,
                 transport: Transport | None = None) -> tuple[LLMClient, ReplyCountingTransport]:
    """The judge role's client as the product configures it, with a transport that counts requests
    and replies so an open-weight JSON-guard retry shows: meta = the judge with no provider of its
    own (the default Meta client and ledger), openweight = LLM_JUDGE_PROVIDER=baseten (Muse Spark
    Open, the judge's own ledger). LLMConfigError when the provider or its key is not usable."""
    env = dict(os.environ if env is None else env)
    if judge not in JUDGES:
        raise ValueError(f"unknown judge {judge!r}; expected one of {', '.join(JUDGES)}")
    env["LLM_JUDGE_PROVIDER"] = "baseten" if judge == "openweight" else ""
    config = LLMConfig.from_env(env, role="judge")
    if judge == "meta" and config.provider != "meta":
        raise LLMConfigError(f"the meta judge needs LLM_PROVIDER=meta, not {config.provider}")
    if not config.api_key:
        raise LLMConfigError(f"{config.key_source} is not set, so provider {config.provider} cannot be called")
    counting = ReplyCountingTransport(transport if transport is not None else OpenAITransport(config))
    return LLMClient(config, Ledger.from_env(env, role="judge"), counting), counting


def fact_rank(facts: list[dict[str, Any]], chosen: str, name: str) -> str | None:
    """'lowest' or 'highest' when the chosen candidate alone holds that extreme of the fact, as the
    editor ranks a confirmed reason (reviewStore.factRank); 'neither' on a tie or in the middle;
    None when fewer than two candidates have the fact."""
    values = {row["label"]: row[name] for row in facts if row[name] is not None}
    if chosen not in values or len(values) < 2:
        return None
    mine = values[chosen]
    others = [value for label, value in values.items() if label != chosen]
    if all(mine < other for other in others):
        return "lowest"
    if all(mine > other for other in others):
        return "highest"
    return "neither"


def run_review(entry: dict[str, Any], order: str, client: LLMClient,
               counting: ReplyCountingTransport) -> dict[str, Any]:
    """One product review of the entry in `order`: the choice in stored letters and every reason
    with the chosen candidate's rank on the fact it cites, or the failure."""
    request, letters = ordered(entry, order)
    attempts_before, replies_before = counting.attempts, counting.replies
    record: dict[str, Any] = {"request": entry["request"], "order": order, "letters": letters}
    try:
        result = review.review_candidates(request, client=client)
    except review.ReviewFailure as failure:
        return record | {
            "status": "error", "choice": None, "choiceStored": None, "reasons": [], "factsAsBuilt": None,
            "error": {"kind": failure.kind, "message": failure.message, "requestId": failure.request_id},
            "requestId": failure.request_id, "costUsd": failure.cost_usd, "latencyMs": failure.latency_ms,
            "attempts": counting.attempts - attempts_before, "replies": counting.replies - replies_before,
        }
    stored = letters[result.choice]
    shown_facts = sorted(({**row.model_dump(), "label": letters[row.label]} for row in result.facts),
                         key=lambda row: row["label"])
    reasons = [{**reason.model_dump(), "rank": fact_rank(entry["facts"], stored, reason.factName)}
               for reason in result.reasons]
    return record | {
        "status": "ok", "choice": result.choice, "choiceStored": stored, "reasons": reasons,
        # The facts are code: the same chords in another order must give the same table
        "factsAsBuilt": shown_facts == sorted(entry["facts"], key=lambda row: row["label"]),
        "error": None, "requestId": result.requestId, "costUsd": result.costUsd, "latencyMs": result.latencyMs,
        "attempts": counting.attempts - attempts_before, "replies": counting.replies - replies_before,
        "provider": result.provider, "model": result.model,
    }


def scrubbed(text: str) -> str:
    """The results text with the local paths replaced; a key in it is a bug, so nothing is written."""
    for var in KEY_VARS:
        key = os.environ.get(var, "")
        if len(key) >= 8 and key in text:
            raise RuntimeError(f"the value of {var} appeared in the results; nothing was written")
    return text.replace(str(REPO_ROOT), "<repo>").replace(str(Path.home()), "~")


def write_results(path: Path, document: dict[str, Any]) -> None:
    """The results replaced whole (temp file + os.replace, as Ledger writes), so a failed write keeps the last."""
    text = scrubbed(json.dumps(document, indent=1, ensure_ascii=False)) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        # backslashreplace keeps an unpaired surrogate in a judge's claim from failing the write
        with os.fdopen(fd, "w", encoding="utf-8", errors="backslashreplace") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _ledger_facts(ledger: Ledger) -> dict[str, Any]:
    snapshot = ledger.snapshot()
    return {"path": repo_relative(Path(snapshot["path"])), "capUsd": snapshot["cap_usd"],
            "spentUsd": snapshot["spent_usd"], "outstandingUsd": snapshot["outstanding_usd"]}


def _line(index: int, total: int, record: dict[str, Any]) -> str:
    if record["status"] == "ok":
        confirmed = sum(reason["confirmed"] for reason in record["reasons"])
        outcome = (f"chose {record['choice']} (stored {record['choiceStored']}), reasons confirmed "
                   f"{confirmed}/{len(record['reasons'])}")
    else:
        outcome = f"ERR {record['error']['kind']}: {record['error']['message']}"
    return (f"{index:2d}/{total} {record['request']:32s} order {record['order']}  {outcome}  "
            f"${record['costUsd']:.4f}  {record['latencyMs'] / 1000:.1f} s  sent {record['attempts']}")


def _stop_reason(record: dict[str, Any], failed_streak: int, unanswered: int) -> str | None:
    error = record["error"]
    if error and error["kind"] in STOP_KINDS:
        return f"{error['kind']} failure every later review would repeat"
    if unanswered >= UNANSWERED_STOP:
        return f"{unanswered} reviews in a row got no answer from the provider"
    if failed_streak >= FAILED_STOP:
        return f"{failed_streak} reviews in a row failed"
    return None


def run_all(judge: str, entries: list[dict[str, Any]], client: LLMClient, counting: ReplyCountingTransport,
            max_usd: float, out_path: Path, source: dict[str, Any], say=print) -> dict[str, Any]:
    """Every entry in the three orders under the spend limit; the results document, also written to out_path."""
    cfg = client.config
    start_usd = client.ledger.snapshot()["spent_usd"]
    document: dict[str, Any] = {
        "ts": _now(), "judge": judge, "provider": cfg.provider, "model": cfg.model,
        "effort": review.REVIEW_EFFORT if cfg.reasoning_effort is not None else None,
        "limits": {"maxUsd": max_usd, "reviewMaxUsd": review.REVIEW_MAX_USD,
                   "reviewMaxTokens": review.REVIEW_MAX_TOKENS, "reviewTimeoutS": review.REVIEW_TIMEOUT_S},
        "source": source, "orders": list(ORDERS),
        "ledger": {"before": _ledger_facts(client.ledger), "after": None},
        "spentUsd": 0.0, "stopped": None, "sections": entries, "reviews": [],
    }
    total = len(entries) * len(ORDERS)
    say(f"judge {judge}: {cfg.provider} {cfg.model}, {len(entries)} sections x {len(ORDERS)} orders, "
        f"--max-usd ${max_usd:.2f}; ledger {document['ledger']['before']['path']} spent "
        f"${document['ledger']['before']['spentUsd']:.4f} of ${document['ledger']['before']['capUsd']:.2f}")
    failed_streak = unanswered = 0

    def not_run() -> str:
        return f"{total - len(document['reviews'])} reviews not run"

    try:
        for entry in entries:
            for order in ORDERS:
                spent = round(client.ledger.snapshot()["spent_usd"] - start_usd, 8)
                if spent + review.REVIEW_MAX_USD > max_usd + _SPEND_TOLERANCE_USD:
                    document["stopped"] = (f"spent ${spent:.4f} + one review's cap ${review.REVIEW_MAX_USD:.2f} "
                                           f"would pass --max-usd ${max_usd:.2f}; {not_run()}")
                    break
                record = run_review(entry, order, client, counting)
                document["reviews"].append(record)
                document["spentUsd"] = round(client.ledger.snapshot()["spent_usd"] - start_usd, 8)
                document["ledger"]["after"] = _ledger_facts(client.ledger)
                write_results(out_path, document)
                say(_line(len(document["reviews"]), total, record))
                failed = record["status"] != "ok"
                failed_streak = failed_streak + 1 if failed else 0
                unanswered = unanswered + 1 if failed and not record["requestId"] else 0
                if (reason := _stop_reason(record, failed_streak, unanswered)) is not None:
                    document["stopped"] = f"{reason}; {not_run()}"
                    break
            if document["stopped"]:
                break
    except KeyboardInterrupt:
        document["stopped"] = f"interrupted; {not_run()}"
    document["spentUsd"] = round(client.ledger.snapshot()["spent_usd"] - start_usd, 8)
    document["ledger"]["after"] = _ledger_facts(client.ledger)
    write_results(out_path, document)
    failures = sum(1 for record in document["reviews"] if record["status"] != "ok")
    say(f"{len(document['reviews'])} reviews, {failures} failed, spent ${document['spentUsd']:.4f}"
        + (f"; stopped: {document['stopped']}" if document["stopped"] else ""))
    return document


# --- The numbers ---


def _rate(hits: int, total: int) -> str:
    return "-" if total == 0 else f"{hits}/{total} ({100 * hits / total:.0f}%)"


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _number(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _seconds(records: list[dict[str, Any]]) -> str:
    latencies = [record["latencyMs"] / 1000 for record in records]
    if not latencies:
        return "-"
    return f"{percentile(latencies, .5):.1f} / {percentile(latencies, .95):.1f}"


def _facts_by_letter(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["label"]: row for row in entry["facts"]}


def _most_in_key(entry: dict[str, Any], letter: str) -> bool:
    """Whether the candidate is among the candidates with the lowest outOfKeyRatio."""
    values = [row["outOfKeyRatio"] for row in entry["facts"] if row["outOfKeyRatio"] is not None]
    mine = _facts_by_letter(entry)[letter]["outOfKeyRatio"]
    return bool(values) and mine is not None and mine == min(values)


def _chance(entries: list[dict[str, Any]], hits) -> float | None:
    """The expected share of a uniformly random pick that `hits` (entry, letter) counts as a hit."""
    if not entries:
        return None
    return statistics.fmean(sum(bool(hits(entry, row["label"])) for row in entry["facts"]) / len(entry["facts"])
                            for entry in entries)


def _baseline(entry: dict[str, Any]) -> str:
    """The R1 order's pick: the lowest roughness, the earliest stored letter on a tie (stored A without R1)."""
    return entry["r1Pick"][0] if entry["r1Pick"] else "A"


def _sent(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The reviews that sent at least one request; one refused before its send (ledger cap) sent none."""
    return [record for record in records if record["attempts"] > 0]


def order_metrics(entries: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers over one set of review records (one order, or all pooled). A failed review counts
    as no agreement in the (all) columns and is left out of the (completed) ones; cost and latency
    cover every review that sent a request, failures included."""
    done = [record for record in records if record["status"] == "ok"]
    sent = _sent(records)
    reasons = [reason for record in done for reason in record["reasons"]]
    confirmed = [reason for reason in reasons if reason["confirmed"]]
    ranks = Counter(reason["rank"] or "n/a" for reason in confirmed)
    failures = Counter(record["error"]["kind"] for record in records if record["error"])
    r1_hits = sum(record["choiceStored"] in entries[record["request"]]["r1Pick"] for record in done)
    a_hits = sum(record["choiceStored"] == "A" for record in done)
    attempts = sum(record["attempts"] for record in sent)
    replies = sum(record["replies"] for record in sent)
    retries = sum(record["attempts"] - 1 for record in sent)
    # Each JSON-guard retry was earned by one reply that was not the JSON; so was the last reply of a
    # review that failed on it, and the reply whose retry the ledger then refused (budget after a send)
    no_json = sum(1 for record in sent if record["error"] and (
        (record["error"]["kind"] == "llm" and record["error"]["message"].startswith(_NO_JSON))
        or record["error"]["kind"] == "budget"))
    refused = len(records) - len(sent)
    return {
        "reviews": len(records), "completed": _rate(len(done), len(records)),
        "shownPicks": " / ".join(str(sum(record["choice"] == letter for record in done)) for letter in "ABC"),
        "r1Agree": _rate(r1_hits, len(records)), "r1AgreeCompleted": _rate(r1_hits, len(done)),
        "storedAAgree": _rate(a_hits, len(records)), "storedAAgreeCompleted": _rate(a_hits, len(done)),
        "reasonsPerReview": _number(len(reasons) / len(done), 2) if done else "-",
        "confirmed": _rate(len(confirmed), len(reasons)),
        "ranks": " / ".join(str(ranks[name]) for name in ("lowest", "highest", "neither")),
        "usdPerReview": _number(_mean([record["costUsd"] for record in sent]), 4),
        "usdTotal": f"{sum(record['costUsd'] for record in records):.4f}",
        "latency": _seconds(sent),
        "attempts": f"{attempts} ({retries} retries" + (f", {refused} refused unsent)" if refused else ")"),
        "jsonValidity": "-" if replies == 0 else f"{100 * (1 - (retries + no_json) / replies):.0f}%",
        "failures": ", ".join(f"{kind} {count}" for kind, count in sorted(failures.items())) or "none",
    }


def consistency_metrics(entries: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    """Position consistency over the sections every order completed, and what the picks look like
    over every completed review (all orders pooled)."""
    picks: dict[str, dict[str, str]] = {}
    run: dict[str, set[str]] = {}
    for record in records:
        run.setdefault(record["request"], set()).add(record["order"])
        if record["status"] == "ok":
            picks.setdefault(record["request"], {})[record["order"]] = record["choiceStored"]
    complete = {name: orders for name, orders in picks.items() if len(orders) == len(ORDERS)}
    with_failure = sum(1 for name, orders in run.items() if len(orders) == len(ORDERS)
                       and len(picks.get(name, {})) < len(ORDERS))
    pairs = [(orders[a], orders[b]) for orders in picks.values()
             for i, a in enumerate(ORDERS) for b in ORDERS[i + 1:] if a in orders and b in orders]
    chosen = [(entries[name], letter) for name, orders in picks.items() for letter in orders.values()]
    creativity = Counter(next(c["creativity"] for c in entry["candidates"] if c["letter"] == letter) or "unknown"
                         for entry, letter in chosen)
    diatonic = [(entry, letter) for entry, letter in chosen if entry["genre"] in DIATONIC_GENRES]

    def mean_fact(name: str) -> float | None:
        values = [_facts_by_letter(entry)[letter][name] for entry, letter in chosen]
        return _mean([value for value in values if value is not None])

    return {
        "complete": len(complete), "withFailure": with_failure,
        "consistent": _rate(sum(len(set(orders.values())) == 1 for orders in complete.values()), len(complete)),
        "pairwise": _rate(sum(a == b for a, b in pairs), len(pairs)),
        "storedPicks": " / ".join(str(sum(letter == stored for _, letter in chosen)) for stored in "ABC"),
        "creativity": " / ".join(str(creativity[name]) for name in CREATIVITIES),
        "meanRoughness": _number(mean_fact("r1Roughness")), "meanOutOfKey": _number(mean_fact("outOfKeyRatio")),
        "diatonicInKey": _rate(sum(_most_in_key(entry, letter) for entry, letter in diatonic), len(diatonic)),
    }


def baseline_metrics(entries: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The R1 pick, stored A and a uniformly random pick over exactly the reviews the judge completed,
    one per completed review as its picks are pooled, so both sides cover the same lists."""
    covered = [entries[record["request"]] for record in records if record["status"] == "ok"]
    diatonic = [entry for entry in covered if entry["genre"] in DIATONIC_GENRES]

    def described(pairs: list[tuple[dict[str, Any], str]]) -> dict[str, Any]:
        def mean_fact(name: str) -> float | None:
            values = [_facts_by_letter(entry)[letter][name] for entry, letter in pairs]
            return _mean([value for value in values if value is not None])
        in_key = [(entry, letter) for entry, letter in pairs if entry["genre"] in DIATONIC_GENRES]
        return {"n": len(pairs), "meanRoughness": _number(mean_fact("r1Roughness")),
                "meanOutOfKey": _number(mean_fact("outOfKeyRatio")),
                "diatonicInKey": _rate(sum(_most_in_key(entry, letter) for entry, letter in in_key), len(in_key))}

    def expected(name: str) -> float | None:
        means = [_mean([row[name] for row in entry["facts"] if row[name] is not None]) for entry in covered]
        return _mean([value for value in means if value is not None])

    random_in_key = _chance(diatonic, _most_in_key)
    return {
        "R1 pick (lowest r1Roughness)": described([(entry, _baseline(entry)) for entry in covered]),
        "stored A (the planner run's order)": described([(entry, "A") for entry in covered]),
        "random pick (expected)": {"n": len(covered), "meanRoughness": _number(expected("r1Roughness")),
                                   "meanOutOfKey": _number(expected("outOfKeyRatio")),
                                   "diatonicInKey": "-" if random_in_key is None else f"{100 * random_in_key:.0f}%"},
    }


def judges_agree(documents: dict[str, dict[str, Any]]) -> str | None:
    """How often the two judges chose the same candidate for the same section and order."""
    if len(documents) < 2:
        return None
    picks = [{(r["request"], r["order"]): r["choiceStored"] for r in document["reviews"] if r["status"] == "ok"}
             for document in documents.values()]
    both = set(picks[0]) & set(picks[1])
    return _rate(sum(picks[0][pair] == picks[1][pair] for pair in both), len(both))


def input_facts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """What the lists are: kinds, previous sections, R1 ties, rules-slot mismatches and how often
    stored A is the R1 pick."""
    return {
        "sections": len(entries), "kinds": dict(Counter(entry["kind"] for entry in entries)),
        "genres": len({entry["genre"] for entry in entries}),
        "diatonic": sum(entry["genre"] in DIATONIC_GENRES for entry in entries),
        "withPrevious": sum(entry["body"]["previousSection"] is not None for entry in entries),
        "bars": dict(sorted(Counter(entry["bars"] for entry in entries).items())),
        "r1Ties": sum(len(entry["r1Pick"]) > 1 for entry in entries),
        "noR1": sum(not entry["r1Pick"] for entry in entries),
        "storedAIsR1": sum("A" in entry["r1Pick"] for entry in entries),
        "storedAIsRawR1": sum("A" in entry["rawR1Pick"] for entry in entries),
        "r1Chance": _chance(entries, lambda entry, letter: letter in entry["r1Pick"]),
        "rulesMismatch": [entry["request"] for entry in entries if not entry["rulesSlotsMatch"]],
    }


# --- The report ---

_ORDER_COLUMNS = (
    ("reviews", "reviews"), ("completed", "completed"), ("shown A / B / C", "shownPicks"),
    ("agrees with R1 pick (all)", "r1Agree"), ("agrees with R1 pick (completed)", "r1AgreeCompleted"),
    ("agrees with stored A (all)", "storedAAgree"), ("agrees with stored A (completed)", "storedAAgreeCompleted"),
    ("reasons / review", "reasonsPerReview"), ("reasons confirmed", "confirmed"),
    ("confirmed fact: lowest / highest / neither", "ranks"), ("USD / review", "usdPerReview"),
    ("USD total", "usdTotal"), ("p50 / p95 (s)", "latency"), ("requests sent", "attempts"),
    ("JSON validity", "jsonValidity"), ("failures", "failures"),
)
_CONSISTENCY_COLUMNS = (
    ("sections every order completed", "complete"), ("sections with a failed order", "withFailure"),
    ("same candidate in all orders", "consistent"), ("same candidate, order pairs", "pairwise"),
    ("picks: stored A / B / C", "storedPicks"), ("picks: conservative / balanced / creative", "creativity"),
    ("mean r1Roughness", "meanRoughness"), ("mean outOfKeyRatio", "meanOutOfKey"),
    ("diatonic genres: most in-key", "diatonicInKey"),
)


def _table(columns: tuple[tuple[str, str], ...], rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    header = "| | " + " | ".join(name for name, _ in columns) + " |"
    rule = "|---|" + "|".join("---" if key == "failures" else "---:" for _, key in columns) + "|"
    return [header, rule, *("| " + " | ".join([label, *(str(values[key]) for _, key in columns)]) + " |"
                            for label, values in rows)]


def _judge_label(document: dict[str, Any]) -> str:
    return f"{document['judge']} ({document['provider']} {document['model']}, effort {document['effort']})"


def _union_sections(documents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every file's sections once, in source order; ValueError when two files hold different inputs
    for one section (another code version, or another source)."""
    entries: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for judge, document in documents.items():
        for entry in document["sections"]:
            known = seen.get(entry["request"])
            if known is None:
                seen[entry["request"]] = entry
                entries.append(entry)
            elif known != entry:
                raise ValueError(f"{entry['request']}: results-{judge}.json holds other inputs for this section than "
                                 "another results file; rerun the judges on one source and one code version")
    return entries


def report(out_dir: Path = OUT_DIR) -> str:
    """Markdown tables over the results files in the folder: one block per judge and order, the
    position consistency, the picks against the R1 order, the cited facts and the per-section picks."""
    documents = {}
    for judge in JUDGES:
        path = out_dir / f"results-{judge}.json"
        if path.exists():
            documents[judge] = json.loads(path.read_text(encoding="utf-8"))
    if not documents:
        raise FileNotFoundError(f"no results-<judge>.json files in {out_dir}")
    if len({json.dumps(document["source"], sort_keys=True) for document in documents.values()}) > 1:
        raise ValueError("the results files were built from different planner runs; rerun them on one source")
    first = next(iter(documents.values()))
    entries = _union_sections(documents)
    by_name = {entry["request"]: entry for entry in entries}
    facts = input_facts(entries)
    kinds = facts["kinds"]
    lengths = ", ".join(f"{count} × {bars}" for bars, count in facts["bars"].items())
    mismatch = facts["rulesMismatch"]
    lines = [
        "## Inputs", "",
        f"{facts['sections']} A/B/C lists, the first section of each run in `{first['source']['path']}` "
        f"({first['source']['planner']} planner, effort {first['source']['effort']}, run {first['source']['ts']}, "
        f"sha256 `{first['source']['sha256'][:12]}…`): {kinds.get('new', 0)} new songs, "
        f"{kinds.get('complete', 0)} completions and {kinds.get('tight', 0)} tight completions in "
        f"{facts['genres']} genres ({facts['diatonic']} lists in genres that usually stay in key); section "
        f"lengths (lists × bars) {lengths}; {facts['withPrevious']} with a previous section. Each list is judged "
        f"in the {len(ORDERS)} cyclic orders {', '.join(ORDERS)} (the stored letters shown as A, B, C). R1 ties: "
        f"{facts['r1Ties']}, lists without R1: {facts['noR1']}. Stored A holds the lowest r1Roughness of the "
        f"review's fact table in {facts['storedAIsR1']} of {facts['sections']} lists, and the lowest R1 over the "
        f"same chords without slash basses and rules slots (closer to what the rerank scored) in "
        f"{facts['storedAIsRawR1']}; a random pick would agree with the R1 pick "
        f"{100 * (facts['r1Chance'] or 0):.0f}% of the time.",
    ]
    if mismatch:
        lines += ["", f"In {len(mismatch)} lists ({', '.join(mismatch)}, marked † below) the planner's cadence wrote "
                      "slots the review's rulesSlots do not list (a review request carries no cadence, so its rules "
                      "slots are the section type's default): the judge saw those rules-written chords as the model's."]
    lines += ["", "## Each judge and order", ""]
    rows = []
    for judge, document in documents.items():
        for order in ORDERS:
            records = [record for record in document["reviews"] if record["order"] == order]
            rows.append((f"{judge}, order {order}", order_metrics(by_name, records)))
        rows.append((f"{judge}, all orders", order_metrics(by_name, document["reviews"])))
    lines += _table(_ORDER_COLUMNS, rows)
    lines += ["", "A failed review counts as no agreement in the (all) columns and is left out of the (completed) "
                  "ones; cost and latency cover every review that sent a request, failures included. JSON validity "
                  "is the share of replies that held the schema's JSON; a timeout, connection or HTTP error got no "
                  "reply and is left out, a reply cut at the token limit or empty counts as not JSON. Over all orders "
                  "a judge that chooses by the chords picks each shown letter equally often.", ""]
    for judge, document in documents.items():
        after = document["ledger"]["after"] or document["ledger"]["before"]
        lines.append(f"- `{judge}`: {_judge_label(document)}, {document['ts']}, {len(document['reviews'])} reviews"
                     + (f", stopped: {document['stopped']}" if document["stopped"] else "")
                     + f"; ledger `{document['ledger']['before']['path']}` ${document['ledger']['before']['spentUsd']:.4f}"
                     f" → ${after['spentUsd']:.4f} of ${document['ledger']['before']['capUsd']:.2f}; limits "
                     f"{document['limits']}")
    lines += ["", "## Position consistency and what the picks look like (all orders pooled)", ""]
    lines += _table(_CONSISTENCY_COLUMNS, [(judge, consistency_metrics(by_name, document["reviews"]))
                                           for judge, document in documents.items()])
    if (agreement := judges_agree(documents)) is not None:
        lines += ["", f"The two judges chose the same candidate in {agreement} of the reviews both completed "
                      "(same section, same order)."]
    lines += ["", "The baselines over the same completed reviews (one row per judge):", "",
              "| judge | baseline | N | mean r1Roughness | mean outOfKeyRatio | diatonic genres: most in-key |",
              "|---|---|---:|---:|---:|---:|"]
    for judge, document in documents.items():
        for name, values in baseline_metrics(by_name, document["reviews"]).items():
            lines.append(f"| {judge} | {name} | {values['n']} | {values['meanRoughness']} | {values['meanOutOfKey']} | "
                         f"{values['diatonicInKey']} |")
    lines += ["", "## Facts the reasons cite", "", "| judge | fact | cited | confirmed |", "|---|---|---:|---:|"]
    for judge, document in documents.items():
        reasons = [reason for record in document["reviews"] for reason in record["reasons"]]
        for name in FACT_NAMES:
            cited = [reason for reason in reasons if reason["factName"] == name]
            lines.append(f"| {judge} | {name} | {len(cited)} | {_rate(sum(r['confirmed'] for r in cited), len(cited))} |")
    columns = [(judge, order) for judge in documents for order in ORDERS]
    lines += ["", "## Per section (stored letters)", "",
              "| request | genre | section | bars | R1 pick | " + " | ".join(f"{j} {o}" for j, o in columns) + " |",
              "|---|---|---|---:|---|" + "---|" * len(columns)]
    for entry in entries:
        cells = []
        for judge, order in columns:
            record = next((r for r in documents[judge]["reviews"] if r["request"] == entry["request"]
                           and r["order"] == order), None)
            if record is None:
                cells.append("not run")
            elif record["status"] != "ok":
                cells.append(f"error ({record['error']['kind']})")
            else:
                confirmed = sum(reason["confirmed"] for reason in record["reasons"])
                cells.append(f"{record['choiceStored']} ({confirmed}/{len(record['reasons'])})")
        section = entry["sectionType"] + ("†" if not entry["rulesSlotsMatch"] else "")
        r1 = "=".join(entry["r1Pick"]) or "-"
        lines.append(f"| {entry['request']} | {entry['genre']} | {section} | {entry['bars']} | {r1} | "
                     + " | ".join(cells) + " |")
    lines += ["", "A cell is the stored letter the judge chose and its confirmed / stated reasons."]
    return "\n".join(lines) + "\n"


# --- Entry point ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge the planner evaluation's A/B/C lists with the second ear.")
    parser.add_argument("--judge", choices=JUDGES, help="meta: Muse Spark 1.3; openweight: Muse Spark Open on Baseten")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD,
                        help=f"stop before a review that could pass this spend (default {DEFAULT_MAX_USD:g})")
    parser.add_argument("--limit", type=int, help="only the first N sections")
    parser.add_argument("--source", type=Path, default=SOURCE_PATH, help="planner results with the A/B/C lists")
    parser.add_argument("--requests", type=Path, default=REQUESTS_DIR, help="the planner request files")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="folder of the results files")
    parser.add_argument("--report", action="store_true", help="print the summary tables from --out and exit")
    args = parser.parse_args(argv)
    if args.report:
        print(report(args.out), end="")
        return 0
    if args.judge is None:
        parser.error("--judge is required unless --report is given")
    if not (math.isfinite(args.max_usd) and args.max_usd > 0):
        parser.error("--max-usd must be a positive number")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    entries = load_sections(args.source, args.requests)[:args.limit]
    try:
        client, counting = judge_client(args.judge)
    except LLMError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    out = args.out / f"results-{args.judge}.json"
    document = run_all(args.judge, entries, client, counting, args.max_usd, out, source_facts(args.source))
    print(f"wrote {repo_relative(out)}")
    return 1 if document["stopped"] or any(record["status"] != "ok" for record in document["reviews"]) else 0


if __name__ == "__main__":
    sys.exit(main())
