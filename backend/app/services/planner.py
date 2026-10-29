"""Complete the form: plan the rest of a song form from the user's sketch, then write it.

One run is a deterministic controller around at most five LLM calls:

    plan_song          Muse Spark plans the sections after the locked sketch (strict JSON)
    validate_plan      code checks the plan; its issues go back as a user message, twice at most
    generate_section   the author's chord model writes every planned section in order, each
                       with the previous ones as context and the planned cadence (compose_section)
    judge              one observe-then-act turn: the judge role reads analyzer facts about the
                       model's own chords (rule-written slots excluded) and may send at most two
                       sections back for one regeneration each; at most two judgments

planner "rules" is the genre-default form through the same validator and generation,
with no LLM call: the "before" baseline and the fallback button. Every LLM call goes
through app.services.llm with a per-call cap, and the run stops with a typed failure
when its call count, reservation total or time budgets would be passed. The trace
reports everything that happened, failures included; nothing is applied server-side.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.models.plan import (
    MAX_CITES,
    MAX_PLAN_SECTION_BARS,
    MAX_PLAN_SECTIONS,
    MAX_REASON_CHARS,
    MIN_PLAN_SECTION_BARS,
    JudgeDecision,
    JudgeTarget,
    PlanCall,
    PlanError,
    PlanIssue,
    PlanRequest,
    PlanSectionResult,
    PlanTrace,
    PlannedSection,
    SectionReport,
    SketchMeasure,
    SongPlan,
    ValidationAttempt,
)
from app.models.schemas import CADENCE_TYPES, ContextMeasure, SectionGenerateRequest
from app.models.sections import CHORDS_PER_BAR, SECTION_INFO, SECTION_TYPES
from app.routes.generate import compose_section
from app.services.key_anchor import _chord_pcs
from app.services.llm import (
    BudgetExceeded,
    LedgerError,
    LLMClient,
    LLMCancelled,
    LLMConfigError,
    LLMConnectionError,
    LLMDisabled,
    LLMError,
    LLMResponseError,
    LLMResult,
    LLMSchemaError,
    LLMTimeout,
    get_client,
)
from app.services.song_form import SECTION_RULES, rule_slots
from app.services.voice_leading import _NOTE_PC

log = logging.getLogger(__name__)

# --- Limits per run (initial values; U3's eval and U4's host measurements adjust them) ---
MAX_META_CALLS = 5            # 1 plan + up to 2 revisions + up to 2 judgments
MAX_REVISIONS = 2
MAX_JUDGMENTS = 2
MAX_TARGETS = 2               # sections one judgment may send back
CALL_TIMEOUT_S = 45.0
MAX_REQUEST_USD = 0.05        # worst-case reservation of one call
MAX_RUN_USD = 0.10            # the run's settled spend plus the next call's worst case never passes it
RUN_BUDGET_S = 120.0
META_BUDGET_S = 75.0          # wall clock inside LLM calls
OWN_MODEL_BUDGET_S = 45.0     # wall clock inside the chord model
MIN_CALL_S = 2.0              # below this much Meta time left, a call is not even started
PLAN_EFFORT = "medium"
REVISE_EFFORT = "low"
JUDGE_EFFORT = "low"
# Reasoning tokens count toward these. Real runs (10/29) hit 1024 in judgments and 4096 in 64-bar plans
PLAN_MAX_TOKENS = 8192
JUDGE_MAX_TOKENS = 4096
OUTRO_BARS = 4                # the rules planner's outro

# Event callback of the streaming route: (event name, payload)
OnEvent = Callable[[str, dict], None]

# --- Section and cadence vocabulary as the prompt states it (what the rules will do) ---
SECTION_GLOSSARY = {
    "intro": "opening; the rules start it on I; allowed only as the first section of an empty song",
    "verse": "narrative section; ends V-I unless another cadence is chosen",
    "pre_chorus": "build-up; hangs on V",
    "chorus": "the hook; ends V-I",
    "post_chorus": "static loop of its first two bars",
    "bridge": "contrast; starts on IV and ends IV-V",
    "outro": "ending; IV-I; allowed only as the last section",
    "interlude": "instrumental breather; the model's own phrase",
    "solo": "instrumental feature; the model's own phrase",
    "breakdown": "one-bar vamp loop (electronic)",
    "drop": "two-bar loop (electronic)",
    "vamp": "one-bar loop (funk, gospel)",
    "turnaround": "I vi ii V back to the top",
    "tag": "closing repeat; V-I",
    "head": "jazz theme; ends V-I",
    "a_section": "jazz A section; ends V-I",
    "b_section": "jazz B section / bridge; starts on IV, ends IV-V",
}
assert set(SECTION_GLOSSARY) == set(SECTION_TYPES), "SECTION_GLOSSARY and SECTION_TYPES drifted"
CADENCE_GLOSSARY = {
    "authentic": "V-I", "plagal": "IV-I", "half": "ends on V", "half_iv_v": "IV-V",
    "turnaround": "I vi ii V", "none": "the model's own ending",
}
LOOP_SECTIONS = frozenset(section for section, rules in SECTION_RULES.items() if rules.get("loop"))
# Genres whose harmony usually stays in key; the judge tolerates chromatic chords elsewhere
DIATONIC_GENRES = ("pop", "country", "folk", "gospel", "classical", "rock", "electronic", "hip_hop")

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array", "minItems": 1, "maxItems": MAX_PLAN_SECTIONS,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(SECTION_TYPES)},
                    # No bounds here: an out-of-range length is a validator issue the model gets to revise,
                    # not a schema mismatch that ends the run
                    "bars": {"type": "integer"},
                    "cadence": {"type": "string", "enum": list(CADENCE_TYPES)},
                    "reason": {"type": "string", "maxLength": MAX_REASON_CHARS},
                    "cites": {
                        "type": "array", "maxItems": MAX_CITES,
                        "items": {"type": "object", "properties": {
                            "bar": {"type": "integer", "minimum": 0},
                            "roman": {"type": "string", "maxLength": 32},
                        }},
                    },
                },
            },
        },
    },
}
JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "regenerate"]},
        "targets": {
            "type": "array", "maxItems": MAX_TARGETS,
            "items": {"type": "object", "properties": {
                "section": {"type": "integer", "minimum": 0},
                "reason": {"type": "string", "maxLength": MAX_REASON_CHARS},
            }},
        },
    },
}

PLAN_SYSTEM_PROMPT = f"""You plan the song form of a chord chart in a chord editor with {CHORDS_PER_BAR} chord slots per bar.
The user's sketch (bars already written, each with the Roman numerals the editor computed) and its
existing sections are locked and come first. You plan only the sections that follow the sketch; a
separate chord model then writes their chords in your order, section by section, and song-form rules
write each section's first chord and ending as the type and cadence say. Reply with one JSON object
{{"sections": [{{"type", "bars", "cadence", "reason", "cites"}}]}} and nothing else.

