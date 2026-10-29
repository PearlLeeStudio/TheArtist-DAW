"""POST /api/plan/song (+ /stream): complete a song form from a sketch (app.services.planner).

The JSON route answers the whole trace on success and, on a failed run, the same
trace under the HTTP status of the failure, so the client always sees the request
ids and the spend so far. The stream sends each step as it happens and ends with
one `complete` or `error` frame carrying the trace. Nothing is applied server-side.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.models.plan import PlanError, PlanRequest, PlanTrace
from app.routes.generate import _sse, _sse_response
from app.services import planner

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
def plan_song_route(req: PlanRequest):
    """Plan the rest of the form, generate every planned section, judge once or twice."""
    trace = planner.complete_form(req)
    if trace.error is not None:
        return JSONResponse(status_code=error_status(trace.error), content=trace.model_dump(mode="json"))
    return trace


@router.post("/plan/song/stream")
async def plan_song_stream(req: PlanRequest) -> StreamingResponse:
    """The same run as SSE: plan, validate, revise, generate_section (one per section, also
    for a regeneration), judge, then one terminal complete or error frame with the trace."""
    async def stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_event(event: str, payload: dict) -> None:
            # The run is on a worker thread; call_soon_threadsafe keeps the frames in order
            # ahead of the done-callback's sentinel (see routes/generate.py).
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (event, payload))
            except RuntimeError:
                pass  # event loop closed (client disconnected)

        future: asyncio.Future = loop.run_in_executor(None, planner.complete_form, req, on_event)
        future.add_done_callback(lambda _f: queue.put_nowait(_STREAM_DONE))
        while (item := await queue.get()) is not _STREAM_DONE:
            yield _sse(*item)
        try:
            trace = future.result()
        except Exception:
            log.exception("Song planning failed")
            yield _sse("error", {"detail": "Song planning failed"})
            return
        yield _sse("error" if trace.error is not None else "complete", trace.model_dump(mode="json"))

    return _sse_response(stream())
