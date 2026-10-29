"""Second ear: the judge role picks one of the A/B/C candidates of a Generate, on facts code computed.

Code builds a fact table per candidate (chords outside the key, slots changed from the
original, repetition of the previous section, mean Sethares roughness, the slots the
song-form rules write). One judge call under a strict schema (enums for the choice and the
fact names) returns the choice and at most two reasons, each citing one fact of the chosen
candidate; code checks every cited value against the table and marks the reason confirmed
or not (a model statement). Any failure is raised as a ReviewFailure with the planner's
kinds; nothing falls back to the R1 order.
"""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any

from app.models.review import (
    FACT_NAMES,
    MAX_CLAIM_CHARS,
    MAX_REASONS,
    CandidateFacts,
    ReviewReason,
    ReviewRequest,
    ReviewResponse,
)
from app.services import inference
from app.services.llm import LLMClient, LLMError, LLMResult, get_client
from app.services.planner import DIATONIC_GENRES, _in_key, _key_collection, _kind, _message, _spent, _symbol
from app.services.song_form import rule_slots

REVIEW_LABEL = "review"
REVIEW_SCHEMA_NAME = "candidate_review"
REVIEW_EFFORT = "low"
REVIEW_TIMEOUT_S = 30.0
REVIEW_MAX_USD = 0.03        # the limiter's worst case, and the cap on the call's reservations
# Reasoning tokens count toward it. Real low-effort judgments ran out of 1024 and used up to 1656;
# 4096 would push an open-weight judge's doubled worst case past REVIEW_MAX_USD
REVIEW_MAX_TOKENS = 2048
_COUNT_FACTS = frozenset({"changedSlots"})
# A cited ratio or roughness may be rounded to two decimals; counts must match exactly
_TOLERANCE = 0.005
_RELATIVE_TOLERANCE = 0.01

REVIEW_SYSTEM_PROMPT = f"""You are the second ear in a chord editor. The chord model wrote two or three candidates for the
same bars of a song and the user will pick one. For each candidate an analyzer computed facts over its
chords as they would land on the score:
- outOfKeyRatio: share of its chords with a tone outside the song's key (null without chords)
- changedSlots: chord slots that differ from the original bars
- repetitionVsPrevious: share of its chords equal to the previous section's chord in the same slot (null
  without a previous section)
- r1Roughness: mean Sethares sensory roughness per chord, lower is more consonant (null when not computed)
- rulesSlots: slots the song-form rules write for the section type (its cadence); they are the rules'
  choice, not the model's, so never credit a candidate for them
Pick the candidate that suits the genre, key and section best. Genres that usually stay in key:
{", ".join(DIATONIC_GENRES)}; jazz, bossa, blues, funk and R&B welcome chromatic chords. A section that
repeats the previous one adds little contrast unless it is meant to return. Give one or two reasons; each
cites one fact of the candidate you chose, its factName and its value exactly as the table gives it,
with a claim of one short sentence (at most {MAX_CLAIM_CHARS} characters). Reply with one JSON object
{{"choice", "reasons": [{{"factName", "value", "claim"}}]}} and nothing else."""

# The editor's quality aliases (frontend chordParser.ts), so 'C' and 'Cmaj' or 'Am' and 'Amin'
# are one chord there and here; any other quality text is compared as written
_QUALITY_ALIASES = {"": "maj", "M": "maj", "major": "maj", "m": "min", "minor": "min", "M7": "maj7",
                    "min7": "m7", "o7": "dim7", "ø7": "m7b5", "+": "aug", "+7": "aug7", "7#5": "aug7",
                    "sus": "sus4"}
_NOTE_NAMES = frozenset("C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B B# Cb E# Fb".split())
_EXTENSIONS = re.compile(r"\(([^)]+)\)")
_ALTERED_TRIAD = re.compile(r"\A([A-G][#b]?)\([^)]*\)")


class ReviewFailure(Exception):
    """A review that ended without a choice: kind and message become the response's error."""

    def __init__(self, kind: str, message: str, request_id: str | None = None, *, provider: str | None = None,
                 model: str | None = None, cost_usd: float = 0.0, latency_ms: int = 0) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.request_id = request_id
        self.provider = provider
        self.model = model
        self.cost_usd = cost_usd
        self.latency_ms = latency_ms


# --- Facts ---


def _slot(symbol: str | None) -> str | None:
    return (symbol or "").strip() or None


def _flat(bars: list[list[str | None]]) -> list[str | None]:
    return [_slot(symbol) for measure in bars for symbol in measure]