Section types: {"; ".join(f"{name}: {meaning}" for name, meaning in SECTION_GLOSSARY.items())}.
Cadences: {"; ".join(f"{name}: {meaning}" for name, meaning in CADENCE_GLOSSARY.items())}.

A validator checks every plan and returns its issues for one more try, so follow these rules:
- bars: {MIN_PLAN_SECTION_BARS} to {MAX_PLAN_SECTION_BARS} per section; the sketch's bars plus your sections' bars must total exactly targetBars.
- intro: only as the first section, and only when the sketch is empty. outro: only as the last
  section; the last section must be an outro when wantOutro is true and must not be one otherwise.
- The last section's cadence must be authentic or plagal (the song has to land).
- reason: at most {MAX_REASON_CHARS} characters, naming what in the sketch you build on or contrast with.
- cites: the sketch bars whose Roman numerals your reason relies on, as {{"bar", "roman"}} copied
  exactly from the sketch (at most {MAX_CITES}); an empty list when the sketch is empty.
- contrast low: few distinct section types, lengths like the sketch's phrases; medium: the genre's
  usual form; high: more distinct types (pre_chorus, bridge, breakdown, solo) and cadences that
  differ from the sketch's. Keep the genre's conventions (jazz: AABA sections; blues: 12-bar
  verses; electronic: breakdown and drop; funk and gospel: vamps; folk: strophic verses)."""

JUDGE_SYSTEM_PROMPT = f"""You are the second ear after the chords of a planned song form were generated.
The analyzer report lists, per section, facts about the chords the chord model chose itself
(slots the song-form rules wrote are excluded): the share of chords with a tone outside the song's
key, how much the section repeats the material right before it (same slot, same chord), the number
of distinct chords and empty slots. Decide from these facts only: "accept", or "regenerate" with at
most {MAX_TARGETS} target sections and a short reason each. Send a section back when its facts show a
problem: many chords outside the key in a genre that stays in key ({", ".join(DIATONIC_GENRES)}),
a section that repeats the previous one although the requested contrast is medium or high, a
non-loop section with fewer than 2 distinct chords, or empty slots. Loop sections
({", ".join(sorted(LOOP_SECTIONS))}) repeat by design; jazz, bossa, blues, funk and R&B tolerate
chromatic chords. Accept when nothing stands out: a regeneration costs time and is not guaranteed to
improve. Reply with one JSON object {{"decision", "targets": [{{"section", "reason"}}]}} and nothing else."""

_ROMAN = re.compile(r"([#b]*)([ivIV]+)")
_TRAILING_ONE = 1  # a leftover of one bar is folded into the section before it


class PlanFailure(Exception):
    """A run stopped: kind and message become the trace's error (see PlanError.kind)."""

    def __init__(self, kind: str, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.request_id = request_id


# --- Sketch facts for the prompt ---


def _degree(roman: str | None) -> str | None:
    """The scale degree of an editor Roman numeral with its accidental, upper-cased: 'vi7' -> 'VI', 'bVII' -> 'bVII'."""
    match = _ROMAN.match(roman.strip()) if roman else None
    return (match[1] + match[2].upper()) if match else None


def sketch_facts(measures: list[SketchMeasure]) -> dict[str, Any]:
    """Cadences and repeated passages read off the sketch's Roman numerals.

    authentic / plagal: a V or IV followed by I, at the bar of the I. half: a bar whose last
    chord is V and is not followed by I. repeats: a 4-bar (else 2-bar) run of Roman numerals
    equal to an earlier aligned run.
    """
    slots = [(m.index, roman) for m in measures for roman in m.roman if roman]
    cadences: list[dict[str, Any]] = []
    for (_, before), (bar, after) in zip(slots, slots[1:]):
        if _degree(after) == "I" and _degree(before) in ("V", "IV"):
            cadences.append({"bar": bar, "type": "authentic" if _degree(before) == "V" else "plagal"})
    for position, measure in enumerate(measures):
        last = next((roman for roman in reversed(measure.roman) if roman), None)
        following = next((roman for later in measures[position + 1:] for roman in later.roman if roman), None)
        if _degree(last) == "V" and _degree(following) != "I":
            cadences.append({"bar": measure.index, "type": "half"})
    cadences.sort(key=lambda cadence: cadence["bar"])

    bars = [tuple(_degree(roman) for roman in m.roman) for m in measures]
    repeats: list[dict[str, Any]] = []
    covered: set[int] = set()
    for width in (4, 2):
        for start in range(width, len(bars) - width + 1):
            if start in covered or any(degree is None for bar in bars[start:start + width] for degree in bar):
                continue
            earlier = next((t for t in range(start % width, start, width)
                            if bars[t:t + width] == bars[start:start + width]), None)
            if earlier is not None:
                repeats.append({"bars": [start, start + width - 1], "sameAs": [earlier, earlier + width - 1]})
                covered.update(range(start, start + width))
    repeats.sort(key=lambda repeat: repeat["bars"][0])
    return {"cadences": cadences, "repeats": repeats}


def _plan_messages(request: PlanRequest) -> list[dict[str, str]]:
    sketch = {
        "bars": len(request.measures),
        "measures": [{"bar": m.index, "chords": m.chords, "roman": m.roman} for m in request.measures],
        "sections": [{"type": s.type, "start": s.start, "length": s.length, "label": s.label}
                     for s in request.sections],
        **sketch_facts(request.measures),
    }
    payload = {
        "key": request.key, "timeSignature": list(request.timeSignature or (4, 4)), "genre": request.genre,
        "bpm": request.bpm, "targetBars": request.targetBars, "wantOutro": request.wantOutro,
        "contrast": request.contrast, "sketch": sketch,
        "plan": {"barsToPlan": request.targetBars - len(request.measures),
                 "firstBar": len(request.measures), "maxSections": MAX_PLAN_SECTIONS},
    }
    return [{"role": "system", "content": PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]


def _revision_message(issues: list[PlanIssue]) -> dict[str, str]:
    """The validator's issues, as the user message that asks for a corrected plan."""
    listed = [{"code": issue.code, "section": issue.section, "message": issue.message} for issue in issues]
    return {"role": "user", "content": "The validator rejected that plan: "
            f"{json.dumps(listed, ensure_ascii=False, separators=(',', ':'))}. Reply with the whole corrected "
            "plan as one JSON object matching the schema; keep what was not rejected."}


# --- validate_plan ---


def validate_plan(plan: SongPlan, request: PlanRequest) -> list[PlanIssue]:
    """The planner's rules, as machine-readable issues (empty when the plan is valid).

    The plan holds only the sections after the sketch, so the request's existing
    sections cannot be changed by it; the rules below judge the combined form.
    """
    issues: list[PlanIssue] = []

    def issue(code: str, message: str, section: int | None = None) -> None:
        issues.append(PlanIssue(code=code, section=section, message=message))

    sections = plan.sections
    if not sections:
        issue("empty", "the plan has no sections")
        return issues
    sketch_bars = len(request.measures)
    for index, section in enumerate(sections):
        if section.type not in SECTION_INFO:
            issue("section_type", f"unknown section type {section.type!r}; use one of {', '.join(SECTION_TYPES)}", index)
        if not MIN_PLAN_SECTION_BARS <= section.bars <= MAX_PLAN_SECTION_BARS:
            issue("bars", f"{section.bars} bars; a section has {MIN_PLAN_SECTION_BARS} to {MAX_PLAN_SECTION_BARS}", index)
        if section.cadence not in CADENCE_TYPES:
            issue("cadence", f"unknown cadence {section.cadence!r}; use one of {', '.join(CADENCE_TYPES)}", index)
        if len(section.reason) > MAX_REASON_CHARS:
            issue("reason_length", f"reason has {len(section.reason)} characters; at most {MAX_REASON_CHARS}", index)
        if section.type == "intro" and (index > 0 or sketch_bars > 0):
            issue("intro_first", "an intro may only be the first section of an empty song", index)
        if section.type == "outro" and index < len(sections) - 1:
            issue("outro_last", "an outro may only be the last section", index)
        if section.type == "outro" and not request.wantOutro:
            issue("outro_unwanted", "wantOutro is false: no outro", index)
        for cite in section.cites:
            if not 0 <= cite.bar < sketch_bars:
                issue("cite_bar", f"cites bar {cite.bar}, which is not in the {sketch_bars}-bar sketch", index)
            elif cite.roman.strip() not in [roman for roman in request.measures[cite.bar].roman if roman]:
                issue("cite_roman", f"cites {cite.roman!r} at bar {cite.bar}, whose Roman numerals are "
                                    f"{[roman for roman in request.measures[cite.bar].roman]}", index)
    planned = sum(section.bars for section in sections)
    if sketch_bars + planned != request.targetBars:
        issue("total_bars", f"the sketch's {sketch_bars} bars plus the planned {planned} bars make "
                            f"{sketch_bars + planned}, not targetBars {request.targetBars}")
    last = sections[-1]
    if last.cadence in CADENCE_TYPES and last.cadence not in ("authentic", "plagal"):
        issue("final_cadence", f"the last section ends with {last.cadence}; the song must land on "
                               "authentic or plagal", len(sections) - 1)
    if request.wantOutro and last.type != "outro":
        issue("outro_wanted", "wantOutro is true: the last section must be an outro", len(sections) - 1)
    return issues


# --- The rules planner: genre-default forms ---

# (type, bars) in order; trimmed or extended to the bars left after the sketch
_POP_FORM = [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 8), ("bridge", 8), ("chorus", 8)]
_AABA_FORM = [("a_section", 8), ("a_section", 8), ("b_section", 8), ("a_section", 8)]
RULES_FORMS: dict[str, list[tuple[str, int]]] = {
    "pop": _POP_FORM, "rock": _POP_FORM, "country": _POP_FORM,
    "rnb_soul": [("intro", 4), ("verse", 8), ("pre_chorus", 4), ("chorus", 8), ("verse", 8), ("pre_chorus", 4),
                 ("chorus", 8), ("bridge", 8), ("chorus", 8)],
    "jazz": _AABA_FORM, "bossa": _AABA_FORM,
    "blues": [("intro", 4), ("verse", 12), ("verse", 12), ("verse", 12)],  # 12-bar choruses
    "hip_hop": [("intro", 4), ("verse", 16), ("chorus", 8), ("verse", 16), ("chorus", 8)],
    "electronic": [("intro", 8), ("breakdown", 8), ("drop", 16), ("breakdown", 8), ("drop", 16)],
    "funk": [("intro", 4), ("vamp", 8), ("verse", 8), ("vamp", 8), ("chorus", 8), ("vamp", 8)],
    "gospel": [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 8), ("vamp", 8), ("tag", 4)],
    "folk": [("intro", 4), ("verse", 8), ("verse", 8), ("verse", 8), ("verse", 8)],
    "classical": _AABA_FORM,  # 8-bar periods
}


