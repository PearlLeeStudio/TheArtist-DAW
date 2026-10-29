"""Explicit, bounded Meta reasoning for unresolved locally read note passages."""

from __future__ import annotations

import base64
from collections.abc import Callable
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
    """Only engine=auto authorizes a call; confidently read printed chords stay intact.

    `before_meta(worst_case_usd)` runs once, right before the first Meta call (none when nothing needs one).
    """
    if req.engine != "auto":
        raise ValueError("Meta assistance requires an explicitly selected auto engine")
    pending = [i for i, measure in enumerate(draft.measures) if not measure.chords and not measure.noChord]
    if not pending:
        return draft
    from app.services.score_pdf import parse_vector_score
    from app.services.harmony_meta import propose_harmony

    score = parse_vector_score(base64.b64decode(req.dataBase64, validate=True))
    source = {measure.index: measure for measure in score.measures}
    targets: list[dict] = []
    for index in pending:
        measure = source.get(index)
        if measure is None or not measure.notes or len(measure.notes) > MAX_ASSIST_NOTES:
            continue
        targets.append(_target(index, measure))

    calls = 0
    attempted = 0
    interpreted = 0
    while targets and calls < MAX_ASSIST_CALLS:
        batch = _next_batch(targets)
        if not batch:
            break
        context = _printed_context(draft, batch)
        if calls == 0 and before_meta is not None:
            # The caller's spend admission, once, only when Meta is really about to be called
            from app.services.harmony_meta import MAX_REQUEST_USD
            before_meta(MAX_ASSIST_CALLS * MAX_REQUEST_USD)
        # Provider/config/budget failures propagate as failures. They never
        # turn into a successful-looking local result or an invented chord.
        proposal = propose_harmony(batch, draft.key, context=context)
        calls += 1
        attempted += len(batch)
        for result in proposal.measures:
            _apply_proposal(draft.measures[result.index], source[result.index], result, proposal)
            interpreted += bool(result.chords)
        draft.analysisSource = "mixed"
        draft.model = proposal.model
        draft.requestId = proposal.request_id

    remaining = sum(not measure.chords and not measure.noChord for measure in draft.measures)
    summary = (f"Explicit Meta assistance attempted {attempted} unresolved measures in {calls} bounded calls; "
               f"{interpreted} received reviewable proposals and {remaining} remain unresolved. "
               "Locally read notes and existing chord symbols were preserved.")
    draft.warnings = _bounded_warnings([summary, *draft.warnings])
    return draft
