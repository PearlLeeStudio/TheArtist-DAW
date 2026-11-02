"""Read-only proposal endpoint; only a user's editor action applies a candidate.

When the caller's daily Meta allowance or the server's daily Meta cap is used up (the limiter's 429),
the search runs without Meta and says so (selection "local", metaUnavailable "limit").
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.models.reharmonize import ReharmRequest, ReharmResponse
from app.services import limits, llm, reharmonize_agent
from app.services.limits import Caller

router = APIRouter()


@router.post("/reharmonize", response_model=ReharmResponse)
def reharmonize_route(req: ReharmRequest, caller: Annotated[Caller | None, Depends(limits.caller)] = None):
    try:
        admission = limits.limiter.admit(caller, estimate_usd=reharmonize_agent.MAX_USD)
        meta_allowed = True
    except HTTPException as refusal:
        if refusal.status_code != 429:  # a missing session id or a misconfigured limit stays an error
            raise
        admission, meta_allowed = None, False
    with llm.track_call_costs() as costs:
        try:
            return reharmonize_agent.propose(req, meta_allowed=meta_allowed)
        except llm.LLMError as exc:
            status = (429 if isinstance(exc, llm.BudgetExceeded) else 504 if isinstance(exc, llm.LLMTimeout)
                      else 503 if isinstance(exc, (llm.LLMConfigError, llm.LLMDisabled)) else 502)
            # The search's own cost cap is named without figures; the server log has them
            detail = ("The reharmonization search reached its cost limit."
                      if isinstance(exc, llm.BudgetExceeded) else str(exc))
            raise HTTPException(status_code=status, detail=detail) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        finally:
            limits.limiter.settle(admission, costs.cost_usd if costs.reliable else reharmonize_agent.MAX_USD)
