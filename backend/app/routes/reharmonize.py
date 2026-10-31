"""Read-only proposal endpoint; only a user's editor action applies a candidate."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.models.reharmonize import ReharmRequest, ReharmResponse
from app.services import limits, llm, reharmonize_agent
from app.services.limits import Caller

router = APIRouter()


@router.post("/reharmonize", response_model=ReharmResponse)
def reharmonize_route(req: ReharmRequest, caller: Annotated[Caller | None, Depends(limits.caller)] = None):
    admission = limits.limiter.admit(caller, estimate_usd=reharmonize_agent.MAX_USD)
    with llm.track_call_costs() as costs:
        try:
            return reharmonize_agent.propose(req)
        except llm.LLMError as exc:
            status = (429 if isinstance(exc, llm.BudgetExceeded) else 504 if isinstance(exc, llm.LLMTimeout)
                      else 503 if isinstance(exc, (llm.LLMConfigError, llm.LLMDisabled)) else 502)
            raise HTTPException(status_code=status, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        finally:
            limits.limiter.settle(admission, costs.cost_usd if costs.reliable else reharmonize_agent.MAX_USD)
