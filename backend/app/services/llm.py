"""OpenAI-compatible LLM client for the Meta Model API and partner endpoints.

chat_json() sends exactly one strict-JSON Chat Completions request (SDK retries
off) and returns the checked object or raises a typed LLMError; it never returns
a fallback that looks like a model answer. Each request first reserves its
worst-case cost in a JSON ledger and is refused before any network I/O when
spent + outstanding reservations + this reservation would pass the cap; the
ledger then records the request id, token usage and settled cost.

Environment (names in deploy/env.example):
  LLM_PROVIDER          meta (default) | baseten | fireworks | ollama | custom
  LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
                        override the provider defaults; custom needs all three.
                        meta, baseten and fireworks take a base URL only on their
                        own https host, ollama and custom any host but those three,
                        so no key reaches another provider. The Meta key is read
                        only from MODEL_API_KEY, so the meta provider ignores
                        LLM_API_KEY.
  LLM_TIMEOUT_S         per-request timeout in seconds (default 60)
  LLM_REASONING_EFFORT  minimal | low | medium | high, sent as given; none = not sent; unset or
                        empty = the provider default (low; ollama and custom: not sent)
  LLM_PRICE_INPUT_PER_M / LLM_PRICE_CACHED_PER_M / LLM_PRICE_OUTPUT_PER_M
                        USD per 1M tokens; unknown models use the Spark prices,
                        and ollama is free only on a loopback host
  THEARTIST_META_BUDGET_USD   spend cap in USD (default 25)
  THEARTIST_META_LEDGER       ledger path (default backend/.ledger/meta_ledger.json)
"""

from __future__ import annotations

import contextlib
import copy
import fcntl
import ipaddress
import json
import logging
import math
import os
import re
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import openai

log = logging.getLogger(__name__)


# --- Errors ---

class LLMError(Exception):
    """Base class for every failure raised by this module."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id

    def __str__(self) -> str:
        text = super().__str__()
        return f"{text} (request_id {self.request_id})" if self.request_id else text


class LLMConfigError(LLMError):
    """Invalid or incomplete provider configuration."""


class LLMSchemaError(LLMError, ValueError):
    """A response schema that strict structured output cannot express."""


class LedgerError(LLMError):
    """The spend ledger cannot be read or written, so nothing is sent."""


class BudgetExceeded(LLMError):
    """The request's worst-case cost would take the ledger past its cap."""

    def __init__(self, message: str, *, spent_usd: float, outstanding_usd: float,
                 request_usd: float, cap_usd: float) -> None:
        super().__init__(message)
        self.spent_usd = spent_usd
        self.outstanding_usd = outstanding_usd
        self.request_usd = request_usd
        self.cap_usd = cap_usd


class LLMTimeout(LLMError):
    """No response within the timeout; settled at the full reservation."""


class LLMConnectionError(LLMError):
    """The endpoint could not be reached; settled at the full reservation."""


class LLMResponseError(LLMError):
    """An HTTP error status, or a reply that is not the requested JSON object.

    kind: http | length | content_filter | refusal | finish_reason | empty |
          invalid_json | schema_mismatch | bad_response
    """

    def __init__(self, message: str, *, kind: str, request_id: str | None = None,
                 status_code: int | None = None) -> None:
        super().__init__(message, request_id=request_id)
        self.kind = kind
        self.status_code = status_code


# --- Provider configuration ---

# USD per 1M tokens (input, cached input, output) for Muse Spark 1.x Standard
SPARK_PRICES = (1.25, 0.15, 4.25)
_SPARK_STANDARD = re.compile(r"muse-spark-1(\.\d+)*")
PRICE_ENV = ("LLM_PRICE_INPUT_PER_M", "LLM_PRICE_CACHED_PER_M", "LLM_PRICE_OUTPUT_PER_M")
REASONING_EFFORTS = ("minimal", "low", "medium", "high")
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_REASONING_EFFORT = "low"
OLLAMA_KEY = "ollama"  # ollama ignores the key, but the SDK needs one


@dataclass(frozen=True)
class _Provider:
    base_url: str
    model: str
    key_env: str | None  # None: the endpoint takes a fixed placeholder key


PROVIDERS: dict[str, _Provider] = {
    "meta": _Provider("https://api.meta.ai/v1", "muse-spark-1.3", "MODEL_API_KEY"),
    "baseten": _Provider("https://inference.baseten.co/v1", "meta-models/muse-spark-open-1026",
                         "BASETEN_API_KEY"),
    "fireworks": _Provider("https://api.fireworks.ai/inference/v1",
                           "accounts/fireworks/models/muse-glimmer-30b", "FIREWORKS_API_KEY"),
    # Offline fallback stays on Meta open weights: the product runs Meta models only.
    "ollama": _Provider("http://localhost:11434/v1", "llama3.2:3b", None),
}


def _round_usd(amount: float) -> float:
    """Every USD amount (costs, reservations and ledger totals) is kept to 8 decimal places."""
    return round(amount, 8)