def _fit_form(form: list[tuple[str, int]], room: int) -> list[tuple[str, int]]:
    """The form's sections in order until `room` bars are filled: a section that does not
    fit is shortened, and after the form's end its body (no intro) repeats. A leftover of
    one bar goes to the section before it, so every section keeps at least 2 bars."""
    body = [section for section in form if section[0] != "intro"] or form
    out: list[tuple[str, int]] = []
    filled = 0
    position = 0
    while filled < room:
        kind, bars = form[position] if position < len(form) else body[(position - len(form)) % len(body)]
        position += 1
        left = room - filled
        bars = min(bars, left)
        if left - bars == _TRAILING_ONE:
            bars = left
        out.append((kind, bars))
        filled += bars
    return out


def _default_cadence(section: str) -> str:
    return SECTION_RULES.get(section, {}).get("cadence") or "none"


def rules_plan(request: PlanRequest) -> SongPlan:
    """The genre-default form for the bars after the sketch; no model is involved."""
    room = request.targetBars - len(request.measures)
    form = list(RULES_FORMS.get(request.genre, _POP_FORM))
    if request.measures:
        form = [section for section in form if section[0] != "intro"]  # the sketch already opened the song
    outro = min(OUTRO_BARS, room) if request.wantOutro else 0
    if 0 < room - outro < MIN_PLAN_SECTION_BARS:
        outro = room
    sections = _fit_form(form, room - outro)
    if outro:
        sections.append(("outro", outro))
    planned: list[PlannedSection] = []
    for index, (kind, bars) in enumerate(sections):
        last = index == len(sections) - 1
        cadence = ("plagal" if kind == "outro" else "authentic") if last else _default_cadence(kind)
        planned.append(PlannedSection(type=kind, bars=bars, cadence=cadence,
                                      reason=f"{request.genre} default form (rules)", cites=[]))
    return SongPlan(sections=planned)


