"""The engines under comparison, each over the same ScoreMeasure objects and the same key.

local       the product's note-based bar analysis (score_analysis._inferred_harmony)
meta        harmony_meta.propose_harmony over the product's batches, notes only, no printed context
auto        the product's engine=auto rule: local first, Meta only for bars local left without chords
openweight  the same notes-only task through an explicitly built Baseten client with its own ledger

Nothing here reimplements an analyzer: the adapters build the objects the product
code expects and call it. Every model call goes through app.services.llm, so the
ledger records it; a SpendGuard stops a run before a call that could pass its limit.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace

from app.models.score_import import MAX_PITCH_NAMES
from app.services import harmony_meta
from app.services.llm import (
    BASETEN_PRICES, DEFAULT_LEDGER_PATH, PROVIDERS, BudgetExceeded, Ledger, LLMClient, LLMConfig, LLMConfigError,
    LLMConnectionError, LLMError, OpenAITransport, Transport,
)
from app.services.score_analysis import _inferred_harmony, _note_name
from app.services.score_assistance import MAX_ASSIST_CALLS, MAX_ASSIST_NOTES, _next_batch, _target
from app.services.score_pdf import NoteEvent as ReadNote, ScoreMeasure

ENGINES = ("local", "meta", "auto", "openweight")
OPENWEIGHT_MODEL = PROVIDERS["baseten"].model
OPENWEIGHT_EFFORT = "high"
OPENWEIGHT_LEDGER_PATH = DEFAULT_LEDGER_PATH.with_name("harmony_eval_baseten.json")
OPENWEIGHT_CAP_USD = 8.0
_SPEND_TOLERANCE_USD = 1e-9


@dataclass(frozen=True)
class BarResult:
    index: int
    chords: tuple[str, ...]
    confidence: str | None  # the engine's reported level; None when it proposed nothing
    source: str  # "local", or the provider that answered
    evidence: str = ""
    request_id: str | None = None
    error: str | None = None  # why the bar got no proposal, when a call or its input failed

    def to_dict(self) -> dict:
        return {**asdict(self), "chords": list(self.chords)}


@dataclass(frozen=True)
class CallRecord:
    provider: str
    model: str
    bars: int
    latency_ms: float
    cost_usd: float
    status: str  # "ok", or the LLMError kind / class name
    request_id: str | None = None
    attempts: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


class SpendLimit(Exception):
    """The run's own USD limit would be passed by the next call."""


class SpendGuard:
    """Stops a run before a call whose worst case could pass --max-usd.

    prior_usd is the spend already recorded for the same provider by earlier runs
    (the limit covers meta and auto together); spent() is this run's part of the
    ledger, so the ledger stays the record of what was actually settled.
    """

    def __init__(self, ledger: Ledger, max_usd: float, prior_usd: float = 0.0) -> None:
        self.ledger = ledger
        self.max_usd = max_usd
        self.prior_usd = prior_usd
        self.start_usd = ledger.snapshot()["spent_usd"]

    def spent(self) -> float:
        return round(self.ledger.snapshot()["spent_usd"] - self.start_usd, 8)

    def check(self) -> None:
        recorded = self.prior_usd + self.spent()
        if recorded + harmony_meta.MAX_REQUEST_USD > self.max_usd + _SPEND_TOLERANCE_USD:
            raise SpendLimit(f"recorded spend ${recorded:.4f} plus one call's worst case "
                             f"${harmony_meta.MAX_REQUEST_USD:.2f} would pass the limit ${self.max_usd:.2f}")


class CountingTransport:
    """Counts the requests a client sends, so a retry shows in the call record."""

    def __init__(self, inner: Transport) -> None:
        self.inner = inner
        self.attempts = 0

    def __call__(self, request: dict) -> tuple[dict, Mapping[str, str]]:
        self.attempts += 1
        return self.inner(request)


def measures_from_record(record: dict) -> list[ScoreMeasure]:
    """A dataset record's bars as the reader's ScoreMeasure objects, chords left out."""
    meter = (record["timeSignature"][0], record["timeSignature"][1])
    return [ScoreMeasure(index=bar["index"], page=1, system=1, number=bar["index"] + 1, time_signature=meter,
                         notes=[ReadNote(staff=note["staff"], midi=note["pitch"], spelling=note["spelling"],
                                         onset=note["onset"], duration=note["duration"], x=0.0, y=0.0)
                                for note in bar["notes"]])
            for bar in record["bars"]]