def _env_str(env: Mapping[str, str], name: str) -> str:
    """The variable's value without surrounding whitespace; empty when unset."""
    return (env.get(name) or "").strip()


def _env_float(env: Mapping[str, str], name: str) -> float | None:
    raw = _env_str(env, name)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise LLMConfigError(f"{name} must be a number, got {raw!r}") from None


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _is_loopback(host: str) -> bool:
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# The hosted endpoints by host, each reached only under its own provider name
_PROVIDER_BY_HOST = {_host(spec.base_url): name for name, spec in PROVIDERS.items() if spec.key_env}


def _check_endpoint(provider: str, base_url: str) -> None:
    """Keep every key on the endpoint it was meant for, whichever variable it came from.

    meta, baseten and fireworks take only their own https host; ollama and custom take
    any host but those three. So a copied template that still carries the Meta URL
    cannot send a partner key, or LLM_API_KEY, to Meta under another provider's name.
    """
    host, scheme = _host(base_url), urlsplit(base_url).scheme
    shown = f"{scheme}://{host}" if host else "a URL with no host"  # never a path or credentials
    owner = _PROVIDER_BY_HOST.get(host)
    if provider in _PROVIDER_BY_HOST.values():  # a hosted provider: its own host, over https only
        if owner == provider and scheme == "https":
            return
        if owner is None:
            hint = ", or use LLM_PROVIDER=custom with LLM_API_KEY for another endpoint"
        elif owner != provider:
            hint = f", or set LLM_PROVIDER={owner}"
        else:
            hint = ""  # its own host, but over plain http
        raise LLMConfigError(f"LLM_BASE_URL is {shown}, not the {provider} endpoint "
                             f"{PROVIDERS[provider].base_url}: clear LLM_BASE_URL and LLM_MODEL to use the "
                             f"{provider} defaults{hint}")
    if owner is not None:  # any other provider: any host but the hosted ones
        hint = ", or clear LLM_BASE_URL and LLM_MODEL for the local defaults" if provider == "ollama" else ""
        raise LLMConfigError(f"LLM_BASE_URL {shown} is the {owner} endpoint, reached only with "
                             f"LLM_PROVIDER={owner}{hint}")


def _provider_key(env: Mapping[str, str], provider: str, key_override: str) -> tuple[str, str]:
    """The API key of a listed provider, and where it came from (safe to show).

    For meta, LLM_API_KEY is ignored (a warning is logged when it is set): the Meta key is
    read only from MODEL_API_KEY.
    """
    if provider == "meta":
        if key_override:
            log.warning("LLM_API_KEY is ignored for provider meta: the Meta key is read "
                        "only from MODEL_API_KEY")
        return _env_str(env, "MODEL_API_KEY"), "MODEL_API_KEY"
    if key_override:
        return key_override, "LLM_API_KEY"
    key_env = PROVIDERS[provider].key_env
    if key_env:
        return _env_str(env, key_env), key_env
    return OLLAMA_KEY, "placeholder"


def _token_prices(env: Mapping[str, str], provider: str, base_url: str,
                  model: str) -> tuple[tuple[float, ...], str]:
    """USD per 1M (input, cached input, output) tokens, and where those prices came from.

    Each LLM_PRICE_*_PER_M variable that is set replaces its own price.
    """
    if provider == "ollama" and _is_loopback(_host(base_url)):
        prices, price_source = (0.0, 0.0, 0.0), "ollama (local)"
    elif _SPARK_STANDARD.fullmatch(model):
        prices, price_source = SPARK_PRICES, "muse-spark-1.x Standard"
    else:
        prices, price_source = SPARK_PRICES, "unknown model price, Spark Standard assumed"
    overrides = [_env_float(env, name) for name in PRICE_ENV]
    if any(value is not None for value in overrides):
        prices = tuple(o if o is not None else p for o, p in zip(overrides, prices))
        price_source = "LLM_PRICE_*_PER_M"
    return prices, price_source