# --- Analyzer: facts about the model's own chords ---


def _key_collection(key: str) -> frozenset[int]:
    """Pitch classes of the key's collection: the major scale, or natural plus harmonic and
    melodic minor (so a minor key's own V7 and its raised sixth are not 'outside the key')."""
    root, mode = key.split()
    steps = (0, 2, 3, 5, 7, 8, 9, 10, 11) if mode == "minor" else (0, 2, 4, 5, 7, 9, 11)
    tonic = _NOTE_PC[root]
    return frozenset((tonic + step) % 12 for step in steps)


def _symbol(chord: str | None) -> str | None:
    """A chord without its slash bass (voice leading adds those), or None for an empty slot."""
    if not chord:
        return None
    return chord.split("/")[0].strip() or None


def _in_key(symbol: str, collection: frozenset[int]) -> bool:
    """Whether every tone of the chord sits in the key; a symbol the parser cannot read does not."""
    tones = _chord_pcs(symbol)
    return tones is not None and tones <= collection


def _flat_chords(section: PlanSectionResult) -> list[str | None]:
    """The section's applied chords (suggestion A) in slot order."""
    chords = section.suggestions[0].chords if section.suggestions else {}
    return [chord for measure in sorted(chords, key=int) for chord in chords[measure]]


def section_report(index: int, section: PlanSectionResult, before: list[str | None], key: str) -> SectionReport:
    """Facts over the slots the model decided (rulesSlots excluded). `before` is the material
    right before the section (the previous section, else the sketch's tail) for the repeat rate."""
    chords = _flat_chords(section)
    collection = _key_collection(key)
    model_slots = [i for i in range(len(chords)) if i not in set(section.rulesSlots)]
    symbols = [_symbol(chords[i]) for i in model_slots]
    filled = [symbol for symbol in symbols if symbol]
    outside = sum(1 for symbol in filled if not _in_key(symbol, collection))
    comparable = [i for i in model_slots if i < len(before)]
    repeats = sum(1 for i in comparable if _symbol(chords[i]) is not None and _symbol(chords[i]) == _symbol(before[i]))
    return SectionReport(
        section=index, type=section.sectionType, bars=section.bars, modelSlots=len(model_slots),
        outsideKey=round(outside / len(filled), 3) if filled else 0.0,
        repeatRate=round(repeats / len(comparable), 3) if comparable else None,
        distinctChords=len(set(filled)), emptySlots=len(symbols) - len(filled),
    )


