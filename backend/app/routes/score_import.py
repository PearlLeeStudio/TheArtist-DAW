from fastapi import APIRouter, HTTPException

from app.models.score_import import ScoreImportRequest, ScoreImportResponse
from app.services.llm import BudgetExceeded, LedgerError, LLMConfigError, LLMDisabled, LLMError, LLMTimeout
from app.services.score_import import ScoreInputError, import_score

router = APIRouter()


@router.post("/import/score", response_model=ScoreImportResponse)
def import_score_route(req: ScoreImportRequest) -> ScoreImportResponse:
    try:
        return import_score(req)
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
