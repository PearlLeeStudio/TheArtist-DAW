"""POST /api/review/candidates: the second ear over one Generate's A/B/C (app.services.review).

The route goes through the spend limiter like routes/plan.py: admitted at the review's
worst case before the call, settled at what the call cost afterwards, failures included.
A failure answers its HTTP status with the error, the request id and the spend; there is
no fallback choice. Nothing is applied: adopting a candidate stays the user's click.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.models.review import ReviewError, ReviewErrorResponse, ReviewRequest, ReviewResponse
from app.services import limits, review
from app.services.limits import Caller

router = APIRouter()

# The failure's HTTP status, as routes/plan.py maps the planner's
_STATUS = {"disabled": 503, "config": 503, "budget": 429, "timeout": 504, "llm": 502}


@router.post(
    "/review/candidates",
    response_model=ReviewResponse,
    responses={code: {"model": ReviewErrorResponse} for code in sorted(set(_STATUS.values()))},
)
def review_candidates_route(req: ReviewRequest, caller: Annotated[Caller | None, Depends(limits.caller)] = None):
    """Facts per candidate, one judge call, and each reason checked against the facts."""
    admission = limits.limiter.admit(caller, estimate_usd=review.REVIEW_MAX_USD)
    try:
        result = review.review_candidates(req)
    except review.ReviewFailure as failure:
        limits.limiter.settle(admission, failure.cost_usd)
        body = ReviewErrorResponse(
            detail=failure.message,
            error=ReviewError(kind=failure.kind, message=failure.message, requestId=failure.request_id),
            provider=failure.provider, model=failure.model, costUsd=failure.cost_usd, latencyMs=failure.latency_ms,
        )
        return JSONResponse(status_code=_STATUS[failure.kind], content=body.model_dump(mode="json"))
    limits.limiter.settle(admission, result.costUsd)
    return result
