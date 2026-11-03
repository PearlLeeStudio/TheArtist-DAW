"""Meta-first reading, local recovery, and deterministic comparison.

Agreement is not accuracy proof. Printed local symbols are preserved, conflicts
are review flags. A failed Meta request returns an explicitly attributed local reading.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
import logging
from fastapi import HTTPException

from app.models.score_import import ScoreImportRequest, ScoreImportResponse, ScoreVerification
from app.services.score_analysis import LocalScoreUnsupported, analyze_local_score
from app.services.score_context import ScoreContextError, score_context
from app.services.llm import CreditExhausted, LLMDisabled, LLMError
from app.services.score_import import (
    MAX_META_SCORE_MEASURES, SCORE_MAX_REQUEST_USD, ScoreInputError, _import_meta_score,
)

# How long the Meta call waits for a quick local reading, so a score longer than
# Meta's bar limit opens locally without a paid request that cannot align with it.
LOCAL_HEAD_START_S = 2.0


def _review(bar, fields):
    bar.needsReview = True
    bar.confidence = "low"
    bar.note = ("Local/Meta comparison: " + ", ".join(fields) + ". " + bar.note)[:400]


def compare_readings(local: ScoreImportResponse | None, meta: ScoreImportResponse) -> ScoreImportResponse:
    result = meta.model_copy(deep=True)
    meta_count = len(meta.measures)
    if local is None:
        for bar in result.measures:
            bar.needsReview = True
            if bar.confidence == "high":
                bar.confidence = "medium"
        result.verification = ScoreVerification(
            status="local_unavailable", localMeasures=0, metaMeasures=meta_count,
            comparedMeasures=0, disputedMeasures=[],
            notes=["The local reader could not read this file. Meta read the original, but local cross-checking was unavailable; review every bar."])
        return result

    notes = []
    if local.key and local.key != meta.key:
        notes.append(f"Key differs: local {local.key}; Meta {meta.key or 'unreadable'}.")
    if local.timeSignature and local.timeSignature != meta.timeSignature:
        meta_meter = '/'.join(map(str, meta.timeSignature)) if meta.timeSignature else 'unreadable'
        notes.append(f"Meter differs: local {local.timeSignature[0]}/{local.timeSignature[1]}; Meta {meta_meter}.")
    warnings = list(dict.fromkeys([*local.warnings, *meta.warnings]))
    if len(warnings) > 32:
        raise ScoreInputError("The combined readings have too many warnings. Split the score for comparison.", 422)
    if len(local.measures) != meta_count:
        # Unequal bar counts cannot be zipped safely. Keep the complete local
        # reading, including printed symbols, instead of shifting Meta proposals.
        result = local.model_copy(deep=True)
        result.model, result.requestId, result.analysisSource = meta.model, meta.requestId, "mixed"
        result.warnings = warnings
        notes.insert(0, f"Bar counts differ: local {len(local.measures)}; Meta {meta_count}. The complete local reading is retained; no bars were merged.")
        for bar in result.measures:
            _review(bar, ["bar alignment could not be established"])
        result.verification = ScoreVerification(
            status="unaligned", localMeasures=len(local.measures), metaMeasures=meta_count,
            comparedMeasures=0, disputedMeasures=list(range(len(result.measures))), notes=notes)
        return result

    local_context, meta_context = score_context(local), score_context(meta)
    result.warnings = warnings
    disputed = []
    for index, (source, checked) in enumerate(zip(local.measures, meta.measures)):
        fields = []
        if source.chords != checked.chords or source.noChord != checked.noChord:
            fields.append("chord readings differ")
        source_pitches = local_context["measures"][index]["pitchClasses"]
        checked_pitches = meta_context["measures"][index]["pitchClasses"]
        if source_pitches and source_pitches != checked_pitches:
            fields.append("note evidence differs or is missing")
        if source.timeSignature and checked.timeSignature and source.timeSignature != checked.timeSignature:
            fields.append("bar meter differs")
        retain_local = source.noChord or (source.chordBasis == "printed" and source.chords)
        if source.chords and not checked.chords and not checked.noChord:
            retain_local = True
            fields.append("Meta supplied no chord; the local hypothesis is retained for review")
        if retain_local:
            result.measures[index] = source.model_copy(deep=True)
            result.measures[index].analysisSource = "local"
            result.measures[index].model = source.model
            result.measures[index].requestId = None
            result.analysisSource = "mixed"
        rank = {"low": 0, "medium": 1, "high": 2}
        result.measures[index].confidence = min((source.confidence, checked.confidence), key=rank.get)
        result.measures[index].needsReview = source.needsReview or checked.needsReview
        if fields or notes:
            disputed.append(index)
            _review(result.measures[index], fields or ["score key or meter differs"])
        # Agreement never upgrades confidence or clears an existing review flag.
        elif source.needsReview:
            result.measures[index].needsReview = True
    result.verification = ScoreVerification(
        status="compared", localMeasures=len(local.measures), metaMeasures=meta_count,
        comparedMeasures=len(local.measures), disputedMeasures=disputed, notes=notes)
    return result


def import_verified_score(req: ScoreImportRequest, attachment: dict, *,
                          before_meta: Callable[[float], None] | None = None,
                          on_progress: Callable[[str], None] | None = None) -> ScoreImportResponse:
    progress = on_progress or (lambda _label: None)
    def read_local():
        try:
            local = analyze_local_score(req)
            if req.mode == "infer_harmony":
                from app.services.score_completion import complete_sparse_harmony
                local = complete_sparse_harmony(local)
            return local
        except (LocalScoreUnsupported, ScoreInputError):
            return None

    local = None
    local_future = None
    # Both readers consume the original, never each other's hypotheses. Keep
    # Meta's attribution and fallback rules while overlapping independent work.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        # Admission first: no reader starts for a request the limiter refuses.
        if before_meta is not None:
            before_meta(SCORE_MAX_REQUEST_USD)
        local_future = executor.submit(copy_context().run, read_local)
        try:
            local = local_future.result(timeout=LOCAL_HEAD_START_S)
        except FutureTimeout:
            pass
        if local is not None and len(local.measures) > MAX_META_SCORE_MEASURES:
            # Meta reads at most MAX_META_SCORE_MEASURES bars, so its reading could
            # never align with this score; the complete local reading opens instead.
            progress(f"Local analysis is ready for all {len(local.measures)} bars. Meta reads at most "
                     f"{MAX_META_SCORE_MEASURES} bars, so the comparison was skipped.")
            local.verification = ScoreVerification(
                status="local_only", localMeasures=len(local.measures), metaMeasures=0,
                comparedMeasures=0, disputedMeasures=[],
                notes=[f"Meta reads at most {MAX_META_SCORE_MEASURES} bars; this {len(local.measures)}-bar score "
                       "opened from the local reader without a Meta comparison."])
            return local
        progress("Meta is reading the original score while the local reader checks its notation…")
        checked = _import_meta_score(req, attachment)
        local = local_future.result()
    except LLMDisabled as off:
        # Meta is paused or switched off: nothing was read by Meta, which is not a problem with the file.
        # Without a local reading the route names the pause (503); with one, the score opens and says why
        state = "paused" if isinstance(off, CreditExhausted) else "switched off"
        logging.getLogger(__name__).warning("Meta score reading skipped: Meta is %s", state)
        local = local_future.result() if local_future is not None else read_local()
        if local is None:
            raise
        local.verification = ScoreVerification(
            status="local_fallback", localMeasures=len(local.measures), metaMeasures=0,
            comparedMeasures=0, disputedMeasures=[],
            notes=[f"Meta is {state} on this server, so the local reader opened this score without a Meta "
                   "comparison; unresolved bars remain editable."])
        progress("Local analysis is ready. You can import the reviewed score.")
        return local
    except (LLMError, ScoreInputError, HTTPException) as failure:
        logging.getLogger(__name__).warning("Meta score reading failed; using local reader: kind=%s request_id=%s",
                                            getattr(failure, "kind", type(failure).__name__),
                                            getattr(failure, "request_id", None))
        progress("Meta reading was unavailable. Continuing with the local score reader…")
        local = local_future.result() if local_future is not None else read_local()
        if local is None:
            raise ScoreInputError("Neither reader could recover an editable score from this file. "
                                  "Use a PDF with readable notation or a clearer image.", 422) from failure
        local.verification = ScoreVerification(
            status="local_fallback", localMeasures=len(local.measures), metaMeasures=0,
            comparedMeasures=0, disputedMeasures=[],
            notes=["Meta reading was unavailable. The local reader recovered this score; unresolved bars remain editable."])
        progress("Local analysis is ready. You can import the reviewed score.")
        return local
    finally:
        executor.shutdown(wait=True)

    try:
        progress("Comparing both readings and marking unresolved bars for review…")
        return compare_readings(local, checked)
    except ScoreContextError as exc:
        raise ScoreInputError(str(exc), 422) from None