def hide_chords(measure: ScoreMeasure) -> ScoreMeasure:
    """A copy of a read measure without its printed chords, so no engine input carries them."""
    return replace(measure, chords=[], no_chord=False)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


class LocalEngine:
    name = "local"
    provider = "local"
    model = "harmony_analysis"

    def __init__(self) -> None:
        self.calls: list[CallRecord] = []

    def describe(self) -> dict:
        return {"provider": self.provider, "model": self.model}

    def analyze(self, measures: Sequence[ScoreMeasure], key: str | None) -> list[BarResult]:
        results = []
        for bar in measures:
            names = list(dict.fromkeys(_note_name(note.midi, note.spelling) for note in bar.notes))[:MAX_PITCH_NAMES]
            warnings: list[str] = []
            started = time.perf_counter()
            chords, _basis, confidence, evidence = _inferred_harmony(
                bar, key, names, " ".join(bar.warnings), f"Bar {bar.number}", warnings)
            self.calls.append(CallRecord(self.provider, self.model, 1, _ms(started), 0.0, "ok"))
            results.append(BarResult(bar.index, tuple(chords), confidence if chords else None, self.provider,
                                     evidence, error="too_many_changes" if warnings else None))
        return results


class LLMEngine:
    """propose_harmony over the product's batches (at most 8 bars and 512 notes per call)."""

    def __init__(self, name: str, client: LLMClient, *, transport: CountingTransport | None = None,
                 guard: SpendGuard | None = None) -> None:
        self.name = name
        self.client = client
        self.provider = client.config.provider
        self.model = client.config.model
        self.transport = transport
        self.guard = guard
        self.calls: list[CallRecord] = []

    def describe(self) -> dict:
        cfg = self.client.config
        return {"provider": cfg.provider, "model": cfg.model, "reasoning_effort": cfg.reasoning_effort,
                "timeout_s": harmony_meta.TIMEOUT_S, "max_completion_tokens": harmony_meta.MAX_COMPLETION_TOKENS,
                "max_request_usd": harmony_meta.MAX_REQUEST_USD, "ledger_cap_usd": self.client.ledger.cap_usd,
                "batch": {"max_measures": harmony_meta.MAX_MEASURES, "max_notes": MAX_ASSIST_NOTES}}

    def analyze(self, measures: Sequence[ScoreMeasure], key: str | None, *,
                max_calls: int | None = None) -> list[BarResult]:
        results: dict[int, BarResult] = {}
        targets: list[dict] = []
        for bar in measures:
            # The product sends no bar without notes and none past the note limit.
            if not bar.notes:
                results[bar.index] = BarResult(bar.index, (), None, self.provider, error="no_notes")
            elif len(bar.notes) > MAX_ASSIST_NOTES:
                results[bar.index] = BarResult(bar.index, (), None, self.provider, error="too_many_notes")
            else:
                targets.append(_target(bar.index, bar))
        calls = 0
        while targets and (max_calls is None or calls < max_calls):
            results.update(self._call(_next_batch(targets), key))
            calls += 1
        for target in targets:
            results[target["index"]] = BarResult(target["index"], (), None, self.provider, error="call_cap")
        return [results[bar.index] for bar in measures]

    def _call(self, batch: list[dict], key: str | None) -> dict[int, BarResult]:
        if self.guard is not None:
            self.guard.check()
        attempts_before = self.transport.attempts if self.transport else 0
        spent_before = self.client.ledger.snapshot()["spent_usd"]
        started = time.perf_counter()
        try:
            proposal = harmony_meta.propose_harmony(batch, key, context=None, client=self.client)
        except BudgetExceeded:
            raise  # the ledger cap: the run stops, nothing was sent
        except (LLMError, ValueError) as exc:
            kind = getattr(exc, "kind", None) or type(exc).__name__
            request_id = getattr(exc, "request_id", None)
            self.calls.append(CallRecord(
                self.provider, self.model, len(batch), _ms(started),
                round(self.client.ledger.snapshot()["spent_usd"] - spent_before, 8), kind, request_id,
                self._attempts(attempts_before, failed=True)))
            if isinstance(exc, LLMConnectionError):
                # An unreachable endpoint would fail every batch at its full reservation: the run stops
                raise
            return {target["index"]: BarResult(target["index"], (), None, self.provider, request_id=request_id,
                                               error=kind) for target in batch}
        self.calls.append(CallRecord(proposal.provider, proposal.model, len(batch), _ms(started),
                                     proposal.cost_usd, "ok", proposal.request_id, self._attempts(attempts_before)))
        return {measure.index: BarResult(measure.index, measure.chords, measure.confidence if measure.chords else None,
                                         proposal.provider, measure.evidence, proposal.request_id)
                for measure in proposal.measures}

    def _attempts(self, before: int, failed: bool = False) -> int:
        if self.transport is not None:
            return max(1, self.transport.attempts - before)
        return 1  # the shared Meta client never retries