# --- The run ---


@dataclass
class _Run:
    request: PlanRequest
    on_event: OnEvent | None = None
    cancelled: Callable[[], bool] | None = None
    started: float = field(default_factory=time.perf_counter)
    client: LLMClient | None = None
    judge_client: LLMClient | None = None
    plan: SongPlan | None = None
    validation: list[ValidationAttempt] = field(default_factory=list)
    sections: list[PlanSectionResult] = field(default_factory=list)
    judge: list[JudgeDecision] = field(default_factory=list)
    calls: list[PlanCall] = field(default_factory=list)
    spend_usd: float = 0.0
    reserved_usd: float = 0.0
    meta_ms: int = 0
    generation_ms: int = 0
    error: PlanError | None = None

    def elapsed_ms(self) -> int:
        return round((time.perf_counter() - self.started) * 1000)

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        if self.on_event is not None:
            self.on_event(event, {**payload, "t_ms": self.elapsed_ms()})

    def check_clock(self) -> None:
        self.check_cancelled()
        if self.elapsed_ms() >= RUN_BUDGET_S * 1000:
            raise PlanFailure("timeout", f"the run passed its {RUN_BUDGET_S:g} s budget")

    def check_cancelled(self) -> None:
        if self.cancelled is not None and self.cancelled():
            raise PlanFailure("generation", "The song-form run was cancelled")

    def call(self, client: LLMClient, step: str, attempt: int, messages: list[dict[str, str]],
             schema: dict[str, Any], *, name: str, effort: str, max_tokens: int) -> LLMResult:
        """One ledgered LLM call within the run's limits; a failure is recorded, then raised."""
        if len(self.calls) >= MAX_META_CALLS:
            raise PlanFailure("budget", f"the run's limit of {MAX_META_CALLS} LLM calls is used up")
        self.check_clock()
        timeout = min(CALL_TIMEOUT_S, META_BUDGET_S - self.meta_ms / 1000)
        if timeout < MIN_CALL_S:
            raise PlanFailure("timeout", f"the run's {META_BUDGET_S:g} s of LLM time is used up")
        # A provider configured without a reasoning mode (ollama, custom) gets no effort field
        sent_effort = effort if client.config.reasoning_effort is not None else None
        options = dict(name=name, max_completion_tokens=max_tokens, timeout_s=timeout,
                       max_request_usd=MAX_REQUEST_USD, reasoning_effort=sent_effort)
        try:
            prepared = client.prepare(messages, schema, **options)
            spent_before = client.ledger.snapshot()["spent_usd"]
        except LLMError as exc:
            raise PlanFailure(_kind(exc), _message(exc), exc.request_id) from None
        # What the run has settled plus this call's worst case (an open-weight provider may reserve twice,
        # for its one JSON-guard retry); each call settles at or below its reservation, so the run's
        # spend never passes the cap, while unspent reservations no longer crowd out later calls
        worst_case = prepared.reserve_usd * (1 if client.config.provider == "meta" else 2)
        if self.spend_usd + worst_case > MAX_RUN_USD + 1e-9:
            raise PlanFailure("budget", f"reserving ${worst_case:.4f} for {step} could take the run past its "
                                        f"${MAX_RUN_USD:.2f} cap (${self.spend_usd:.4f} spent so far)")
        started = time.perf_counter()
        try:
            result = client.chat_json(messages, schema, label=f"plan.{step}", cancelled=self.cancelled, **options)
        except LLMError as exc:
            cost = max(0.0, _spent(client) - spent_before)
            if cost > 0 or not isinstance(exc, (BudgetExceeded, LLMConfigError, LedgerError, LLMSchemaError, LLMCancelled)):
                # A retry may be refused after its first attempt already settled.
                # Keep that spend too, as well as a timeout's full reservation.
                latency = round((time.perf_counter() - started) * 1000)
                self.meta_ms += latency
                self.reserved_usd += prepared.reserve_usd
                self._record(step, attempt, client, exc.request_id, cost, latency, sent_effort, ok=False)
            raise PlanFailure(_kind(exc), _message(exc), exc.request_id) from None
        latency = round((time.perf_counter() - started) * 1000)
        self.meta_ms += latency
        self.reserved_usd += prepared.reserve_usd * result.attempts
        # The result prices only the last attempt; the ledger contains the rejected first reply too.
        cost = result.cost_usd if result.attempts == 1 else max(result.cost_usd, _spent(client) - spent_before)
        self._record(step, attempt, client, result.request_id, cost, latency, sent_effort)
        self.check_cancelled()
        return result

    def _record(self, step: str, attempt: int, client: LLMClient, request_id: str | None, cost: float,
                latency_ms: int, effort: str | None, ok: bool = True) -> PlanCall:
        call = PlanCall(step=step, attempt=attempt, provider=client.config.provider, model=client.config.model,
                        requestId=request_id, costUsd=round(cost, 8), latencyMs=latency_ms, effort=effort, ok=ok)
        self.calls.append(call)
        self.spend_usd = round(self.spend_usd + cost, 8)
        return call

    def trace(self) -> PlanTrace:
        request = self.request
        return PlanTrace(
            status="error" if self.error else "ok", planner=request.planner, genre=request.genre,
            key=request.key or "", bpm=request.bpm or 0, timeSignature=request.timeSignature or (4, 4),
            plan=self.plan, validation=self.validation, sections=self.sections, judge=self.judge,
            calls=self.calls, spendUsd=self.spend_usd, reservedUsd=round(self.reserved_usd, 8),
            elapsedMs=self.elapsed_ms(), metaMs=self.meta_ms, generationMs=self.generation_ms, error=self.error,
        )


