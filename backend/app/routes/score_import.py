from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.models.score_import import ScoreImportRequest, ScoreImportResponse
from app.services import limits
from app.services.limits import Caller
from app.services.llm import BudgetExceeded, LedgerError, LLMConfigError, LLMDisabled, LLMError, LLMTimeout
from app.services.score_import import ScoreInputError, import_score

router = APIRouter()
PUBLIC_HOST_REASON = ("Meta reading of the whole score file is not available on this public server; choose "
                      "engine \"auto\" (Meta interprets only the bars local reading leaves open) or \"local\".")


@router.post("/import/score", response_model=ScoreImportResponse)
def import_score_route(req: ScoreImportRequest,
                       caller: Annotated[Caller | None, Depends(limits.caller)] = None) -> ScoreImportResponse:
    # A public host keeps the editor's bounded assist (auto: at most two 8-bar calls, admitted against
    # the limits below) and refuses the whole-file read, whose one request may reserve $1.35
    if req.engine == "meta" and limits.public_host():
        raise HTTPException(status_code=403, detail=PUBLIC_HOST_REASON)
    charge: dict = {}

    def admit(worst_case_usd: float) -> None:
        # Admitted only when the service is about to call Meta (an auto import the local reader
        # finishes costs nothing), then settled at what the ledger recorded for it
        admission = limits.limiter.admit(caller, estimate_usd=worst_case_usd)
        if admission is not None:
            charge.update(admission=admission, spent_before=limits.spent_usd())

    try:
        return import_score(req, before_meta=admit if req.engine != "local" else None)
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
        spent_before = charge.get("spent_before")
        if spent_before is not None and (spent_after := limits.spent_usd()) is not None:
            limits.limiter.settle(charge["admission"], spent_after - spent_before)
