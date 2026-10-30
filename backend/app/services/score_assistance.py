"""Bounded whole-context Meta review of locally inferred and unresolved harmony."""

from __future__ import annotations

import base64
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import TYPE_CHECKING

from app.models.score_import import MAX_NOTE_CHARS, ImportedMeasure, ScoreImportRequest, ScoreImportResponse
from app.services.score_analysis import _bounded_warnings

if TYPE_CHECKING:
    from app.services.harmony_meta import HarmonyProposal, MeasureProposal
    from app.services.score_pdf import ScoreMeasure

MAX_ASSIST_CALLS = 2
MAX_ASSIST_MEASURES = 8
MAX_ASSIST_NOTES = 512


def _target(index: int, measure: ScoreMeasure) -> dict:
    """One measure's musical evidence; titles, filenames and annotations never leave the machine."""
    # harmony_meta accepts at most 8 reading warnings of 200 characters each.
    return {"index": index, "timeSignature": list(measure.time_signature),
            "timingIsEstimated": not measure.rhythm_exact,
            "readWarnings": [warning[:200] for warning in measure.warnings[:8]],
            "notes": [{"pitch": note.midi, "spelling": note.spelling,
                       "onset": note.onset, "duration": note.duration,
                       "staff": note.staff} for note in measure.notes]}


def _next_batch(targets: list[dict]) -> list[dict]:
    """Remove the next call's targets from the front: at least one, then up to the measure and note limits."""
    batch: list[dict] = []
    note_count = 0
    while targets and len(batch) < MAX_ASSIST_MEASURES:
        next_count = len(targets[0]["notes"])
        if batch and note_count + next_count > MAX_ASSIST_NOTES:
            break
        batch.append(targets.pop(0))
        note_count += next_count
    return batch


def _printed_context(draft: ScoreImportResponse, batch: list[dict]) -> list[dict]:
    """Printed chords next to each target, at most 16 measures; interpretations are never sent as context."""
    neighbors = sorted({neighbor for target in batch
                        for neighbor in range(max(0, target["index"] - 1),
                                              min(len(draft.measures), target["index"] + 2))})
    return [{"index": index, "chords": draft.measures[index].chords}
            for index in neighbors if draft.measures[index].chords and
            draft.measures[index].chordBasis == "printed"][:16]


def _apply_proposal(measure: ImportedMeasure, source: ScoreMeasure, result: MeasureProposal,
                    proposal: HarmonyProposal) -> None:
    """Replace one measure's chords with Meta's proposal, keeping its read notes and reading caveats."""
    reading_note = measure.note
    reading_uncertain = not source.rhythm_exact or bool(source.warnings)
    source_warnings = " ".join(source.warnings)[:160]
    measure.chords = list(result.chords)
    measure.chordBasis = "inferred" if result.chords else "unreadable"
    measure.confidence = result.confidence if result.chords and not reading_uncertain else "low"
    measure.needsReview = True
    measure.analysisSource = "meta"
    measure.requestId = proposal.request_id
    measure.model = proposal.model
    # Reading caveats come first, so the length cut trims trailing evidence rather than them.
    measure.note = (("Reading remains provisional: " + (source_warnings or reading_note[:100]) + ". " if reading_uncertain else "") +
                    "Meta harmonic interpretation: " + result.evidence[:230] +
                    " Reading evidence: " + reading_note[:100])[:MAX_NOTE_CHARS]


def enrich_local_harmony(req: ScoreImportRequest, draft: ScoreImportResponse, *,
                         before_meta: Callable[[float], None] | None = None) -> ScoreImportResponse:
    """Only engine=auto authorizes a call; printed chords and N.C. stay intact.

    `before_meta(worst_case_usd)` runs once, right before the first Meta call (none when nothing needs one).
    """
    if req.engine != "auto":
        raise ValueError("Meta assistance requires an explicitly selected auto engine")
    pending = [i for i, measure in enumerate(draft.measures)
               if not measure.noChord and measure.chordBasis != "printed"]
    if not pending:
        return draft
    from app.services.score_pdf import parse_vector_score
    from app.services.harmony_meta import harmony_request, propose_harmony
    from app.services.score_context import ScoreContextError, score_context

    # Freeze the complete context before any proposal changes a target. Later
    # batches see the same source hypotheses, not earlier model guesses as facts.
    synopsis = score_context(draft)

    score = parse_vector_score(base64.b64decode(req.dataBase64, validate=True))
    source = {measure.index: measure for measure in score.measures}
    targets: list[dict] = []
    for index in pending:
        measure = source.get(index)
        if measure is None or not measure.notes or len(measure.notes) > MAX_ASSIST_NOTES:
            continue
        targets.append(_target(index, measure))

    batches = []
    while targets and len(batches) < MAX_ASSIST_CALLS:
        batch = _next_batch(targets)
        if not batch:
            break
        context = _printed_context(draft, batch)
        try:
            harmony_request(batch, draft.key, context, synopsis)
        except ValueError as exc:
            raise ScoreContextError(str(exc)) from None
        batches.append((batch, context))

    if batches and before_meta is not None:
        # Admit on the request thread before either independent call starts.
        from app.services.harmony_meta import MAX_REQUEST_USD
        before_meta(MAX_ASSIST_CALLS * MAX_REQUEST_USD)

    def propose(batch_and_context):
        batch, context = batch_and_context
        return propose_harmony(batch, draft.key, context=context, score_context=synopsis)

    if len(batches) > 1:
        # Each call reads the same frozen source synopsis. Copy the request's
        # cost context separately into each worker; wait for all settlements
        # even if one fails, before the route settles its admission.
        with ThreadPoolExecutor(max_workers=MAX_ASSIST_CALLS) as executor:
            futures = [executor.submit(copy_context().run, propose, item) for item in batches]
            proposals = [future.result() for future in futures]
    else:
        proposals = [propose(item) for item in batches]

    calls = len(proposals)
    attempted = 0
    interpreted = 0
    # Apply in source order, independently of completion order. Failures above
    # propagate instead of exposing a partly modified, successful-looking draft.
    for (batch, _), proposal in zip(batches, proposals):
        attempted += len(batch)
        for result in proposal.measures:
            _apply_proposal(draft.measures[result.index], source[result.index], result, proposal)
            interpreted += bool(result.chords)
        draft.analysisSource = "mixed"
        draft.model = proposal.model
        draft.requestId = proposal.request_id

    remaining = sum(not measure.chords and not measure.noChord for measure in draft.measures)
    summary = (f"Meta reviewed {attempted} of {len(pending)} eligible measures in {calls} bounded calls "
               "with the complete score context; "
               f"{interpreted} received reviewable proposals, {len(pending) - attempted} were not reviewed "
               f"and {remaining} remain unresolved. Printed chords, N.C. and read notes were preserved.")
    draft.warnings = _bounded_warnings([summary, *draft.warnings])
    return draft