def _spent(client: LLMClient) -> float:
    try:
        return client.ledger.snapshot()["spent_usd"]
    except LLMError:
        return 0.0


def _kind(exc: LLMError) -> str:
    if isinstance(exc, LLMCancelled):
        return "generation"
    if isinstance(exc, LLMDisabled):
        return "disabled"
    if isinstance(exc, (LLMConfigError, LedgerError)):
        return "config"
    if isinstance(exc, BudgetExceeded):
        return "budget"
    if isinstance(exc, LLMTimeout):
        return "timeout"
    return "llm"


def _message(exc: LLMError) -> str:
    """The failure's text for the trace: never a ledger path, and the request id kept apart."""
    if isinstance(exc, BudgetExceeded):
        return (f"Meta budget: spent ${exc.spent_usd:.4f} + outstanding ${exc.outstanding_usd:.4f} + this "
                f"request ${exc.request_usd:.4f} would pass the cap ${exc.cap_usd:.2f}")
    if isinstance(exc, LedgerError):
        return "the spend ledger cannot be read or written; check THEARTIST_META_LEDGER"
    return str(exc.args[0]) if exc.args else type(exc).__name__


def _client(role: str) -> LLMClient:
    """The role's shared client, or the failure that stands for its missing configuration."""
    try:
        client = get_client(role)
    except LLMError as exc:
        raise PlanFailure(_kind(exc), _message(exc)) from None
    if not client.config.api_key:
        raise PlanFailure("config", f"{client.config.key_source} is not set, so provider "
                                    f"{client.config.provider} cannot be called")
    return client