def _chord_key(symbol: str | None, with_bass: bool = True) -> tuple | str | None:
    """A chord as the editor compares two chords (generationComparison.ts): root and slash bass as
    spelled, the quality under the editor's aliases, the extensions in parentheses; text it cannot
    read stays text."""
    text = _slot(symbol)
    if text is None:
        return None
    head, bass = text, ""
    cut = text.rfind("/")
    if cut > 0 and text[cut + 1:] in _NOTE_NAMES:
        head, bass = text[:cut], text[cut + 1:]
    root_len = 2 if len(head) >= 2 and head[1] in "#b" else 1
    root, rest = head[:root_len], head[root_len:]
    if root not in _NOTE_NAMES:
        return text
    extensions: tuple[str, ...] = ()
    if match := _EXTENSIONS.search(rest):
        extensions = tuple(sorted(part.strip() for part in match[1].split(",")))
        rest = rest.replace(match[0], "", 1)
    return root, _QUALITY_ALIASES.get(rest, rest or "maj"), extensions, bass if with_bass else ""


def _music21_symbol(symbol: str) -> str:
    """The editor's symbol as the physics code reads it: extensions without parentheses (C7(b9) -> C7b9),
    which music21 does not voice; ai/physics respells flats itself."""
    # An alteration right after a bare root ('C(b9)') would otherwise read as a flat root ('Cb9'): drop it
    bare = _ALTERED_TRIAD.sub(r"\1", symbol)
    return bare.replace("(", "").replace(")", "").replace(",", "")


def _outside_key(chord: str, collection: frozenset[int]) -> bool:
    """A chord with a tone outside the key, without its slash bass as the planner reads it; a
    symbol the parser cannot read counts as outside."""
    core = _symbol(chord)
    return core is None or not _in_key(core, collection)


def _mean_roughness(chords: list[str]) -> float | None:
    """R1 as inference's rerank computes it (ai/physics), over every chord music21 can voice."""
    if not inference.PHYSICS_AVAILABLE or not chords:
        return None
    total, scored = inference.sequence_roughness([_music21_symbol(chord) for chord in chords])
    return round(total / scored, 3) if scored else None


def candidate_facts(request: ReviewRequest) -> list[CandidateFacts]:
    """One row per candidate, in request order. Every ratio counts the candidate's filled slots."""
    original = _flat(request.original)
    previous = _flat(request.previousSection) if request.previousSection is not None else None
    collection = _key_collection(request.key)
    rules = rule_slots(request.sectionType, len(original)) if request.sectionType else []
    rows = []
    for candidate in request.candidates:
        chords = _flat(candidate.chords)
        filled = [chord for chord in chords if chord]
        outside = sum(1 for chord in filled if _outside_key(chord, collection))
        changed = sum(1 for mine, theirs in zip(chords, original) if _chord_key(mine) != _chord_key(theirs))
        repetition = None
        if previous is not None:
            placed = [i for i, chord in enumerate(chords[:len(previous)]) if chord]
            same = sum(1 for i in placed if _chord_key(chords[i], False) == _chord_key(previous[i], False))
            repetition = round(same / len(placed), 3) if placed else None
        rows.append(CandidateFacts(
            label=candidate.label,
            outOfKeyRatio=round(outside / len(filled), 3) if filled else None,
            changedSlots=changed, repetitionVsPrevious=repetition, r1Roughness=_mean_roughness(filled),
            rulesSlots=list(rules),
        ))
    return rows


# --- The judge call ---


def review_schema(labels: list[str], fact_names: list[str]) -> dict[str, Any]:
    """The strict reply schema: the choice among `labels`, one or two reasons citing `fact_names`."""
    return {
        "type": "object",
        "properties": {
            "choice": {"type": "string", "enum": list(labels)},
            "reasons": {
                "type": "array", "minItems": 1, "maxItems": MAX_REASONS,
                "items": {"type": "object", "properties": {
                    "factName": {"type": "string", "enum": list(fact_names)},
                    "value": {"type": "number"},
                    "claim": {"type": "string", "maxLength": MAX_CLAIM_CHARS},
                }},
            },
        },
    }


