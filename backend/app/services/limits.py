"""Judge-server lockdown and daily Meta spend limits for the routes that call Meta.

THEARTIST_PUBLIC_HOST (off by default) marks a server that strangers reach: the DAW
handoff, the warmup route and the MCP mount are refused there, score import stays on
the local reader, and the planner runs only through the limiter below. The limiter
(THEARTIST_META_LIMITS, forced on by the public host) admits a Meta-calling request
while its worst-case reservation fits the caller's daily allowance and the server's
daily cap, and answers 429 otherwise, before anything is reserved. Allowances are kept
per UTC day in this process, keyed by the X-TheArtist-Session header or, for a request
carrying THEARTIST_JUDGE_CODE, by that code; the daily cap is read from the ledger that
records every call. There are no per-IP limits.
"""

from __future__ import annotations

import hmac
import math
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from app.services.env_flags import env_bool
from app.services.llm import Ledger, LLMError, _round_usd

PUBLIC_HOST_VAR = "THEARTIST_PUBLIC_HOST"
LIMITS_VAR = "THEARTIST_META_LIMITS"
SESSION_LIMIT_VAR = "THEARTIST_META_SESSION_LIMIT_USD"
DAILY_LIMIT_VAR = "THEARTIST_META_DAILY_LIMIT_USD"
JUDGE_CODE_VAR = "THEARTIST_JUDGE_CODE"
JUDGE_LIMIT_VAR = "THEARTIST_JUDGE_CODE_DAILY_USD"
SESSION_HEADER = "X-TheArtist-Session"
JUDGE_CODE_HEADER = "X-TheArtist-Judge-Code"
DEFAULT_SESSION_LIMIT_USD = 1.0
DEFAULT_DAILY_LIMIT_USD = 10.0
DEFAULT_JUDGE_LIMIT_USD = 5.0
MAX_SESSION_CHARS = 128
_TOLERANCE_USD = 1e-9  # as the ledger's cap check: a request that exactly fills an allowance still fits
_LEDGER_UNREADABLE = ("The Meta spend ledger cannot be read; check THEARTIST_META_LEDGER and "
                      "THEARTIST_META_BUDGET_USD.")


def public_host(env: Mapping[str, str] | None = None) -> bool:
    return env_bool(PUBLIC_HOST_VAR, False, env)


def limits_enabled(env: Mapping[str, str] | None = None) -> bool:
    """The limiter runs on a public host, or wherever THEARTIST_META_LIMITS opts in."""
    return public_host(env) or env_bool(LIMITS_VAR, False, env)


def refuse_on_public_host(reason: str) -> Callable[[], None]:
    """A route dependency that answers 403 with `reason` while THEARTIST_PUBLIC_HOST is on."""
    def refuse() -> None:
        if public_host():
            raise HTTPException(status_code=403, detail=reason)
    return refuse


@dataclass(frozen=True)
class Caller:
    """What the limiter knows about a request: its session id and judge code headers."""
    session: str | None = None
    judge_code: str | None = None


def caller(request: Request) -> Caller:
    """Route dependency; a direct call of a route (the MCP adapter) passes no caller instead."""
    return Caller((request.headers.get(SESSION_HEADER) or "").strip() or None,
                  (request.headers.get(JUDGE_CODE_HEADER) or "").strip() or None)


@dataclass(frozen=True)
class Admission:
    """An admitted request's charge: `estimate_usd` against `pool` on `day`, until it is settled."""
    day: str
    pool: str
    estimate_usd: float


@dataclass(frozen=True)
class Limits:
    session_usd: float
    daily_usd: float
    judge_code: str
    judge_usd: float


def _usd(env: Mapping[str, str], name: str, default: float) -> float:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value >= 0):
        raise ValueError(f"{name} must be a non-negative number, got {raw!r}")
    return value


def configured_limits(env: Mapping[str, str] | None = None) -> Limits:
    env = os.environ if env is None else env
    return Limits(_usd(env, SESSION_LIMIT_VAR, DEFAULT_SESSION_LIMIT_USD),
                  _usd(env, DAILY_LIMIT_VAR, DEFAULT_DAILY_LIMIT_USD),
                  (env.get(JUDGE_CODE_VAR) or "").strip(),
                  _usd(env, JUDGE_LIMIT_VAR, DEFAULT_JUDGE_LIMIT_USD))