def _reasoning_effort(provider: str, raw: str) -> str | None:
    """The reasoning_effort to send for LLM_REASONING_EFFORT=raw; None leaves it out of the request."""
    effort = raw.lower()
    if not effort:
        # Unset or empty: the provider default. A local model may have no reasoning mode and a
        # custom endpoint may reject the parameter, so those two get it only when it is set
        return None if provider in ("ollama", "custom") else DEFAULT_REASONING_EFFORT
    if effort == "none":
        return None
    return effort  # LLMConfig checks it against REASONING_EFFORTS


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = field(default="", repr=False)  # never logged, printed or stored
    key_source: str = ""  # where the key came from, safe to show
    timeout_s: float = DEFAULT_TIMEOUT_S
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT
    price_input_per_m: float = SPARK_PRICES[0]
    price_cached_per_m: float = SPARK_PRICES[1]
    price_output_per_m: float = SPARK_PRICES[2]
    price_source: str = "muse-spark-1.x Standard"

    def __post_init__(self) -> None:
        if "contributor" in self.model.lower():
            raise LLMConfigError(
                f"model {self.model!r} is a Contributor-mode id, whose prompts may be used to "
                "train Meta models; use a Standard id such as muse-spark-1.3")
        if not self.base_url or not self.model:
            raise LLMConfigError("base_url and model must both be set")
        _check_endpoint(self.provider, self.base_url)
        if not (math.isfinite(self.timeout_s) and self.timeout_s > 0):
            raise LLMConfigError(f"timeout must be a positive number of seconds, got {self.timeout_s!r}")
        if self.reasoning_effort is not None and self.reasoning_effort not in REASONING_EFFORTS:
            raise LLMConfigError(f"reasoning effort must be one of {', '.join(REASONING_EFFORTS)}, none "
                                 f"(not sent) or empty (the provider default), got {self.reasoning_effort!r}")
        for name in ("price_input_per_m", "price_cached_per_m", "price_output_per_m"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0):
                raise LLMConfigError(f"{name} must be a non-negative number, got {value!r}")

    def cost_usd(self, *, prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> float:
        """(prompt - cached) x input + cached x cached price + completion x output."""
        total = ((prompt_tokens - cached_tokens) * self.price_input_per_m
                 + cached_tokens * self.price_cached_per_m
                 + completion_tokens * self.price_output_per_m)
        return _round_usd(total / 1_000_000)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMConfig:
        env = os.environ if env is None else env
        provider = _env_str(env, "LLM_PROVIDER").lower() or "meta"
        base_url, model = _env_str(env, "LLM_BASE_URL"), _env_str(env, "LLM_MODEL")
        key_override = _env_str(env, "LLM_API_KEY")
        if provider == "custom":
            missing = [name for name, value in (("LLM_BASE_URL", base_url), ("LLM_MODEL", model),
                                                ("LLM_API_KEY", key_override)) if not value]
            if missing:
                raise LLMConfigError(f"LLM_PROVIDER=custom needs {', '.join(missing)}")
            api_key, key_source = key_override, "LLM_API_KEY"
        elif provider in PROVIDERS:
            spec = PROVIDERS[provider]
            api_key, key_source = _provider_key(env, provider, key_override)
            # __post_init__ then checks the host, whichever variable the key came from
            base_url, model = base_url or spec.base_url, model or spec.model
        else:
            raise LLMConfigError(f"unknown LLM_PROVIDER {provider!r}; expected one of "
                                 f"{', '.join([*PROVIDERS, 'custom'])}")

        prices, price_source = _token_prices(env, provider, base_url, model)
        timeout = _env_float(env, "LLM_TIMEOUT_S")
        effort = _reasoning_effort(provider, _env_str(env, "LLM_REASONING_EFFORT"))
        return cls(
            provider=provider, base_url=base_url, model=model, api_key=api_key,
            key_source=key_source,
            timeout_s=DEFAULT_TIMEOUT_S if timeout is None else timeout,
            reasoning_effort=effort,
            price_input_per_m=prices[0], price_cached_per_m=prices[1], price_output_per_m=prices[2],
            price_source=price_source,
        )


# --- Strict structured-output schemas ---

_UNSUPPORTED_KEYWORDS = ("oneOf", "anyOf", "allOf", "$ref", "$defs", "definitions")


def _is_object_schema(node: Mapping[str, Any]) -> bool:
    types = node.get("type")
    return types == "object" or (isinstance(types, list) and "object" in types) or "properties" in node


def strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of `schema` in the form strict structured output accepts.

    Every object gets "additionalProperties": false and lists all of its
    properties in "required". The root must be a plain object; oneOf, anyOf,
    allOf and $ref (so also recursion) raise LLMSchemaError.
    """
    out = copy.deepcopy(dict(schema))
    if out.get("type") != "object":
        raise LLMSchemaError('the schema root must be a plain {"type": "object"}')
    _make_strict(out, "$")
    return out


def _make_strict(node: dict[str, Any], path: str) -> None:
    for keyword in _UNSUPPORTED_KEYWORDS:
        if keyword in node:
            raise LLMSchemaError(f"{path}: {keyword} is not supported by strict structured output")
    if _is_object_schema(node):
        props = node.setdefault("properties", {})
        if node.get("additionalProperties", False) is not False:
            raise LLMSchemaError(f"{path}: additionalProperties must be false in strict mode")
        unknown = set(node.get("required", [])) - set(props)
        if unknown:
            raise LLMSchemaError(f"{path}: required names unknown properties {sorted(unknown)}")
        node["additionalProperties"] = False
        node["required"] = list(props)
        for key, child in props.items():
            if not isinstance(child, dict):
                raise LLMSchemaError(f"{path}.{key}: property schema must be an object")
            _make_strict(child, f"{path}.{key}")
    items = node.get("items")
    if items is not None:
        if not isinstance(items, dict):
            raise LLMSchemaError(f"{path}: items must be a single schema")
        _make_strict(items, f"{path}[]")


_JSON_TYPES: dict[str, Callable[[Any], bool]] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _is_json_type(value: Any, name: str) -> bool:
    """Whether `value` has the JSON Schema type `name`; a type name it does not know never matches."""
    check = _JSON_TYPES.get(name)
    return check is not None and check(value)


def _json_type(value: Any) -> str:
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _is_json_type(value, name):
            return name
    return type(value).__name__


def schema_errors(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Check a parsed reply against the schema keywords strict mode uses.

    Covers type, enum, const, properties / required / additionalProperties,
    items and the min/max bounds; returns readable errors, empty when it fits.
    """
    types = schema.get("type")
    if types is not None:
        allowed = [types] if isinstance(types, str) else list(types)
        if not any(_is_json_type(value, t) for t in allowed):
            return [f"{path}: expected {' or '.join(allowed)}, got {_json_type(value)}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of the allowed values")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{path}: missing key {key!r}" for key in schema.get("required", []) if key not in value]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}: unexpected key {key!r}" for key in value if key not in props]
        for key, child in props.items():
            if key in value:
                errors += schema_errors(value[key], child, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors += schema_errors(item, schema["items"], f"{path}[{index}]")
    if _is_json_type(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is above the maximum {schema['maximum']}")
    return errors


# --- Spend ledger ---

DEFAULT_BUDGET_USD = 25.0
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[2] / ".ledger" / "meta_ledger.json"
WARN_FRACTION = 0.8
_CAP_TOLERANCE_USD = 1e-9  # float slack, so a reservation that exactly fills the cap still fits
_warned_ledgers: set[str] = set()  # ledgers that already logged the 80 % warning in this process
_warned_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _outstanding(state: Mapping[str, Any]) -> float:
    return _round_usd(sum(e.get("reserved_usd") or 0.0 for e in state["entries"]
                          if e.get("status") == "reserved"))


class Ledger:
    """JSON spend ledger shared by every worker that points at the same file.

    Each update holds a thread lock and an exclusive flock on a sidecar
    ".lock" file, re-reads the file and replaces it atomically (temp file +
    os.replace), so concurrent processes never lose an entry or a reservation.
    A reservation left open by a crashed worker stays counted (safe over-count).
    """

    def __init__(self, path: str | os.PathLike[str] | None = None, cap_usd: float | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path is not None else DEFAULT_LEDGER_PATH
        self.cap_usd = DEFAULT_BUDGET_USD if cap_usd is None else float(cap_usd)
        if not (math.isfinite(self.cap_usd) and self.cap_usd >= 0):
            raise LLMConfigError(f"the budget cap must be a non-negative number, got {cap_usd!r}")
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Ledger:
        env = os.environ if env is None else env
        path = _env_str(env, "THEARTIST_META_LEDGER") or None
        return cls(path, _env_float(env, "THEARTIST_META_BUDGET_USD"))

    def snapshot(self) -> dict[str, Any]:
        """Current totals, read without locking or creating anything (writes replace the file whole)."""
        state = self._load()
        return {"path": str(self.path), "cap_usd": self.cap_usd, "spent_usd": state["spent_usd"],
                "outstanding_usd": _outstanding(state), "entries": len(state["entries"])}

    def reserve(self, *, label: str, provider: str, model: str, reserved_usd: float) -> str:
        """Record a worst-case reservation and return its id, or raise BudgetExceeded."""
        reserved_usd = _round_usd(reserved_usd)
        with self._transaction() as state:
            spent, outstanding = state["spent_usd"], _outstanding(state)
            if spent + outstanding + reserved_usd > self.cap_usd + _CAP_TOLERANCE_USD:
                raise BudgetExceeded(
                    f"LLM budget cap reached: spent ${spent:.4f} + outstanding ${outstanding:.4f} "
                    f"+ this request ${reserved_usd:.4f} > cap ${self.cap_usd:.2f} (ledger {self.path})",
                    spent_usd=spent, outstanding_usd=outstanding, request_usd=reserved_usd,
                    cap_usd=self.cap_usd)
            entry_id = uuid.uuid4().hex
            state["entries"].append({
                "id": entry_id, "ts": _utc_now(), "label": label, "provider": provider, "model": model,
                "reserved_usd": reserved_usd, "settled_usd": None, "status": "reserved",
                "request_id": None, "response_id": None, "usage": None, "latency_ms": None, "error": None,
            })
        return entry_id

    def settle(self, entry_id: str, *, settled_usd: float, status: str, request_id: str | None = None,
               response_id: str | None = None, usage: Mapping[str, int] | None = None,
               latency_ms: int | None = None, error: str | None = None) -> float:
        """Close a reservation at its settled cost; returns the new spent total."""
        if status not in ("settled", "failed"):
            raise ValueError(f"unknown settlement status {status!r}")
        settled_usd = _round_usd(settled_usd)
        with self._transaction() as state:
            entry = next((e for e in reversed(state["entries"]) if e.get("id") == entry_id), None)
            if entry is None or entry.get("status") != "reserved":
                raise LedgerError(f"no open reservation {entry_id} in {self.path}")
            entry.update(settled_usd=settled_usd, status=status, request_id=request_id,
                         response_id=response_id, usage=dict(usage) if usage else None,
                         latency_ms=latency_ms, error=error)
            state["spent_usd"] = spent = _round_usd(state["spent_usd"] + settled_usd)
        self._warn_if_high(spent)
        return spent

    def _warn_if_high(self, spent: float) -> None:
        if self.cap_usd <= 0 or spent < WARN_FRACTION * self.cap_usd:
            return
        with _warned_lock:
            if str(self.path) in _warned_ledgers:
                return
            _warned_ledgers.add(str(self.path))
        log.warning("LLM spend $%.4f has crossed 80%% of the $%.2f cap; requests are refused at "
                    "the cap (ledger %s)", spent, self.cap_usd, self.path)

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                lock_file = open(self._lock_path, "a")
            except OSError as exc:
                raise LedgerError(f"cannot open the ledger lock {self._lock_path}: {exc}") from exc
            with lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # released when the file closes
                except OSError as exc:  # e.g. ENOLCK on a network volume without lock support
                    raise LedgerError(f"cannot lock the ledger {self._lock_path}: {exc}") from exc
                state = self._load()
                yield state
                self._write(state)

    def _load(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"cap_usd": self.cap_usd, "spent_usd": 0.0, "entries": []}
        except OSError as exc:
            raise LedgerError(f"cannot read the ledger {self.path}: {exc}") from exc
        try:
            state = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"the ledger {self.path} is not valid JSON; fix or move it before "
                              "spending more") from exc
        if not isinstance(state, dict) or not isinstance(state.get("entries"), list):
            raise LedgerError(f"the ledger {self.path} has no entries list")
        if not isinstance(state.get("spent_usd"), (int, float)):
            state["spent_usd"] = _round_usd(sum(e.get("settled_usd") or 0.0 for e in state["entries"]))
        return state

    def _write(self, state: dict[str, Any]) -> None:
        state["cap_usd"] = self.cap_usd
        try:
            fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        except OSError as exc:  # e.g. a read-only or full volume
            raise LedgerError(f"cannot write the ledger {self.path}: {exc}") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=1)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException as exc:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            if isinstance(exc, OSError):
                raise LedgerError(f"cannot write the ledger {self.path}: {exc}") from exc
            raise


# --- Client ---

# (request kwargs) -> (response dict, response headers); tests pass a fake
Transport = Callable[[dict[str, Any]], tuple[dict[str, Any], Mapping[str, str]]]
CHARS_PER_TOKEN = 3  # conservative; English chat text averages nearer 4 characters per token
_SCHEMA_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SCHEMA_ERRORS_SHOWN = 5  # a schema_mismatch message lists at most this many problems


@dataclass(frozen=True)
class PreparedRequest:
    body: dict[str, Any]  # Chat Completions JSON body: no key, no headers
    timeout_s: float
    schema: dict[str, Any]  # strict form, also used to check the reply
    input_tokens_estimate: int
    reserve_usd: float


@dataclass(frozen=True)
class LLMResult:
    data: dict[str, Any]
    text: str
    provider: str
    model: str
    request_id: str | None
    response_id: str | None
    usage: dict[str, int]  # prompt_tokens, cached_tokens, completion_tokens, reasoning_tokens
    cost_usd: float
    latency_ms: int
    label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenAITransport:
    """Default transport: one request through the openai SDK with retries off.

    with_raw_response keeps the HTTP headers, so the x-request-id is captured, also for a
    success status whose body is not a JSON chat completion (raised as bad_response).
    """

    def __init__(self, config: LLMConfig, http_client: Any | None = None) -> None:
        self._client = openai.OpenAI(api_key=config.api_key, base_url=config.base_url,
                                     timeout=config.timeout_s, max_retries=0, http_client=http_client)
        self._where = f"{config.provider} ({config.model})"

    def __call__(self, request: dict[str, Any]) -> tuple[dict[str, Any], Mapping[str, str]]:
        raw = self._client.chat.completions.with_raw_response.create(**request)
        try:
            parsed = raw.parse()  # the body text, not a model, when the body is not JSON
            completion = parsed.to_dict() if isinstance(parsed, openai.BaseModel) else None
        except Exception:  # e.g. a JSON content type over a body that is not JSON
            completion = None
        if completion is None:
            # An HTML page from a proxy, or a base URL missing /v1. Raised outside the handler, so the
            # parser's exception, which holds the body, is not chained
            content_type = raw.headers.get("content-type", "").split(";")[0].strip()[:80] or "not set"
            raise LLMResponseError(
                f"HTTP {raw.status_code} from {self._where} is not a JSON chat completion (content type "
                f"{content_type}); check that LLM_BASE_URL is the API root, usually ending in /v1",
                kind="bad_response", request_id=raw.headers.get("x-request-id"), status_code=raw.status_code)
        return completion, dict(raw.headers)


def _is_positive_int(value: Any) -> bool:
    """An int of at least 1; a bool is not a count."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _has_media(messages: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a message's content is a list of parts with a part that is not text (an image, a file)."""
    return any(
        isinstance(message.get("content"), list)
        and any(not isinstance(part, dict) or part.get("type") != "text" for part in message["content"])
        for message in messages)


def _estimated_text_tokens(messages: list[dict[str, Any]], schema: dict[str, Any]) -> int:
    """Input tokens of a text-only request, estimated from the characters of its messages and schema."""
    chars = len(json.dumps(messages, ensure_ascii=False)) + len(json.dumps(schema, ensure_ascii=False))
    return math.ceil(chars / CHARS_PER_TOKEN)


def _token_count(mapping: Any, key: str) -> int | None:
    """mapping[key] as an int when it is a non-negative number (not a bool), else None."""
    value = mapping.get(key) if isinstance(mapping, dict) else None
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def _api_message(exc: openai.APIStatusError) -> str:
    """The provider's error message from the response body, else the SDK's own message."""
    body = exc.body
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict) and inner.get("message"):
            return str(inner["message"])
    return exc.message


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


