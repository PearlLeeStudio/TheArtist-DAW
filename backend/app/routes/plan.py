"""POST /api/plan/song (+ /stream): complete a song form from a sketch (app.services.planner).

The JSON route answers the whole trace on success and, on a failed run, the same
trace under the HTTP status of the failure, so the client always sees the request
ids and the spend so far. The stream sends each step as it happens and ends with
one `complete` or `error` frame carrying the trace. Nothing is applied server-side.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.models.plan import PlanError, PlanRequest, PlanTrace
from app.routes.generate import _sse, _sse_response
from app.services import limits, planner
from app.services.limits import Admission, Caller

log = logging.getLogger(__name__)

router = APIRouter()

# The failure's HTTP status, as routes/score_import.py maps the client's errors
_STATUS = {"disabled": 503, "config": 503, "budget": 429, "timeout": 504, "llm": 502, "invalid": 502,
           "generation": 500}
_STREAM_DONE = object()


def error_status(error: PlanError) -> int:
    return _STATUS.get(error.kind, 500)


def error_detail(trace: PlanTrace) -> str:
    """One line for callers that take a message, not a trace (MCP): the failure, its request ids and the spend."""
    assert trace.error is not None
    ids = [call.requestId for call in trace.calls if call.requestId]
    where = f" Request ids: {', '.join(ids)}." if ids else ""
    return f"{trace.error.message}.{where} Spent ${trace.spendUsd:.4f} over {len(trace.calls)} LLM call(s)."


def _admit(req: PlanRequest, caller: Caller | None) -> Admission | None:
    """The limiter's charge for a Meta run, whose reservations the planner caps at MAX_RUN_USD; none for rules."""
    if req.planner != "meta":
        return None
    return limits.limiter.admit(caller, estimate_usd=planner.MAX_RUN_USD)


def _complete_and_settle(req: PlanRequest, admission: Admission | None,
                         on_event: planner.OnEvent | None = None,
                         cancelled: Callable[[], bool] | None = None) -> PlanTrace:
    """The worker owns settlement even when its streaming consumer disconnects.

    An unexpected failure has no reliable trace, so keep the admitted worst case.
    Do not refund an unfinished worker just because the browser stopped listening.
    """
    trace: PlanTrace | None = None
    try:
        trace = planner.complete_form(req, on_event, cancelled)
        return trace
    finally:
        actual = trace.spendUsd if trace is not None else admission.estimate_usd if admission is not None else 0.0
        limits.limiter.settle(admission, actual)


def plan_only(req: PlanRequest) -> PlanTrace:
    """plan_song as the MCP tool runs it: plan, validate, revise; a failed run is raised with
    its HTTP status so the tool result is an error, never a trace that looks like a plan."""
    trace = planner.plan_song(req)
    if trace.error is not None:
        raise HTTPException(status_code=error_status(trace.error), detail=error_detail(trace))
    return trace


@router.post(
    "/plan/song",
    response_model=PlanTrace,
    responses={code: {"model": PlanTrace} for code in sorted(set(_STATUS.values()))},
)
def plan_song_route(req: PlanRequest, caller: Annotated[Caller | None, Depends(limits.caller)] = None):
    """Plan the rest of the form, generate every planned section, judge once or twice."""
    admission = _admit(req, caller)
    trace = _complete_and_settle(req, admission)
    if trace.error is not None:
        return JSONResponse(status_code=error_status(trace.error), content=trace.model_dump(mode="json"))
    return trace


@router.post("/plan/song/stream")
async def plan_song_stream(req: PlanRequest,
                           caller: Annotated[Caller | None, Depends(limits.caller)] = None) -> StreamingResponse:
    """The same run as SSE: plan, validate, revise, generate_section (one per section, also
    for a regeneration), judge, then one terminal complete or error frame with the trace."""
    admission = _admit(req, caller)  # refused here, so an over-limit run is a 429, never a stream

    async def stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        cancelled = threading.Event()

        def on_event(event: str, payload: dict) -> None:
            # The run is on a worker thread; call_soon_threadsafe keeps the frames in order
            # ahead of the done-callback's sentinel (see routes/generate.py).
            if cancelled.is_set():
                return
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (event, payload))
            except RuntimeError:
                pass  # event loop closed (client disconnected)

        def worker_done(future: asyncio.Future) -> None:
            # Retrieve exceptions even after the consumer has gone away.
            if not future.cancelled():
                future.exception()
            if not cancelled.is_set():
                queue.put_nowait(_STREAM_DONE)

        # Await only the event queue, never the executor future: cancelling this
        # generator must not discard the worker's trace or its actual settlement.
        future: asyncio.Future = loop.run_in_executor(
            None, _complete_and_settle, req, admission, on_event, cancelled.is_set)
        future.add_done_callback(worker_done)
        try:
            while (item := await queue.get()) is not _STREAM_DONE:
                yield _sse(*item)
            try:
                trace = future.result()
            except Exception:
                log.exception("Song planning failed")
                yield _sse("error", {"detail": "Song planning failed"})
                return
            yield _sse("error" if trace.error is not None else "complete", trace.model_dump(mode="json"))
        finally:
            # The current bounded HTTP/model call finishes, records its cost,
            # then the planner stops before starting another call or section.
            cancelled.set()

    return _sse_response(stream())