# --- Steps ---


def _plan(run: _Run) -> None:
    """plan_song: the plan, validated, revised at most MAX_REVISIONS times."""
    run.check_clock()
    request = run.request
    if request.planner == "rules":
        plan = rules_plan(request)
        issues = validate_plan(plan, request)
        run.plan = plan
        run.validation.append(ValidationAttempt(attempt=1, ok=not issues, errors=issues))
        run.emit("plan", {"attempt": 1, "source": "rules", "plan": plan.model_dump()})
        run.emit("validate", {"attempt": 1, "ok": not issues, "errors": [i.model_dump() for i in issues]})
        if issues:  # the forms are built to pass; a failure here is a bug worth seeing
            raise PlanFailure("invalid", "the genre-default form failed validation: " + "; ".join(i.message for i in issues))
        return

    assert run.client is not None
    messages = _plan_messages(request)
    for attempt in range(1, MAX_REVISIONS + 2):
        result = run.call(run.client, "plan_song", attempt, messages, PLAN_SCHEMA, name="song_plan",
                          effort=PLAN_EFFORT if attempt == 1 else REVISE_EFFORT, max_tokens=PLAN_MAX_TOKENS)
        try:
            plan = SongPlan.model_validate(result.data)
        except ValueError as exc:
            raise PlanFailure("llm", f"the plan reply does not fit the plan model: {exc}", result.request_id) from None
        run.plan = plan
        run.emit("plan" if attempt == 1 else "revise",
                 {"attempt": attempt, "source": "meta", "plan": plan.model_dump(), "call": run.calls[-1].model_dump()})
        issues = validate_plan(plan, request)
        run.validation.append(ValidationAttempt(attempt=attempt, ok=not issues, errors=issues))
        run.emit("validate", {"attempt": attempt, "ok": not issues, "errors": [i.model_dump() for i in issues]})
        if not issues:
            return
        messages = [*messages, {"role": "assistant", "content": result.text}, _revision_message(issues)]
    raise PlanFailure("invalid", f"the plan still failed validation after {MAX_REVISIONS} revisions",
                      run.calls[-1].requestId)


def _context(run: _Run, upto: int) -> list[ContextMeasure]:
    """The sketch plus the applied chords (suggestion A) of the sections before `upto`."""
    context = [ContextMeasure(measure=m.index, chords=list(m.chords)) for m in run.request.measures]
    for section in run.sections[:upto]:
        chords = section.suggestions[0].chords if section.suggestions else {}
        context += [ContextMeasure(measure=int(measure), chords=list(chords[measure]))
                    for measure in sorted(chords, key=int)]
    return context


def _generate_section(run: _Run, index: int, regenerated: bool = False) -> PlanSectionResult:
    """generate_section: the planned section after everything before it, with its cadence."""
    assert run.plan is not None
    planned = run.plan.sections[index]
    request = run.request
    run.check_clock()
    if run.generation_ms >= OWN_MODEL_BUDGET_S * 1000:
        raise PlanFailure("timeout", f"the run's {OWN_MODEL_BUDGET_S:g} s of chord-model time is used up")
    section_request = SectionGenerateRequest(
        key=request.key or "", bpm=request.bpm or 80, genre=request.genre,
        timeSignature=request.timeSignature or (4, 4), sectionType=planned.type,
        chordCount=planned.bars * CHORDS_PER_BAR, context=_context(run, index), modelKey=request.modelKey,
        cadence=planned.cadence,
        seed=None if request.seed is None else (request.seed + index * 1009 + int(regenerated) * 1000003) & 0xFFFFFFFF,
    )
    started = time.perf_counter()
    try:
        response = compose_section(section_request)
    except HTTPException as exc:
        raise PlanFailure("generation", str(exc.detail)) from None
    except Exception:
        log.exception("Section generation failed for planned section %d (%s)", index, planned.type)
        raise PlanFailure("generation", "Chord generation failed") from None
    finally:
        run.generation_ms += round((time.perf_counter() - started) * 1000)
    run.check_cancelled()
    return PlanSectionResult(
        **response.model_dump(), cadence=planned.cadence,
        rulesSlots=rule_slots(planned.type, response.chordCount, planned.cadence),
        reason=planned.reason, cites=planned.cites, regenerated=regenerated,
    )


