"""Read-only proposal endpoint; only a user's editor action applies a candidate.

When Meta cannot take the request, the search runs without Meta and says so (selection "local"): the
caller's daily Meta allowance or the server's daily Meta cap is used up (the limiter's 429,
metaUnavailable "limit"), or the limiter's ledger cannot be read or its settings are refused (its 503,
"paused" or "unconfigured"). A search that will not call Meta needs no admission at all.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.models.reharmonize import ReharmRequest, ReharmResponse
from app.services import limits, llm, reharmonize_agent
from app.services.limits import Caller

router = APIRouter()


def _detail(exc: llm.LLMError) -> str:
    """The editor shows this text: never a ledger path, a cost figure or the provider's own words."""
    if isinstance(exc, llm.BudgetExceeded):
        return "The reharmonization search reached its cost limit."
    if isinstance(exc, llm.LedgerError):
        return "The Meta spend ledger cannot be read or written on this server."
    if isinstance(exc, llm.LLMResponseError) and exc.kind == "http" and exc.status_code:
        request = f", request {exc.request_id}" if exc.request_id else ""
        return f"Meta could not complete the search (HTTP {exc.status_code}{request})."
    return str(exc)


@router.post("/reharmonize", response_model=ReharmResponse)
def reharmonize_route(req: ReharmRequest, caller: Annotated[Caller | None, Depends(limits.caller)] = None):
    admission, meta_allowed, reason = None, True, None
    if llm.meta_availability() is None:
        try:
            admission = limits.limiter.admit(caller, estimate_usd=reharmonize_agent.MAX_USD)
        except HTTPException as refusal:
            if refusal.status_code == 429:
                meta_allowed = False
            elif refusal.status_code == 503:  # the limiter cannot read its ledger or its settings are refused
                reason = "paused" if refusal.detail == limits.LEDGER_UNREADABLE else "unconfigured"
            else:  # a missing session id stays an error
                raise
    with llm.track_call_costs() as costs:
        try:
            return reharmonize_agent.propose(req, meta_allowed=meta_allowed, unavailable_reason=reason)
        except llm.LLMError as exc:
            status = (429 if isinstance(exc, llm.BudgetExceeded) else 504 if isinstance(exc, llm.LLMTimeout)
                      else 503 if isinstance(exc, (llm.LLMConfigError, llm.LLMDisabled, llm.LedgerError)) else 502)
            raise HTTPException(status_code=status, detail=_detail(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        finally:
            limits.limiter.settle(admission, costs.cost_usd if costs.reliable else reharmonize_agent.MAX_USD)