def _messages(request: ReviewRequest, facts: list[CandidateFacts]) -> list[dict[str, str]]:
    payload = {
        "key": request.key, "genre": request.genre, "sectionType": request.sectionType,
        "original": request.original, "previousSection": request.previousSection,
        "candidates": [{"label": candidate.label, "chords": candidate.chords,
                        "facts": row.model_dump(exclude={"label"})}
                       for candidate, row in zip(request.candidates, facts)],
    }
    return [{"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]


def _client() -> LLMClient:
    """The judge role's shared client, or the failure that stands for its missing configuration."""
    try:
        client = get_client("judge")
    except LLMError as exc:
        raise ReviewFailure(_kind(exc), _message(exc)) from None
    if not client.config.api_key:
        raise ReviewFailure("config", f"{client.config.key_source} is not set, so provider "
                                      f"{client.config.provider} cannot be called")
    return client


def _call(client: LLMClient, messages: list[dict[str, str]], schema: dict[str, Any]) -> tuple[LLMResult, float, int]:
    """One ledgered judge call: (result, settled cost of every attempt, wall-clock ms), or a ReviewFailure."""
    cfg = client.config
    # A provider configured without a reasoning mode (ollama, custom) gets no effort field
    effort = REVIEW_EFFORT if cfg.reasoning_effort is not None else None
    options = dict(name=REVIEW_SCHEMA_NAME, max_completion_tokens=REVIEW_MAX_TOKENS, timeout_s=REVIEW_TIMEOUT_S,
                   max_request_usd=REVIEW_MAX_USD, reasoning_effort=effort)
    try:
        prepared = client.prepare(messages, schema, **options)
        spent_before = client.ledger.snapshot()["spent_usd"]
    except LLMError as exc:
        raise ReviewFailure(_kind(exc), _message(exc), exc.request_id, provider=cfg.provider,
                            model=cfg.model) from None
    # The limiter admitted REVIEW_MAX_USD; an open-weight provider may reserve twice (its one JSON-guard retry)
    worst_case = prepared.reserve_usd * (1 if cfg.provider == "meta" else 2)
    if worst_case > REVIEW_MAX_USD + 1e-9:
        raise ReviewFailure("budget", f"the review's worst case ${worst_case:.4f} would pass its "
                                      f"${REVIEW_MAX_USD:.2f} cap", provider=cfg.provider, model=cfg.model)
    started = time.perf_counter()
    try:
        result = client.chat_json(messages, schema, label=REVIEW_LABEL, **options)
    except LLMError as exc:
        # What the ledger moved: nothing for a refusal before the send, the settled first attempt when
        # the ledger refused an open-weight retry, the whole reservation after a timeout
        cost = max(0.0, _spent(client) - spent_before)
        raise ReviewFailure(_kind(exc), _message(exc), exc.request_id, provider=cfg.provider, model=cfg.model,
                            cost_usd=round(cost, 8), latency_ms=_elapsed_ms(started)) from None
    latency = _elapsed_ms(started)
    cost = result.cost_usd
    if result.attempts > 1:  # the result carries only the last attempt's cost; the ledger has both
        cost = max(cost, _spent(client) - spent_before)
    return result, round(cost, 8), latency


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _matches(name: str, value: float, actual: float) -> bool:
    if name in _COUNT_FACTS:
        return value == actual
    return abs(value - actual) <= max(_TOLERANCE, _RELATIVE_TOLERANCE * abs(actual))


def verify_reason(reason: dict[str, Any], row: CandidateFacts) -> ReviewReason:
    """A judge reason checked against the chosen candidate's row: confirmed when its fact has that
    value there (within the tolerance), else it stays the model's statement."""
    name, raw = reason["factName"], reason["value"]
    value = float(raw) if isinstance(raw, (int, float)) and math.isfinite(raw) else None
    actual = getattr(row, name)
    confirmed = value is not None and actual is not None and _matches(name, value, actual)
    return ReviewReason(fact=f"{name}={raw:g}" if value is not None else f"{name}={raw}", factName=name, value=value,
                        claim=str(reason["claim"]).strip()[:MAX_CLAIM_CHARS], confirmed=confirmed,
                        analyzerValue=actual)


def review_candidates(request: ReviewRequest, client: LLMClient | None = None) -> ReviewResponse:
    """The facts, one judge call and the verified reasons; raises ReviewFailure on any LLM failure.
    An explicit client (evaluation scripts) is used as given instead of the judge role's shared one."""
    client = client if client is not None else _client()
    facts = candidate_facts(request)
    citable = [name for name in FACT_NAMES if any(getattr(row, name) is not None for row in facts)]
    schema = review_schema([row.label for row in facts], citable)
    result, cost, latency = _call(client, _messages(request, facts), schema)
    choice = result.data["choice"]
    row = next(row for row in facts if row.label == choice)
    return ReviewResponse(
        choice=choice, reasons=[verify_reason(reason, row) for reason in result.data["reasons"]], facts=facts,
        provider=result.provider, model=result.model, requestId=result.request_id, costUsd=cost, latencyMs=latency,
    )
