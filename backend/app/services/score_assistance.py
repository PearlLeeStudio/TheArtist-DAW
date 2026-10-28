"""Explicit, bounded Meta reasoning for unresolved locally read note passages."""

import base64

from app.models.score_import import ScoreImportRequest, ScoreImportResponse
from app.services.score_analysis import _warnings

MAX_ASSIST_CALLS = 2
MAX_ASSIST_MEASURES = 8
MAX_ASSIST_NOTES = 512


def enrich_local_harmony(req: ScoreImportRequest, draft: ScoreImportResponse) -> ScoreImportResponse:
    """Only engine=auto authorizes a call; confidently read printed chords stay intact."""
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
        targets.append({"index": index, "timeSignature": list(measure.time_signature),
                        "timingIsEstimated": not measure.rhythm_exact,
                        "readWarnings": [warning[:200] for warning in measure.warnings[:8]],
                        "notes": [{"pitch": note.midi, "spelling": note.spelling,
                                   "onset": note.onset, "duration": note.duration,
                                   "staff": note.staff} for note in measure.notes]})

    calls = 0
    attempted = 0
    interpreted = 0
    while targets and calls < MAX_ASSIST_CALLS:
        batch: list[dict] = []
        note_count = 0
        while targets and len(batch) < MAX_ASSIST_MEASURES:
            next_count = len(targets[0]["notes"])
            if batch and note_count + next_count > MAX_ASSIST_NOTES:
                break
            batch.append(targets.pop(0))
            note_count += next_count
        if not batch:
            break
        # Provider/config/budget failures propagate as failures. They never
        # turn into a successful-looking local result or an invented chord.
        context_indices = sorted({neighbor for target in batch
                                  for neighbor in range(max(0, target["index"] - 1),
                                                        min(len(draft.measures), target["index"] + 2))})
        context = [{"index": index, "chords": draft.measures[index].chords}
                   for index in context_indices if draft.measures[index].chords and
                   draft.measures[index].chordBasis == "printed"][:16]
        proposal = propose_harmony(batch, draft.key, context=context)
        calls += 1
        attempted += len(batch)
        for result in proposal.measures:
            measure = draft.measures[result.index]
            reading_note = measure.note
            reading_uncertain = not source[result.index].rhythm_exact or bool(source[result.index].warnings)
            source_warnings = " ".join(source[result.index].warnings)[:160]
            measure.chords = list(result.chords)
            measure.chordBasis = "inferred" if result.chords else "unreadable"
            measure.confidence = result.confidence if result.chords and not reading_uncertain else "low"
            measure.needsReview = True
            measure.analysisSource = "meta"
            measure.requestId = proposal.request_id
            measure.model = proposal.model
            measure.note = (("Reading remains provisional: " + (source_warnings or reading_note[:100]) + ". " if reading_uncertain else "") +
                            "Meta harmonic interpretation: " + result.evidence[:230] +
                            " Reading evidence: " + reading_note[:100])[:400]
            interpreted += bool(result.chords)
        draft.analysisSource = "mixed"
        draft.model = proposal.model
        draft.requestId = proposal.request_id

    remaining = sum(not measure.chords and not measure.noChord for measure in draft.measures)
    summary = (f"Explicit Meta assistance attempted {attempted} unresolved measures in {calls} bounded calls; "
               f"{interpreted} received reviewable proposals and {remaining} remain unresolved. "
               "Locally read notes and existing chord symbols were preserved.")
    draft.warnings = _warnings([summary, *draft.warnings])
    return draft