class LLMClient:
    """Strict-JSON chat client with a hard spend cap. Thread-safe; share one per process."""

    def __init__(self, config: LLMConfig | None = None, ledger: Ledger | None = None,
                 transport: Transport | None = None) -> None:
        self.config = config if config is not None else LLMConfig.from_env()
        self.ledger = ledger if ledger is not None else Ledger.from_env()
        self._transport = transport
        self._transport_lock = threading.Lock()

    def prepare(self, messages: Sequence[Mapping[str, Any]], schema: Mapping[str, Any], *, name: str,
                max_completion_tokens: int = 2048, timeout_s: float | None = None,
                input_token_upper_bound: int | None = None,
                max_request_usd: float | None = None) -> PreparedRequest:
        """Build the request and reservation without sending anything.

        Text-only input is estimated from its character count. Media requires a caller-supplied
        bound for ALL input tokens, including extracted text, images, and schema;
        base64 character length cannot bound a document's tokenized representation.
        A model's full context window is a conservative bound for accepted requests.
        """
        if not _SCHEMA_NAME.fullmatch(name):
            raise LLMSchemaError(f"schema name {name!r} must be 1-64 letters, digits, _ or -")
        if not _is_positive_int(max_completion_tokens):
            raise ValueError(f"max_completion_tokens must be a positive integer, got {max_completion_tokens!r}")
        if not messages:
            raise ValueError("messages must not be empty")
        timeout = self.config.timeout_s if timeout_s is None else float(timeout_s)
        if not (math.isfinite(timeout) and timeout > 0):
            raise ValueError(f"timeout_s must be a positive number, got {timeout_s!r}")
        strict = strict_schema(schema)
        msgs = [dict(m) for m in messages]
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": msgs,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": name, "strict": True, "schema": strict}},
            "max_completion_tokens": max_completion_tokens,
        }
        if self.config.reasoning_effort:
            body["reasoning_effort"] = self.config.reasoning_effort
        has_media = _has_media(msgs)
        if input_token_upper_bound is not None:
            if not _is_positive_int(input_token_upper_bound):
                raise ValueError("input_token_upper_bound must be a positive integer")
            input_tokens = input_token_upper_bound
        elif has_media:
            raise ValueError("media input requires an explicit input_token_upper_bound")
        else:
            input_tokens = _estimated_text_tokens(msgs, strict)
        # Worst case: every input token uncached, and the whole completion budget spent
        # (reasoning tokens bill as output and count toward max_completion_tokens)
        reserve = _round_usd((input_tokens * self.config.price_input_per_m
                              + max_completion_tokens * self.config.price_output_per_m) / 1_000_000)
        if max_request_usd is not None:
            if isinstance(max_request_usd, bool) or not math.isfinite(max_request_usd) or max_request_usd <= 0:
                raise ValueError("max_request_usd must be a positive finite number")
            if reserve > max_request_usd:
                raise BudgetExceeded(
                    f"request reservation ${reserve:.6f} exceeds the per-request cap ${max_request_usd:.6f}",
                    spent_usd=0.0, outstanding_usd=0.0, request_usd=reserve, cap_usd=max_request_usd)
        return PreparedRequest(body, timeout, strict, input_tokens, reserve)

    def chat_json(self, messages: Sequence[Mapping[str, Any]], schema: Mapping[str, Any], *, name: str,
                  label: str, max_completion_tokens: int = 2048, timeout_s: float | None = None,
                  input_token_upper_bound: int | None = None,
                  max_request_usd: float | None = None) -> LLMResult:
        """Send one strict-JSON request; return the checked object or raise an LLMError."""
        cfg = self.config
        prepared = self.prepare(messages, schema, name=name, max_completion_tokens=max_completion_tokens,
                                timeout_s=timeout_s, input_token_upper_bound=input_token_upper_bound,
                                max_request_usd=max_request_usd)
        if not cfg.api_key:
            raise LLMConfigError(f"{cfg.key_source} is not set, so provider {cfg.provider} cannot be called")
        transport = self._get_transport()
        try:
            entry_id = self.ledger.reserve(label=label, provider=cfg.provider, model=cfg.model,
                                           reserved_usd=prepared.reserve_usd)
        except BudgetExceeded as exc:
            log.warning("llm refused provider=%s model=%s label=%s: %s", cfg.provider, cfg.model, label, exc)
            raise

        started = time.perf_counter()
        error: LLMError | None = None
        try:
            response, headers = transport({**prepared.body, "timeout": prepared.timeout_s})
        except Exception as exc:
            error, settle_usd = self._transport_failure(exc, prepared)
        except BaseException as exc:
            self._close(entry_id, label, prepared.reserve_usd, "failed", _elapsed_ms(started), error=exc)
            raise  # KeyboardInterrupt / SystemExit: settled, now re-raised unchanged
        latency_ms = _elapsed_ms(started)
        if error is not None:
            # Settled and raised outside the handler, so the raw exception is neither the __cause__ nor
            # the __context__ of what propagates: its text and the SDK's request can carry the key
            self._close(entry_id, label, settle_usd, "failed", latency_ms, request_id=error.request_id,
                        error=error)
            raise error

        # Every failure from here on settles too, at the actual usage once it is known (else at the
        # reservation), and is raised outside the handler as an LLMError with nothing chained
        request_id: str | None = None
        response_id: str | None = None
        usage: dict[str, int] | None = None
        cost = prepared.reserve_usd
        try:
            headers = {str(k).lower(): str(v) for k, v in dict(headers or {}).items()}
            request_id = headers.get("x-request-id")
            response_id = response.get("id") if isinstance(response, dict) else None
            usage, cost = self._usage_and_cost(response, prepared)
            data, text, model = self._parse(response, prepared, request_id)
        except LLMResponseError as exc:
            error = exc
        except Exception as exc:  # e.g. a usage count too large to price
            error = LLMResponseError(f"cannot read the reply from {cfg.provider} ({cfg.model}): "
                                     f"{type(exc).__name__}: {self._scrub(str(exc))}",
                                     kind="bad_response", request_id=request_id)
        except BaseException as exc:
            self._close(entry_id, label, cost, "failed", latency_ms, request_id=request_id,
                        response_id=response_id, usage=usage, error=exc)
            raise  # KeyboardInterrupt / SystemExit: settled, now re-raised unchanged
        else:
            self._close(entry_id, label, cost, "settled", latency_ms, request_id=request_id,
                        response_id=response_id, usage=usage)
            return LLMResult(
                data=data, text=text, provider=cfg.provider, model=model, request_id=request_id,
                response_id=response_id, usage=usage or {}, cost_usd=cost, latency_ms=latency_ms, label=label)
        self._close(entry_id, label, cost, "failed", latency_ms, request_id=request_id,
                    response_id=response_id, usage=usage, error=error)
        raise error

    def _get_transport(self) -> Transport:
        with self._transport_lock:
            if self._transport is None:
                self._transport = OpenAITransport(self.config)
            return self._transport

    def _usage_and_cost(self, response: Any, prepared: PreparedRequest) -> tuple[dict[str, int] | None, float]:
        usage = response.get("usage") if isinstance(response, dict) else None
        prompt, completion = _token_count(usage, "prompt_tokens"), _token_count(usage, "completion_tokens")
        if prompt is None or completion is None:
            return None, prepared.reserve_usd  # usage unknown: keep the safe over-count
        cached = min(_token_count(usage.get("prompt_tokens_details"), "cached_tokens") or 0, prompt)
        reasoning = _token_count(usage.get("completion_tokens_details"), "reasoning_tokens") or 0
        # Reasoning tokens bill as output and are normally part of completion_tokens; a
        # provider reporting more reasoning than completion tokens counts them separately.
        billed_output = completion + reasoning if reasoning > completion else completion
        cost = self.config.cost_usd(prompt_tokens=prompt, cached_tokens=cached, completion_tokens=billed_output)
        return {"prompt_tokens": prompt, "cached_tokens": cached, "completion_tokens": completion,
                "reasoning_tokens": reasoning}, cost

    def _parse(self, response: Any, prepared: PreparedRequest,
               request_id: str | None) -> tuple[dict[str, Any], str, str]:
        def fail(kind: str, message: str) -> LLMResponseError:
            return LLMResponseError(message, kind=kind, request_id=request_id)

        choices = response.get("choices") if isinstance(response, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise fail("bad_response", "the response has no choices")
        choice = choices[0]
        finish = choice.get("finish_reason")
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        if finish == "length":
            raise fail("length", f"the output hit max_completion_tokens="
                                 f"{prepared.body['max_completion_tokens']} (reasoning tokens count toward it)")
        if finish == "content_filter":
            raise fail("content_filter", "the provider's content filter stopped the output")
        if message.get("refusal"):
            raise fail("refusal", f"the model refused: {str(message['refusal'])[:200]}")
        if finish not in (None, "stop"):
            raise fail("finish_reason", f"unexpected finish_reason {finish!r}")
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise fail("empty", "the response has no message content")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            problem = f"is not JSON ({exc.msg} at char {exc.pos})"
        except ValueError as exc:  # e.g. an integer past Python's int digit limit
            problem = f"cannot be parsed as JSON ({self._scrub(str(exc))})"
        else:
            problem = None
        if problem is not None:
            # raised outside the handler, so the decoder's exception (it holds the reply) is not chained
            raise fail("invalid_json", f"the message content {problem}")
        errors = schema_errors(data, prepared.schema)
        if errors:
            shown, hidden = errors[:_SCHEMA_ERRORS_SHOWN], len(errors) - _SCHEMA_ERRORS_SHOWN
            more = f" (+{hidden} more)" if hidden > 0 else ""
            raise fail("schema_mismatch", "the reply does not match the schema: " + "; ".join(shown) + more)
        model = response.get("model")
        return data, text, model if isinstance(model, str) and model else self.config.model

    def _transport_failure(self, exc: Exception, prepared: PreparedRequest) -> tuple[LLMError, float]:
        """Map a transport exception to (typed error, amount to settle), keeping only scrubbed text of it."""
        full = prepared.reserve_usd
        where = f"{self.config.provider} ({self.config.model})"
        if isinstance(exc, (openai.APITimeoutError, TimeoutError)):
            return LLMTimeout(f"{where} did not answer within {prepared.timeout_s:g}s"), full
        if isinstance(exc, openai.APIStatusError):
            status = exc.status_code
            # A 5xx, or a 408 request timeout, may have generated tokens first, so it keeps the safe
            # over-count; any other 4xx rejects the request before generation, so nothing is billed.
            billed = full if status >= 500 or status == 408 else 0.0
            return LLMResponseError(f"HTTP {status} from {where}: {self._scrub(_api_message(exc))}",
                                    kind="http", request_id=exc.request_id, status_code=status), billed
        if isinstance(exc, (openai.APIConnectionError, ConnectionError)):
            detail = self._scrub(str(exc.__cause__ or exc))
            return LLMConnectionError(f"cannot reach {where} at {self.config.base_url}: {detail}"), full
        if isinstance(exc, LLMError):
            return exc, full
        return LLMError(f"{where} request failed: {type(exc).__name__}: {self._scrub(str(exc))}"), full

    def _scrub(self, text: str, limit: int = 300) -> str:
        """Remove the key from provider error text (some echo it back) and bound the length."""
        key = self.config.api_key
        if key and len(key) >= 8:
            text = text.replace(key, "[redacted]")
        return text if len(text) <= limit else text[:limit] + "..."

    def _close(self, entry_id: str, label: str, cost: float, status: str, latency_ms: int, *,
               request_id: str | None = None, response_id: str | None = None,
               usage: dict[str, int] | None = None, error: BaseException | None = None) -> float:
        """Settle the reservation and write the call's single log line."""
        cfg = self.config
        note = None
        if error is not None:
            note = self._scrub(f"{getattr(error, 'kind', type(error).__name__)}: {error}")
        elif usage is None:
            note = "usage missing from the response; settled at the reservation"
        spent = self.ledger.settle(entry_id, settled_usd=cost, status=status, request_id=request_id,
                                   response_id=response_id, usage=usage, latency_ms=latency_ms, error=note)
        tokens = ("in=%(prompt_tokens)d cached=%(cached_tokens)d out=%(completion_tokens)d "
                  "reasoning=%(reasoning_tokens)d" % usage) if usage else "unknown"
        log.log(logging.INFO if status == "settled" else logging.WARNING,
                "llm %s provider=%s model=%s label=%s request_id=%s tokens %s cost=$%.6f latency=%dms "
                "ledger=$%.4f/$%.2f%s", "ok" if status == "settled" else "failed", cfg.provider, cfg.model,
                label, request_id or "-", tokens, cost, latency_ms, spent, self.ledger.cap_usd,
                f" error={note}" if note else "")
        return spent


_client: LLMClient | None = None
_client_lock = threading.Lock()


def get_client() -> LLMClient:
    """Process-wide client, built from the environment on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = LLMClient()
        return _client