class AutoEngine:
    """The product's engine=auto rule (score_assistance.enrich_local_harmony).

    Local analysis first; the bars it left without chords go to Meta in the same
    batches, at most MAX_ASSIST_CALLS calls per score. A Meta proposal keeps its
    confidence only when the reading was exact and warning-free, as the product does.
    """

    name = "auto"

    def __init__(self, local: LocalEngine, meta: LLMEngine) -> None:
        self.local = local
        self.meta = meta
        self.provider = meta.provider
        self.model = meta.model

    @property
    def calls(self) -> list[CallRecord]:
        return self.meta.calls

    def describe(self) -> dict:
        return {**self.meta.describe(), "max_calls_per_score": MAX_ASSIST_CALLS, "local": self.local.describe()}

    def analyze(self, measures: Sequence[ScoreMeasure], key: str | None) -> list[BarResult]:
        local = self.local.analyze(measures, key)
        pending = [bar for bar, result in zip(measures, local) if not result.chords]
        assisted = {result.index: result
                    for result in self.meta.analyze(pending, key, max_calls=MAX_ASSIST_CALLS)} if pending else {}
        merged = []
        for bar, result in zip(measures, local):
            proposal = assisted.get(bar.index)
            if result.chords or proposal is None:
                merged.append(result)
                continue
            uncertain = not bar.rhythm_exact or bool(bar.warnings)
            confidence = None if not proposal.chords else "low" if uncertain else proposal.confidence
            merged.append(replace(proposal, confidence=confidence))
        return merged


def meta_client() -> LLMClient:
    """The product's shared client, accepted only as Meta Standard at Standard prices."""
    return harmony_meta._standard_meta_client()


def _require_key(config: LLMConfig) -> None:
    """The client's own refusal, raised before a run that would otherwise log it once per batch."""
    if not config.api_key:
        raise LLMConfigError(f"{config.key_source} is not set, so provider {config.provider} cannot be called")


def openweight_client(transport: Transport | None = None,
                      env: Mapping[str, str] | None = None) -> tuple[LLMClient, CountingTransport]:
    """Muse Spark Open on Baseten at high effort, on its own ledger with its own cap."""
    import os

    env = os.environ if env is None else env
    # Baseten's own list price, not LLMConfig's Spark default, even while the two are equal
    config = LLMConfig(provider="baseten", base_url=PROVIDERS["baseten"].base_url, model=OPENWEIGHT_MODEL,
                       api_key=(env.get("BASETEN_API_KEY") or "").strip(), key_source="BASETEN_API_KEY",
                       reasoning_effort=OPENWEIGHT_EFFORT, price_input_per_m=BASETEN_PRICES[0],
                       price_cached_per_m=BASETEN_PRICES[1], price_output_per_m=BASETEN_PRICES[2],
                       price_source="baseten muse-spark-open-1026 list price")
    _require_key(config)
    counting = CountingTransport(transport if transport is not None else OpenAITransport(config))
    return LLMClient(config, Ledger(OPENWEIGHT_LEDGER_PATH, OPENWEIGHT_CAP_USD), counting), counting


def build_engine(name: str, *, max_usd: float | None = None, prior_usd: float = 0.0,
                 transport: Transport | None = None) -> tuple[LocalEngine | LLMEngine | AutoEngine, Ledger | None]:
    """The engine and the ledger its spend lands in (None for local)."""
    if name == "local":
        return LocalEngine(), None
    if name == "openweight":
        client, counting = openweight_client(transport)
    elif name in ("meta", "auto"):
        client, counting = meta_client(), None
    else:
        raise ValueError(f"unknown engine {name!r}; expected one of {', '.join(ENGINES)}")
    _require_key(client.config)
    guard = SpendGuard(client.ledger, max_usd, prior_usd) if max_usd is not None else None
    llm = LLMEngine("meta" if name == "auto" else name, client, transport=counting, guard=guard)
    return (AutoEngine(LocalEngine(), llm) if name == "auto" else llm), client.ledger