def _generate_all(run: _Run) -> None:
    assert run.plan is not None
    for index in range(len(run.plan.sections)):
        section = _generate_section(run, index)
        run.sections.append(section)
        run.emit("generate_section", {"index": index, **section.model_dump()})


def _reports(run: _Run) -> list[SectionReport]:
    """One report per section; the first section is compared with the sketch's tail."""
    reports = []
    sketch: list[str | None] = [chord for m in run.request.measures for chord in m.chords]
    for index, section in enumerate(run.sections):
        if index > 0:
            before = _flat_chords(run.sections[index - 1])
        else:
            before = sketch[max(0, len(sketch) - len(_flat_chords(section))):]
        reports.append(section_report(index, section, before, run.request.key or ""))
    return reports


def _judge(run: _Run, attempt: int) -> JudgeDecision:
    """judge: one observe-then-act turn over the analyzer's report."""
    assert run.judge_client is not None and run.plan is not None
    report = _reports(run)
    payload = {
        "genre": run.request.genre, "key": run.request.key, "contrast": run.request.contrast,
        "plan": [{"section": i, "type": s.type, "bars": s.bars, "cadence": s.cadence}
                 for i, s in enumerate(run.plan.sections)],
        "report": [r.model_dump() for r in report],
    }
    messages = [{"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]
    result = run.call(run.judge_client, "judge", attempt, messages, JUDGE_SCHEMA, name="plan_judge",
                      effort=JUDGE_EFFORT, max_tokens=JUDGE_MAX_TOKENS)
    data = result.data
    targets: list[JudgeTarget] = []
    for target in data.get("targets") or []:
        section = target.get("section")
        if isinstance(section, int) and 0 <= section < len(run.sections) and section not in [t.section for t in targets]:
            targets.append(JudgeTarget(section=section, reason=str(target.get("reason") or "")[:MAX_REASON_CHARS]))
    decision = "regenerate" if data.get("decision") == "regenerate" and targets else "accept"
    call = run.calls[-1]
    judged = JudgeDecision(decision=decision, targets=targets[:MAX_TARGETS], report=report, provider=call.provider,
                           model=call.model, requestId=call.requestId, costUsd=call.costUsd, latencyMs=call.latencyMs)
    run.judge.append(judged)
    run.emit("judge", {"attempt": attempt, **judged.model_dump()})
    return judged


def _judge_loop(run: _Run) -> None:
    """At most MAX_JUDGMENTS judgments; a section is regenerated at most once."""
    regenerated: set[int] = set()
    for attempt in range(1, MAX_JUDGMENTS + 1):
        decision = _judge(run, attempt)
        targets = [t.section for t in decision.targets if t.section not in regenerated]
        if decision.decision == "accept" or not targets:
            return
        for index in targets:
            regenerated.add(index)
            section = _generate_section(run, index, regenerated=True)
            run.sections[index] = section
            run.emit("generate_section", {"index": index, **section.model_dump()})


def _finish(run: _Run, failure: PlanFailure) -> None:
    """Record the failure; the caller (route or tool) decides how to show it."""
    run.error = PlanError(kind=failure.kind, message=failure.message, requestId=failure.request_id)
    log.warning("plan run failed (%s): %s spend=$%.4f calls=%d", failure.kind, failure.message,
                run.spend_usd, len(run.calls))


# --- Entry points ---


def plan_song(request: PlanRequest, on_event: OnEvent | None = None) -> PlanTrace:
    """Plan, validate and revise only (the MCP plan_song tool): no chord is generated."""
    run = _Run(request, on_event)
    try:
        if request.planner == "meta":
            run.client = _client("default")
        _plan(run)
    except PlanFailure as failure:
        _finish(run, failure)
    return run.trace()


def complete_form(request: PlanRequest, on_event: OnEvent | None = None,
                  cancelled: Callable[[], bool] | None = None) -> PlanTrace:
    """The whole run behind POST /api/plan/song: plan, generate every section, judge once or twice."""
    run = _Run(request, on_event, cancelled)
    try:
        run.check_clock()
        if request.planner == "meta":
            run.client = _client("default")
            run.judge_client = _client("judge")
        _plan(run)
        _generate_all(run)
        if request.planner == "meta":
            _judge_loop(run)
    except PlanFailure as failure:
        _finish(run, failure)
    return run.trace()