def _pool(caller: Caller, limits: Limits) -> tuple[str, float, str]:
    """(pool key, its daily allowance, its name in messages) for the request, or the HTTP refusal."""
    if caller.judge_code is not None:
        if not limits.judge_code or not hmac.compare_digest(caller.judge_code.encode(), limits.judge_code.encode()):
            raise HTTPException(status_code=403, detail=f"The {JUDGE_CODE_HEADER} header does not match this "
                                                        "server's judge code.")
        return "judge", limits.judge_usd, "The judge code's"
    if not caller.session:
        raise HTTPException(status_code=400, detail=f"Meta features on this server need an {SESSION_HEADER} header: "
                                                    "any stable id of your browser or client, up to "
                                                    f"{MAX_SESSION_CHARS} characters.")
    if len(caller.session) > MAX_SESSION_CHARS:
        raise HTTPException(status_code=400, detail=f"{SESSION_HEADER} must be at most {MAX_SESSION_CHARS} characters.")
    return f"session:{caller.session}", limits.session_usd, "This session's"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _refusal(detail: str) -> HTTPException:
    """429 that also says, in Retry-After, how long until the UTC day turns and every allowance resets."""
    now = _utc_now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return HTTPException(status_code=429, detail=detail + " Allowances reset at 00:00 UTC.",
                         headers={"Retry-After": str(max(1, math.ceil((midnight - now).total_seconds())))})


class _DayLedger(Ledger):
    """The Meta ledger, read for one UTC day's spend the way snapshot() reads its totals: no lock, no write."""

    def day_usd(self, day: str) -> float:
        """The day's settled costs plus the reservations still open (a crashed worker's stay counted)."""
        total = 0.0
        for entry in self._load()["entries"]:
            if str(entry.get("ts") or "").startswith(day):
                amount = entry.get("reserved_usd") if entry.get("status") == "reserved" else entry.get("settled_usd")
                total += amount or 0.0
        return _round_usd(total)


def spent_usd(env: Mapping[str, str] | None = None) -> float | None:
    """The Meta ledger's settled total, or None when it cannot be read (a charge then keeps its estimate)."""
    try:
        return Ledger.from_env(env).snapshot()["spent_usd"]
    except LLMError:
        return None


class SpendLimiter:
    """Admits Meta-calling requests against per-pool allowances kept here per UTC day, and the ledger's day total."""

    def __init__(self) -> None:
        self._day = ""
        self._usage: dict[str, float] = {}  # pool -> USD admitted on self._day: estimates, replaced by settled costs
        self._lock = threading.Lock()

    def admit(self, caller: Caller | None, *, estimate_usd: float,
              env: Mapping[str, str] | None = None) -> Admission | None:
        """Charge the request's worst case to its pool, or raise the HTTP refusal; None while limits are off."""
        env = os.environ if env is None else env
        if not limits_enabled(env):
            return None
        try:
            limits = configured_limits(env)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=f"Meta limits are misconfigured: {exc}") from None
        pool, allowance, whose = _pool(caller or Caller(), limits)
        day = _utc_now().strftime("%Y-%m-%d")
        try:
            day_usd = _DayLedger.from_env(env).day_usd(day)
        except LLMError:
            raise HTTPException(status_code=503, detail=_LEDGER_UNREADABLE) from None
        if day_usd + estimate_usd > limits.daily_usd + _TOLERANCE_USD:
            raise _refusal(f"This server's daily Meta limit is reached: ${day_usd:.2f} spent or reserved today + this "
                           f"request's worst case ${estimate_usd:.2f} would pass ${limits.daily_usd:.2f}.")
        with self._lock:
            if day != self._day:
                self._day, self._usage = day, {}
            used = self._usage.get(pool, 0.0)
            if used + estimate_usd > allowance + _TOLERANCE_USD:
                raise _refusal(f"{whose} daily Meta allowance is used up: ${used:.2f} admitted today + this request's "
                               f"worst case ${estimate_usd:.2f} would pass ${allowance:.2f}.")
            self._usage[pool] = _round_usd(used + estimate_usd)
        return Admission(day, pool, estimate_usd)

    def settle(self, admission: Admission | None, actual_usd: float) -> None:
        """Replace an admitted estimate by what the request settled for; an admission of another day is over."""
        if admission is None:
            return
        with self._lock:
            if admission.day != self._day:
                return
            used = self._usage.get(admission.pool, 0.0)
            self._usage[admission.pool] = _round_usd(max(0.0, used - admission.estimate_usd + max(0.0, actual_usd)))


limiter = SpendLimiter()
