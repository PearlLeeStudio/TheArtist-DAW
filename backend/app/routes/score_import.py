from fastapi import APIRouter, HTTPException

from app.models.score_import import ScoreImportRequest, ScoreImportResponse
from app.services.llm import BudgetExceeded, LedgerError, LLMConfigError, LLMError, LLMTimeout
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
    except (LLMConfigError, LedgerError):
        raise HTTPException(status_code=503, detail="Score import is not configured: check MODEL_API_KEY, "
                            "Meta Standard muse-spark-1.3 settings, prices, and the cost ledger.") from None
    except LLMTimeout:
        raise HTTPException(status_code=504, detail="Meta did not finish reading the score within 75 seconds. "
                            "Try a shorter score or a clearer image.") from None
    except LLMError as exc:
        request = f" Request ID: {exc.request_id}." if exc.request_id else ""
        raise HTTPException(status_code=502, detail="Meta could not return a valid score transcription. "
                            "Try a clearer or shorter score." + request) from None
