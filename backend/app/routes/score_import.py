from typing import Annotated
import asyncio
import json
import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.models.score_import import ScoreImportRequest, ScoreImportResponse
from app.services import limits
from app.services.limits import Caller
from app.services.llm import BudgetExceeded, LedgerError, LLMConfigError, LLMDisabled, LLMError, LLMTimeout, track_call_costs
from app.services.score_import import ScoreInputError, import_score

router = APIRouter()
PUBLIC_HOST_REASON = ("Meta reading of the whole score file is not available on this public server; choose "
                      "engine \"auto\" (bounded harmony and form analysis with the whole score context) or \"local\".")


@router.post("/import/score", response_model=ScoreImportResponse)
def import_score_route(req: ScoreImportRequest,
                       caller: Annotated[Caller | None, Depends(limits.caller)] = None) -> ScoreImportResponse:
    return _run_import(req, caller)


def _run_import(req: ScoreImportRequest, caller: Caller | None,
                on_progress: Callable[[str], None] | None = None) -> ScoreImportResponse:
    # Whole-file reading on a public host needs explicit opt-in. Dollar allowances
    # apply unless the operator has explicitly enabled development unlimited mode.
    if req.engine in {"meta", "verified"} and not limits.full_file_score_import_allowed():
        raise HTTPException(status_code=403, detail=PUBLIC_HOST_REASON)
    charge: dict = {}

    def admit(worst_case_usd: float) -> None:
        # Admitted only when the service is about to call Meta (an auto import the local reader
        # finishes costs nothing), then settled only for this request's calls.
        admission = limits.limiter.admit(caller, estimate_usd=worst_case_usd)
        if admission is not None:
            charge.update(admission=admission)

    try:
        # This is a synchronous FastAPI worker. Its context covers both the note
        # batches and form call, without counting another request's settlements.
        with track_call_costs() as costs:
            kwargs = {"on_progress": on_progress} if on_progress is not None else {}
            return import_score(req, before_meta=admit if req.engine != "local" else None, **kwargs)
    except ScoreInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except BudgetExceeded:
        raise HTTPException(status_code=429, detail="Score import would exceed the Meta API cost limit. "
                            "Check the request limit and remaining API budget.") from None
    except LLMDisabled:  # before its base class LLMConfigError, which keeps the configuration message
        raise HTTPException(status_code=503, detail="Meta features are disabled on this server; "
                            "the local reader is still available.") from None
    except (LLMConfigError, LedgerError):
        raise HTTPException(status_code=503, detail="Meta assistance is not configured: check MODEL_API_KEY, "
                            "Meta Standard settings and the cost ledger, or select local analysis.") from None
    except LLMTimeout:
        raise HTTPException(status_code=504, detail="Meta did not finish within the selected reader's time limit. "
                            "Try a shorter passage or select local analysis.") from None
    except LLMError as exc:
        request = f" Request ID: {exc.request_id}." if exc.request_id else ""
        raise HTTPException(status_code=502, detail="Meta could not return a valid score or harmony result. "
                            "Try a shorter passage or select local analysis." + request) from None
    finally:
        if admission := charge.get("admission"):
            limits.limiter.settle(admission, costs.cost_usd if costs.reliable else admission.estimate_usd)


@router.post("/import/score/stream")
async def import_score_stream(req: ScoreImportRequest,
                             caller: Annotated[Caller | None, Depends(limits.caller)] = None):
    """Send actual reader stages and keep gateways alive during the bounded Meta call."""
    def frame(event: str, data: dict) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()

    async def stream():
        yield frame("progress", {"label": "Checking the uploaded score…"})
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def progress(label: str) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, ("progress", {"label": label}))
            except RuntimeError:
                pass  # The browser disconnected; the bounded call still settles its cost.

        async def work():
            try:
                result = await asyncio.to_thread(_run_import, req, caller, progress)
                await queue.put(("result", result.model_dump(mode="json")))
            except HTTPException as exc:
                await queue.put(("error", {"detail": exc.detail, "status": exc.status_code}))
            except Exception:
                logging.getLogger(__name__).exception("Score import failed")
                await queue.put(("error", {"detail": "Score analysis failed. Please try again.", "status": 500}))

        # Keep the worker alive on disconnect: aborting an HTTP stream does not
        # cancel a paid upstream call, which must still settle its allowance.
        task = asyncio.create_task(work())
        _imports.add(task)
        task.add_done_callback(_imports.discard)
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=5)
            except TimeoutError:
                yield b": reading score\n\n"
                continue
            yield frame(event, data)
            if event in {"result", "error"}:
                break

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


_imports: set[asyncio.Task] = set()
