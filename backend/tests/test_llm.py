"""Tests for app.services.llm: spend cap, ledger, strict schemas and typed failures. No network."""

from __future__ import annotations

import contextlib
import errno
import io
import json
import logging
import math
import os
import re
import sys
import tempfile
import threading
import traceback
import unittest
from pathlib import Path
from unittest import mock

import httpx
import openai

from app.services import llm
from app.services.llm import (
    BudgetExceeded, Ledger, LedgerError, LLMClient, LLMConfig, LLMConfigError, LLMConnectionError,
    LLMDisabled, LLMError, LLMResponseError, LLMSchemaError, LLMTimeout, OpenAITransport, strict_schema,
)

KEY = "sk-test-0123456789-never-log-this"
BASETEN = dict(provider="baseten", base_url="https://inference.baseten.co/v1",
               model="meta-models/muse-spark-open-1026", key_source="BASETEN_API_KEY")
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["intro", "verse", "chorus"]},
                    "chordCount": {"type": "integer"},
                },
            },
        },
    },
}
MESSAGES = [{"role": "user", "content": "Plan a short pop song form in C major."}]
GOOD = {"title": "Sunny", "sections": [{"type": "verse", "chordCount": 16}, {"type": "chorus", "chordCount": 16}]}
USAGE = {"prompt_tokens": 1000, "completion_tokens": 500,
         "prompt_tokens_details": {"cached_tokens": 400}, "completion_tokens_details": {"reasoning_tokens": 300}}
USAGE_COST = (600 * 1.25 + 400 * 0.15 + 500 * 4.25) / 1_000_000  # 0.002935 USD
_QUIET = logging.NullHandler()
TEMPLATE = Path(__file__).resolve().parents[2] / "deploy" / "env.example"


def setUpModule():
    # Failure-path tests log WARNING lines on purpose; keep them out of the runner output
    logging.getLogger("app.services.llm").addHandler(_QUIET)


def tearDownModule():
    logging.getLogger("app.services.llm").removeHandler(_QUIET)


def response(content, *, usage=USAGE, finish_reason="stop"):
    body = {"id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "muse-spark-1.3",
            "choices": [{"index": 0, "finish_reason": finish_reason,
                         "message": {"role": "assistant", "content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return body


class FakeTransport:
    """Returns (or raises) the same result on every call and records each request."""

    def __init__(self, result, headers=None):
        self.result = result
        self.headers = headers
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result, self.headers or {"X-Request-Id": f"req_{len(self.calls)}"}


class Replies(FakeTransport):
    """Returns each result in turn, the last one for every later call."""

    def __init__(self, *results):
        super().__init__(results[0])
        self.results = list(results)

    def __call__(self, request):
        self.result = self.results[min(len(self.calls), len(self.results) - 1)]
        return super().__call__(request)


class LLMTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="llm-test-", dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        self.ledger_path = Path(tmp.name) / "ledger" / "meta_ledger.json"

    def config(self, **overrides):
        values = dict(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                      api_key=KEY, key_source="MODEL_API_KEY")
        return LLMConfig(**{**values, **overrides})

    def client(self, transport, *, cap=25.0, **config):
        return LLMClient(self.config(**config), Ledger(self.ledger_path, cap), transport)

    def sdk_client(self, handler, **config):
        """A client whose real OpenAITransport talks to an in-process httpx mock."""
        config = self.config(**config)
        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)
        return LLMClient(config, Ledger(self.ledger_path, 25.0), OpenAITransport(config, http_client=http_client))

    def call(self, client, **kwargs):
        return client.chat_json(MESSAGES, SCHEMA, name="song_form", label="test", **kwargs)

    def ledger(self):
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))


class ReservationTests(LLMTestCase):
    def test_media_needs_an_explicit_token_bound_instead_of_base64_characters(self):
        client = self.client(FakeTransport(response(json.dumps(GOOD))))
        messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]}]
        with self.assertRaisesRegex(ValueError, "input_token_upper_bound"):
            client.prepare(messages, SCHEMA, name="media")
        prepared = client.prepare(messages, SCHEMA, name="media", input_token_upper_bound=1_048_576,
                                  max_completion_tokens=8192, max_request_usd=1.35)
        self.assertEqual(prepared.input_tokens_estimate, 1_048_576)
        self.assertEqual(prepared.reserve_usd, 1.345536)
        # This bound covers the processed input, and must not be sent as an API parameter.
        self.assertNotIn("input_token_upper_bound", prepared.body)
        self.assertNotIn("max_request_usd", prepared.body)

    def test_bad_explicit_bounds_are_rejected(self):
        client = self.client(FakeTransport(response(json.dumps(GOOD))))
        for bound in (0, -1, True, 1.5):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                client.prepare(MESSAGES, SCHEMA, name="media", input_token_upper_bound=bound)
        for cap in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                client.prepare(MESSAGES, SCHEMA, name="media", max_request_usd=cap)

    def test_reservation_is_input_estimate_plus_full_completion_budget(self):
        prepared = self.client(FakeTransport(response(json.dumps(GOOD)))).prepare(
            MESSAGES, SCHEMA, name="song_form", max_completion_tokens=2048)
        chars = len(json.dumps(MESSAGES, ensure_ascii=False)) + len(json.dumps(strict_schema(SCHEMA)))
        tokens = math.ceil(chars / 3)
        self.assertEqual(prepared.input_tokens_estimate, tokens)
        self.assertAlmostEqual(prepared.reserve_usd, (tokens * 1.25 + 2048 * 4.25) / 1_000_000, places=8)
        self.assertEqual(prepared.body["max_completion_tokens"], 2048)
        self.assertEqual(prepared.body["reasoning_effort"], "low")
        self.assertEqual(prepared.body["response_format"]["json_schema"],
                         {"name": "song_form", "strict": True, "schema": strict_schema(SCHEMA)})
        self.assertNotIn(KEY, json.dumps(prepared.body))

    def test_settlement_uses_actual_usage_with_cached_tokens(self):
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertLogs("app.services.llm", "INFO") as logs:
            result = self.call(self.client(transport))
        self.assertEqual(result.data, GOOD)
        self.assertAlmostEqual(result.cost_usd, USAGE_COST, places=8)
        self.assertEqual(result.usage, {"prompt_tokens": 1000, "cached_tokens": 400,
                                        "completion_tokens": 500, "reasoning_tokens": 300})
        self.assertEqual((result.request_id, result.response_id), ("req_1", "chatcmpl-test"))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["timeout"], 60.0)
        state = self.ledger()
        (entry,) = state["entries"]
        self.assertEqual((entry["status"], entry["request_id"]), ("settled", "req_1"))
        self.assertAlmostEqual(entry["settled_usd"], USAGE_COST, places=8)
        self.assertGreater(entry["reserved_usd"], entry["settled_usd"])
        self.assertAlmostEqual(state["spent_usd"], USAGE_COST, places=8)
        self.assertEqual(state["cap_usd"], 25.0)
        (line,) = [r.getMessage() for r in logs.records if r.levelno == logging.INFO]
        for part in ("provider=meta", "model=muse-spark-1.3", "label=test", "request_id=req_1",
                     "in=1000 cached=400 out=500 reasoning=300", "cost=$0.002935", "ledger=$0.0029/$25.00"):
            self.assertIn(part, line)

    def test_missing_usage_settles_at_the_reservation(self):
        client = self.client(FakeTransport(response(json.dumps(GOOD), usage=None)))
        prepared = client.prepare(MESSAGES, SCHEMA, name="song_form")
        result = self.call(client)
        self.assertAlmostEqual(result.cost_usd, prepared.reserve_usd, places=8)
        self.assertIn("usage missing", self.ledger()["entries"][0]["error"])


class CapTests(LLMTestCase):
    def test_per_request_cap_rejects_before_reservation_or_transport(self):
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertRaises(BudgetExceeded) as ctx:
            self.call(self.client(transport), input_token_upper_bound=1_048_576,
                      max_completion_tokens=8192, max_request_usd=1.0)
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.ledger_path.exists())
        self.assertEqual(ctx.exception.request_usd, 1.345536)
        self.assertEqual(ctx.exception.cap_usd, 1.0)

    def test_cap_refusal_happens_before_the_transport(self):
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertRaises(BudgetExceeded) as ctx:
            self.call(self.client(transport, cap=0.005))  # 2048 output tokens alone reserve ~$0.0087
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.ledger_path.exists())
        self.assertIsInstance(ctx.exception, LLMError)
        self.assertEqual(ctx.exception.cap_usd, 0.005)

    def test_outstanding_reservations_count_toward_the_cap(self):
        Ledger(self.ledger_path, 0.018).reserve(label="other.worker", provider="meta",
                                                model="muse-spark-1.3", reserved_usd=0.015)
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertRaises(BudgetExceeded) as ctx:  # ~$0.0046 alone would fit under $0.018
            self.call(self.client(transport, cap=0.018), max_completion_tokens=1024)
        self.assertEqual(transport.calls, [])
        self.assertAlmostEqual(ctx.exception.outstanding_usd, 0.015)

    def test_missing_key_fails_before_reserving(self):
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertRaises(LLMConfigError):
            self.call(self.client(transport, api_key=""))
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.ledger_path.parent.exists())

    def test_80_percent_warning_is_logged_once(self):
        # $1 per output token and free input: each call reserves and settles exactly $1
        client = self.client(FakeTransport(response(json.dumps(GOOD), usage={"prompt_tokens": 10, "completion_tokens": 1})),
                             cap=10.0, price_input_per_m=0.0, price_cached_per_m=0.0, price_output_per_m=1e6)
        with self.assertLogs("app.services.llm", "WARNING") as logs:
            for _ in range(10):
                self.call(client, max_completion_tokens=1)
            with self.assertRaises(BudgetExceeded):
                self.call(client, max_completion_tokens=1)
        crossed = [r for r in logs.records if "80%" in r.getMessage()]
        self.assertEqual(len(crossed), 1)
        self.assertEqual(self.ledger()["spent_usd"], 10.0)

    def test_failures_settle_at_the_full_reservation(self):
        request = httpx.Request("POST", "https://api.meta.ai/v1/chat/completions")
        cases = [(openai.APITimeoutError(request=request), LLMTimeout),
                 (TimeoutError("read timed out"), LLMTimeout),
                 (openai.APIConnectionError(request=request), LLMConnectionError),
                 (RuntimeError("socket closed mid-read"), LLMError)]
        for exc, expected in cases:
            with self.subTest(exc=type(exc).__name__):
                client = self.client(FakeTransport(exc))
                prepared = client.prepare(MESSAGES, SCHEMA, name="song_form")
                with self.assertRaises(expected):
                    self.call(client)
                entry = self.ledger()["entries"][-1]
                self.assertEqual(entry["status"], "failed")
                self.assertAlmostEqual(entry["settled_usd"], prepared.reserve_usd, places=8)
                self.assertEqual(entry["settled_usd"], entry["reserved_usd"])
        state = self.ledger()
        self.assertAlmostEqual(state["spent_usd"], sum(e["settled_usd"] for e in state["entries"]), places=8)

    def test_corrupt_ledger_refuses_to_spend(self):
        self.ledger_path.parent.mkdir(parents=True)
        self.ledger_path.write_text("{not json", encoding="utf-8")
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertRaises(LedgerError):
            self.call(self.client(transport))
        self.assertEqual(transport.calls, [])


class LedgerTests(LLMTestCase):
    def test_ledger_persists_and_reloads_across_two_clients(self):
        first = self.call(self.client(FakeTransport(response(json.dumps(GOOD)))))
        second_client = self.client(FakeTransport(response(json.dumps(GOOD))))
        self.assertAlmostEqual(second_client.ledger.snapshot()["spent_usd"], first.cost_usd, places=8)
        second = self.call(second_client)
        state = self.ledger()
        self.assertEqual([e["status"] for e in state["entries"]], ["settled", "settled"])
        self.assertAlmostEqual(state["spent_usd"], first.cost_usd + second.cost_usd, places=8)
        self.assertEqual(set(state["entries"][0]), {
            "id", "ts", "label", "provider", "model", "reserved_usd", "settled_usd", "status",
            "request_id", "response_id", "usage", "latency_ms", "error"})

    def test_concurrent_workers_on_one_file_lose_nothing(self):
        def worker():
            client = self.client(FakeTransport(response(json.dumps(GOOD))))  # own Ledger: only flock serialises
            for _ in range(5):
                self.call(client)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        state = self.ledger()
        self.assertEqual(len(state["entries"]), 20)
        self.assertTrue(all(e["status"] == "settled" for e in state["entries"]))
        self.assertAlmostEqual(state["spent_usd"], 20 * USAGE_COST, places=6)

    def test_lock_and_temp_file_errors_are_ledger_errors_before_anything_is_sent(self):
        for target, name, error in ((llm.fcntl, "flock", OSError(errno.ENOLCK, "No locks available")),  # NFS
                                    (llm.tempfile, "mkstemp", OSError(errno.EROFS, "Read-only file system"))):
            with self.subTest(fails=name), mock.patch.object(target, name, side_effect=error):
                transport = FakeTransport(response(json.dumps(GOOD)))
                with self.assertRaises(LedgerError) as ctx:  # an LLMError, not the raw OSError
                    self.call(self.client(transport))
                self.assertIn(error.strerror, str(ctx.exception))
                self.assertEqual(transport.calls, [])
                self.assertFalse(self.ledger_path.exists())

    def test_get_client_is_one_client_per_process_built_from_env(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path),
               "THEARTIST_META_BUDGET_USD": "40"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "_clients", {}):
            client = llm.get_client()
            self.assertIs(llm.get_client(), client)
            judge = llm.get_client("judge")  # no LLM_JUDGE_PROVIDER: the judge is the default client's twin
            self.assertIsNot(judge, client)
            self.assertIs(llm.get_client("judge"), judge)
        self.assertEqual((client.config.model, client.ledger.cap_usd), ("muse-spark-1.3", 40.0))
        self.assertEqual(client.ledger.path, self.ledger_path.resolve())
        self.assertEqual((judge.config, judge.ledger.path, judge.ledger.cap_usd),
                         (client.config, client.ledger.path, 40.0))  # the same config and ledger file
        self.assertFalse(self.ledger_path.parent.exists())  # nothing is created until a request

    def test_get_client_builds_the_judge_role_from_its_own_variables_and_ledger(self):
        judge_path = self.ledger_path.with_name("judge_ledger.json")
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path),
               "LLM_JUDGE_PROVIDER": "baseten", "BASETEN_API_KEY": KEY, "THEARTIST_JUDGE_LEDGER": str(judge_path),
               "THEARTIST_JUDGE_BUDGET_USD": "3.5"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "_clients", {}):
            client, judge = llm.get_client(), llm.get_client("judge")
            self.assertIs(llm.get_client("judge"), judge)
            with self.assertRaises(ValueError):
                llm.get_client("critic")
        self.assertEqual((client.config.provider, client.ledger.path, client.ledger.cap_usd),
                         ("meta", self.ledger_path.resolve(), 25.0))
        self.assertEqual((judge.config.provider, judge.config.model, judge.config.role),
                         ("baseten", "meta-models/muse-spark-open-1026", "judge"))
        self.assertEqual((judge.ledger.path, judge.ledger.cap_usd), (judge_path.resolve(), 3.5))

    def test_the_meta_flag_refuses_get_client_for_every_role_but_not_a_direct_client(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path), "LLM_JUDGE_PROVIDER": "baseten",
               "BASETEN_API_KEY": KEY, "THEARTIST_JUDGE_LEDGER": str(self.ledger_path.with_name("judge.json"))}
        for value in ("0", "false", " OFF "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {**env, "THEARTIST_META_ENABLED": value},
                                                            clear=True), mock.patch.object(llm, "_clients", {}):
                for role in ("default", "judge"):
                    with self.assertRaises(LLMDisabled) as ctx:
                        llm.get_client(role)
                    self.assertIsInstance(ctx.exception, LLMConfigError)
                    self.assertIn("THEARTIST_META_ENABLED=0", str(ctx.exception))
                self.assertEqual(llm._clients, {})  # refused before anything was built
                self.assertEqual(self.call(self.client(FakeTransport(response(json.dumps(GOOD))))).data, GOOD)
        with mock.patch.dict(os.environ, {**env, "THEARTIST_META_ENABLED": "maybe"}, clear=True), \
                mock.patch.object(llm, "_clients", {}):
            with self.assertRaises(LLMConfigError) as ctx:  # a typo refuses too, visibly
                llm.get_client()
            self.assertNotIsInstance(ctx.exception, LLMDisabled)
            self.assertIn("THEARTIST_META_ENABLED", str(ctx.exception))
        for value in ("1", "yes", ""):
            with self.subTest(value=value), mock.patch.dict(os.environ, {**env, "THEARTIST_META_ENABLED": value},
                                                            clear=True), mock.patch.object(llm, "_clients", {}):
                self.assertEqual(llm.get_client().config.provider, "meta")
        self.assertFalse(llm.meta_enabled({"THEARTIST_META_ENABLED": "0"}))  # the flag also reads a dict env
        self.assertTrue(llm.meta_enabled({}))

    def test_the_judge_ledger_has_its_own_variables_and_defaults_unless_the_judge_is_the_default_client(self):
        judge = Ledger.from_env({"LLM_JUDGE_PROVIDER": "baseten"}, role="judge")
        self.assertEqual((judge.path, judge.cap_usd), (llm.DEFAULT_JUDGE_LEDGER_PATH, 10.0))
        self.assertEqual(judge.path.name, "judge_ledger.json")
        self.assertEqual(judge.path.parent, llm.DEFAULT_LEDGER_PATH.parent)
        own = Ledger.from_env({"LLM_JUDGE_PROVIDER": "baseten", "THEARTIST_JUDGE_LEDGER": str(self.ledger_path),
                               "THEARTIST_JUDGE_BUDGET_USD": "2", "THEARTIST_META_BUDGET_USD": "40"}, role="judge")
        self.assertEqual((own.path, own.cap_usd), (self.ledger_path.resolve(), 2.0))
        shared = Ledger.from_env({"THEARTIST_META_BUDGET_USD": "40", "THEARTIST_JUDGE_BUDGET_USD": "2",
                                  "THEARTIST_JUDGE_LEDGER": str(self.ledger_path)}, role="judge")
        self.assertEqual((shared.path, shared.cap_usd), (llm.DEFAULT_LEDGER_PATH, 40.0))  # the Meta ledger and cap
        with self.assertRaises(ValueError):
            Ledger.from_env({}, role="critic")
        with self.assertRaises(LLMConfigError):
            Ledger.from_env({"LLM_JUDGE_PROVIDER": "baseten", "THEARTIST_JUDGE_BUDGET_USD": "ten"}, role="judge")


class ConfigTests(unittest.TestCase):
    def test_contributor_model_ids_are_rejected(self):
        for env in ({"MODEL_API_KEY": KEY, "LLM_MODEL": "muse-spark-1.3-contributor"},
                    {"MODEL_API_KEY": KEY, "LLM_MODEL": "muse-spark-1.3-Contributor"},
                    {"LLM_PROVIDER": "custom", "LLM_BASE_URL": "https://llm.example/v1",
                     "LLM_MODEL": "x-contributor", "LLM_API_KEY": KEY}):
            with self.subTest(model=env["LLM_MODEL"]), self.assertRaises(LLMConfigError) as ctx:
                LLMConfig.from_env(env)
            self.assertIn("Contributor", str(ctx.exception))
        with self.assertRaises(LLMConfigError):
            LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3-contributor")

    def test_provider_defaults_prices_and_key_routing(self):
        meta = LLMConfig.from_env({"MODEL_API_KEY": KEY})
        self.assertEqual((meta.base_url, meta.model, meta.api_key, meta.timeout_s, meta.reasoning_effort),
                         ("https://api.meta.ai/v1", "muse-spark-1.3", KEY, 60.0, "low"))
        self.assertEqual((meta.price_input_per_m, meta.price_cached_per_m, meta.price_output_per_m),
                         (1.25, 0.15, 4.25))
        with self.assertLogs("app.services.llm", "WARNING"):
            ignored = LLMConfig.from_env({"MODEL_API_KEY": KEY, "LLM_API_KEY": "sk-other-0123456789"})
        self.assertEqual(ignored.api_key, KEY)  # the Meta key comes only from MODEL_API_KEY
        ollama = LLMConfig.from_env({"LLM_PROVIDER": "ollama"})
        self.assertEqual((ollama.base_url, ollama.model, ollama.api_key), ("http://localhost:11434/v1",
                                                                           "llama3.2:3b", "ollama"))
        self.assertEqual((ollama.price_input_per_m, ollama.price_output_per_m, ollama.reasoning_effort),
                         (0.0, 0.0, None))
        fireworks = LLMConfig.from_env({"LLM_PROVIDER": "fireworks", "FIREWORKS_API_KEY": KEY,
                                        "LLM_REASONING_EFFORT": "none"})
        self.assertEqual((fireworks.price_output_per_m, fireworks.reasoning_effort), (4.25, None))
        baseten = LLMConfig.from_env({"LLM_PROVIDER": "baseten", "BASETEN_API_KEY": KEY})
        self.assertEqual(baseten.model, "meta-models/muse-spark-open-1026")
        self.assertEqual((baseten.price_input_per_m, baseten.price_cached_per_m, baseten.price_output_per_m,
                          baseten.price_source), (1.25, 0.15, 4.25, "baseten muse-spark-open-1026 list price"))
        other = LLMConfig.from_env({"LLM_PROVIDER": "baseten", "BASETEN_API_KEY": KEY, "LLM_MODEL": "meta-models/other"})
        self.assertEqual(other.price_source, "unknown model price, Spark Standard assumed")
        priced = LLMConfig.from_env({"MODEL_API_KEY": KEY, "LLM_PRICE_OUTPUT_PER_M": "5", "LLM_TIMEOUT_S": "12.5",
                                     "LLM_PRICE_INPUT_PER_M": ""})
        self.assertEqual((priced.price_input_per_m, priced.price_output_per_m, priced.timeout_s), (1.25, 5.0, 12.5))
        self.assertEqual(priced.price_source, "LLM_PRICE_*_PER_M")
        custom = LLMConfig.from_env({"LLM_PROVIDER": "custom", "LLM_BASE_URL": "https://llm.example/v1",
                                     "LLM_MODEL": "some-model", "LLM_API_KEY": KEY})
        self.assertEqual((custom.api_key, custom.price_output_per_m), (KEY, 4.25))

    def test_reasoning_effort_is_the_provider_default_unless_set_and_none_is_not_sent(self):
        envs = {"meta": {"MODEL_API_KEY": KEY}, "baseten": {"BASETEN_API_KEY": KEY},
                "fireworks": {"FIREWORKS_API_KEY": KEY}, "ollama": {},
                "custom": {"LLM_BASE_URL": "https://llm.example/v1", "LLM_MODEL": "some-model", "LLM_API_KEY": KEY}}
        defaults = {"meta": "low", "baseten": "low", "fireworks": "low", "ollama": None, "custom": None}
        for provider, env in envs.items():
            # Baseten documents low / medium / high / xhigh; the others take minimal / low / medium / high
            own = "XHigh" if provider == "baseten" else "Minimal"
            for value, expected in ((None, defaults[provider]), ("", defaults[provider]), ("none", None),
                                    ("None", None), ("high", "high"), (own, own.lower())):
                with self.subTest(provider=provider, LLM_REASONING_EFFORT=value):
                    given = {**env, "LLM_PROVIDER": provider}
                    if value is not None:  # None: the variable is unset
                        given["LLM_REASONING_EFFORT"] = value
                    config = LLMConfig.from_env(given)
                    body = LLMClient(config, mock.Mock(spec=Ledger)).prepare(MESSAGES, SCHEMA, name="song_form").body
                    self.assertEqual(config.reasoning_effort, expected)
                    self.assertEqual(body.get("reasoning_effort", "not sent"), expected or "not sent")
            with self.subTest(provider=provider, LLM_REASONING_EFFORT="the other provider's value"):
                other = "minimal" if provider == "baseten" else "xhigh"
                with self.assertRaises(LLMConfigError):
                    LLMConfig.from_env({**env, "LLM_PROVIDER": provider, "LLM_REASONING_EFFORT": other})

    def test_the_judge_role_reads_its_own_variables_or_is_exactly_the_default_config(self):
        env = {"MODEL_API_KEY": KEY, "LLM_TIMEOUT_S": "30", "LLM_REASONING_EFFORT": "high",
               "LLM_PRICE_OUTPUT_PER_M": "9", "BASETEN_API_KEY": "sk-baseten-0123456789"}
        default = LLMConfig.from_env(env)
        self.assertEqual(LLMConfig.from_env(env, role="judge"), default)  # no LLM_JUDGE_PROVIDER
        self.assertEqual(LLMConfig.from_env({**env, "LLM_JUDGE_PROVIDER": " "}, role="judge"), default)
        self.assertEqual((default.role, default.timeout_s, default.price_output_per_m), ("default", 30.0, 9.0))
        judge = LLMConfig.from_env({**env, "LLM_JUDGE_PROVIDER": "Baseten", "LLM_JUDGE_TIMEOUT_S": "90",
                                    "LLM_JUDGE_REASONING_EFFORT": "xhigh", "LLM_JUDGE_PRICE_CACHED_PER_M": "0.1"},
                                   role="judge")
        self.assertEqual((judge.role, judge.provider, judge.base_url, judge.model),
                         ("judge", "baseten", "https://inference.baseten.co/v1", "meta-models/muse-spark-open-1026"))
        self.assertEqual((judge.api_key, judge.key_source), ("sk-baseten-0123456789", "BASETEN_API_KEY"))
        self.assertEqual((judge.timeout_s, judge.reasoning_effort), (90.0, "xhigh"))  # not the LLM_* values
        self.assertEqual((judge.price_input_per_m, judge.price_cached_per_m, judge.price_output_per_m,
                          judge.price_source), (1.25, 0.1, 4.25, "LLM_JUDGE_PRICE_*_PER_M"))
        overridden = LLMConfig.from_env({**env, "LLM_JUDGE_PROVIDER": "baseten", "LLM_JUDGE_API_KEY": KEY,
                                         "LLM_JUDGE_BASE_URL": "https://inference.baseten.co/v1/",
                                         "LLM_JUDGE_MODEL": "meta-models/muse-spark-open-1026"}, role="judge")
        self.assertEqual((overridden.api_key, overridden.key_source), (KEY, "LLM_JUDGE_API_KEY"))
        self.assertEqual(overridden.base_url, "https://inference.baseten.co/v1/")
        self.assertEqual(LLMConfig.from_env({**env, "LLM_JUDGE_PROVIDER": "meta"}, role="judge").api_key, KEY)
        for judge_env, named in (({"LLM_JUDGE_PROVIDER": "baseten", "LLM_JUDGE_BASE_URL": "https://api.meta.ai/v1"},
                                  "LLM_JUDGE_BASE_URL"),
                                 ({"LLM_JUDGE_PROVIDER": "custom"}, "LLM_JUDGE_MODEL"),
                                 ({"LLM_JUDGE_PROVIDER": "nope"}, "LLM_JUDGE_PROVIDER"),
                                 ({"LLM_JUDGE_PROVIDER": "baseten", "LLM_JUDGE_PRICE_INPUT_PER_M": "x"},
                                  "LLM_JUDGE_PRICE_INPUT_PER_M")):
            with self.subTest(env=judge_env), self.assertRaises(LLMConfigError) as ctx:
                LLMConfig.from_env({**env, **judge_env}, role="judge")
            self.assertIn(named, str(ctx.exception))  # errors name the judge's variables
        with self.assertRaises(ValueError):
            LLMConfig.from_env(env, role="critic")

    def test_bad_configurations_fail_at_config_time(self):
        for env in ({"LLM_PROVIDER": "custom", "LLM_BASE_URL": "https://llm.example/v1"},
                    {"LLM_PROVIDER": "nope"},
                    # the template's Meta URL left in place must never receive the Baseten key
                    {"LLM_PROVIDER": "baseten", "BASETEN_API_KEY": KEY, "LLM_BASE_URL": "https://api.meta.ai/v1"},
                    {"MODEL_API_KEY": KEY, "LLM_TIMEOUT_S": "0"},
                    {"MODEL_API_KEY": KEY, "LLM_REASONING_EFFORT": "extreme"},
                    {"MODEL_API_KEY": KEY, "LLM_PRICE_OUTPUT_PER_M": "-1"}):
            with self.subTest(env=env), self.assertRaises(LLMConfigError):
                LLMConfig.from_env(env)

    def test_each_hosted_endpoint_is_reached_only_under_its_own_provider(self):
        meta_url = "https://api.meta.ai/v1"
        for env in ({"LLM_PROVIDER": "baseten", "LLM_API_KEY": KEY, "LLM_BASE_URL": meta_url},
                    {"LLM_PROVIDER": "fireworks", "LLM_API_KEY": KEY, "LLM_BASE_URL": meta_url},
                    {"LLM_PROVIDER": "ollama", "LLM_BASE_URL": meta_url},
                    {"LLM_PROVIDER": "custom", "LLM_BASE_URL": meta_url, "LLM_MODEL": "muse-spark-1.3",
                     "LLM_API_KEY": KEY},
                    {"MODEL_API_KEY": KEY, "LLM_BASE_URL": "https://inference.baseten.co/v1"},
                    {"MODEL_API_KEY": KEY, "LLM_BASE_URL": "http://api.meta.ai/v1"}):  # the key in clear text
            with self.subTest(env=env), self.assertRaises(LLMConfigError):
                LLMConfig.from_env(env)
        own = LLMConfig.from_env({"LLM_PROVIDER": "baseten", "LLM_API_KEY": KEY,
                                  "LLM_BASE_URL": "https://inference.baseten.co/v1/"})
        self.assertEqual((own.base_url, own.key_source), ("https://inference.baseten.co/v1/", "LLM_API_KEY"))
        for url, output_price in (("http://localhost:11434/v1", 0.0), ("http://127.0.0.1:11434/v1", 0.0),
                                  ("http://[::1]:11434/v1", 0.0), ("http://gpu-box:11434/v1", 4.25)):
            with self.subTest(url=url):  # ollama is free only on this machine
                config = LLMConfig.from_env({"LLM_PROVIDER": "ollama", "LLM_BASE_URL": url})
                self.assertEqual(config.price_output_per_m, output_price)

    @unittest.skipUnless(TEMPLATE.exists(), "deploy/env.example is not in this checkout")
    def test_switching_provider_in_the_env_template_keeps_keys_on_their_own_hosts(self):
        lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
        template = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
        keys = {"MODEL_API_KEY": KEY, "LLM_API_KEY": KEY, "BASETEN_API_KEY": KEY, "FIREWORKS_API_KEY": KEY}
        self.assertEqual(LLMConfig.from_env({**template, **keys}).base_url, "https://api.meta.ai/v1")
        for provider, spec in llm.PROVIDERS.items():
            with self.subTest(provider=provider):
                try:
                    config = LLMConfig.from_env({**template, **keys, "LLM_PROVIDER": provider})
                except LLMConfigError:
                    continue  # refused before anything is sent
                self.assertEqual(llm._host(config.base_url), llm._host(spec.base_url))

    @unittest.skipUnless(TEMPLATE.exists(), "deploy/env.example is not in this checkout")
    def test_the_env_template_names_only_providers_the_client_accepts(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        listed = re.findall(r"^#   (\w+) ", text.split("\nLLM_PROVIDER=", 1)[0], flags=re.M)
        self.assertEqual(sorted(listed), sorted([*llm.PROVIDERS, "custom"]))
        self.assertIn("\nLLM_REASONING_EFFORT=\n", text)  # empty, so every provider keeps its default
        with self.assertRaises(LLMConfigError):  # Modal is an endpoint reached through custom
            LLMConfig.from_env({"LLM_PROVIDER": "modal", "LLM_API_KEY": KEY})
        modal = LLMConfig.from_env({"LLM_PROVIDER": "custom", "LLM_BASE_URL": "https://example--llm-serve.modal.run/v1",
                                    "LLM_MODEL": "meta-llama/Llama-3.1-8B-Instruct", "LLM_API_KEY": KEY})
        self.assertEqual((modal.provider, modal.key_source, modal.reasoning_effort), ("custom", "LLM_API_KEY", None))


class SchemaTests(unittest.TestCase):
    def test_strict_schema_closes_every_object(self):
        out = strict_schema(SCHEMA)
        self.assertEqual(out["required"], ["title", "sections"])
        self.assertIs(out["additionalProperties"], False)
        item = out["properties"]["sections"]["items"]
        self.assertEqual(item["required"], ["type", "chordCount"])
        self.assertIs(item["additionalProperties"], False)
        self.assertEqual(item["properties"]["type"]["enum"], ["intro", "verse", "chorus"])
        self.assertNotIn("required", SCHEMA)  # the input is left untouched

    def test_strict_schema_rejects_what_strict_mode_cannot_express(self):
        for bad in ({"type": "object", "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "null"}]}}},
                    {"type": "object", "properties": {"x": {"type": "array", "items": {"oneOf": []}}}},
                    {"type": "object", "allOf": []},
                    {"type": "object", "properties": {"x": {"$ref": "#"}}},
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "object", "properties": {}, "additionalProperties": True},
                    {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["y"]}):
            with self.subTest(bad=bad), self.assertRaises(LLMSchemaError):
                strict_schema(bad)


class OpenWeightTests(LLMTestCase):
    """What differs for the endpoints that do not enforce json_schema; meta stays byte for byte."""

    def test_baseten_sends_max_tokens_and_states_the_schema_in_the_system_message(self):
        system = {"role": "system", "content": "You plan song forms.  "}
        for provider, settings in (("baseten", BASETEN),
                                   ("fireworks", dict(provider="fireworks", base_url="https://api.fireworks.ai/inference/v1",
                                                      model="accounts/fireworks/models/muse-glimmer-30b")),
                                   ("ollama", dict(provider="ollama", base_url="http://localhost:11434/v1", model="llama3.2:3b",
                                                   reasoning_effort=None)),
                                   ("custom", dict(provider="custom", base_url="https://llm.example/v1", model="m",
                                                   reasoning_effort=None))):
            with self.subTest(provider=provider):
                client = self.client(FakeTransport(response(json.dumps(GOOD))), **settings)
                body = client.prepare([system, *MESSAGES], SCHEMA, name="song_form", max_completion_tokens=512).body
                limit = "max_tokens" if provider == "baseten" else "max_completion_tokens"
                self.assertEqual(body[limit], 512)
                self.assertNotIn("max_completion_tokens" if provider == "baseten" else "max_tokens", body)
                self.assertEqual(len(body["messages"]), 2)  # the schema joins the existing system message
                guard = body["messages"][0]["content"]
                self.assertTrue(guard.startswith("You plan song forms.\n\n"))
                self.assertIn("Reply with a single JSON object matching this schema; no prose, no code fences", guard)
                self.assertIn(json.dumps(strict_schema(SCHEMA), ensure_ascii=False), guard)
                self.assertEqual(body["messages"][1], MESSAGES[0])
                self.assertEqual(body["response_format"]["json_schema"]["strict"], True)
                # No system message: one is added in front of the user turn
                body = client.prepare(MESSAGES, SCHEMA, name="song_form").body
                self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
                self.assertEqual(body["messages"][1], MESSAGES[0])
                prepared = client.prepare(MESSAGES, SCHEMA, name="song_form")
                self.assertEqual(prepared.input_tokens_estimate,  # the guard text is part of the estimate
                                 math.ceil((len(json.dumps(body["messages"], ensure_ascii=False))
                                            + len(json.dumps(strict_schema(SCHEMA), ensure_ascii=False))) / 3))
        meta = self.client(FakeTransport(response(json.dumps(GOOD)))).prepare([system, *MESSAGES], SCHEMA,
                                                                              name="song_form", max_completion_tokens=512)
        self.assertEqual(meta.body["messages"], [system, *MESSAGES])  # unchanged
        self.assertEqual(meta.body["max_completion_tokens"], 512)
        self.assertNotIn("max_tokens", meta.body)

    def test_the_request_id_also_comes_from_the_baseten_header_on_success_and_on_a_429(self):
        transport = FakeTransport(response(json.dumps(GOOD)), headers={"X-Baseten-Request-Id": "bt_ok"})
        result = self.call(self.client(transport, **BASETEN))
        self.assertEqual(result.request_id, "bt_ok")
        self.assertEqual(self.ledger()["entries"][-1]["request_id"], "bt_ok")
        both = FakeTransport(response(json.dumps(GOOD)), headers={"x-baseten-request-id": "bt", "x-request-id": "req"})
        self.assertEqual(self.call(self.client(both, **BASETEN)).request_id, "req")

        def limited(request):
            return httpx.Response(429, json={"error": {"message": "rate limited"}},
                                  headers={"x-baseten-request-id": "bt_429", "x-ratelimit-remaining-requests": "0",
                                           "X-RateLimit-Reset-Requests": "12s", "retry-after": "12"})

        client = self.sdk_client(limited, **BASETEN)
        with self.assertRaises(LLMResponseError) as ctx:
            self.call(client)
        exc = ctx.exception
        self.assertEqual((exc.kind, exc.status_code, exc.request_id), ("http", 429, "bt_429"))
        self.assertIn("x-ratelimit-remaining-requests=0; x-ratelimit-reset-requests=12s", str(exc))
        entry = self.ledger()["entries"][-1]
        self.assertEqual((entry["status"], entry["request_id"], entry["settled_usd"]), ("failed", "bt_429", 0.0))
        self.assertIn("x-ratelimit-remaining-requests=0", entry["error"])
        self.assertIn("x-ratelimit-reset-requests=12s", entry["error"])
        self.assertNotIn("retry-after", entry["error"])

    def test_fenced_json_is_accepted_from_open_weight_providers_and_still_refused_from_meta(self):
        fenced = "```json\n" + json.dumps(GOOD, indent=1) + "\n```"
        for content in (fenced, "\n```\n" + json.dumps(GOOD) + "```  \n", "```json" + json.dumps(GOOD) + "```"):
            with self.subTest(content=content[:12]):
                result = self.call(self.client(FakeTransport(response(content)), **BASETEN))
                self.assertEqual((result.data, result.attempts), (GOOD, 1))
                self.assertEqual(json.loads(result.text), GOOD)  # the text is what was parsed
        with self.assertRaises(LLMResponseError) as ctx:
            self.call(self.client(FakeTransport(response(fenced))))
        self.assertEqual(ctx.exception.kind, "invalid_json")
        # Prose around a fence is not JSON either: that is what the retry is for
        with self.assertRaises(LLMResponseError) as ctx:
            self.call(self.client(Replies(response("Here it is:\n" + fenced), response("still prose")), **BASETEN))
        self.assertEqual(ctx.exception.kind, "invalid_json")

    def test_open_weight_providers_retry_exactly_once_after_a_bad_reply_and_meta_never(self):
        bad = response(json.dumps({"title": "x", "sections": [{"type": "drop", "chordCount": 8}]}))
        transport = Replies(bad, response(json.dumps(GOOD)))
        with self.assertLogs("app.services.llm", "WARNING") as logs:
            result = self.call(self.client(transport, **BASETEN), input_token_upper_bound=1000)
        self.assertEqual((result.data, result.attempts, len(transport.calls)), (GOOD, 2, 2))
        first, second = transport.calls
        self.assertEqual(second["messages"][:-1], first["messages"])  # the same request, plus the rejection
        feedback = second["messages"][-1]
        self.assertEqual(feedback["role"], "user")
        self.assertIn("rejected (schema_mismatch)", feedback["content"])
        self.assertIn("$.sections[0].type: 'drop' is not one of the allowed values", feedback["content"])
        self.assertNotIn("req_1", feedback["content"])  # the error text, not the request id
        self.assertTrue(any("retrying" in r.getMessage() and "schema_mismatch" in r.getMessage() for r in logs.records))
        state = self.ledger()
        self.assertEqual([(e["status"], e["request_id"]) for e in state["entries"]], [("failed", "req_1"), ("settled", "req_2")])
        self.assertTrue(state["entries"][0]["error"].startswith("schema_mismatch"))
        self.assertAlmostEqual(state["spent_usd"], 2 * USAGE_COST, places=8)
        self.assertEqual(Ledger(self.ledger_path).snapshot()["outstanding_usd"], 0)
        self.assertGreater(state["entries"][1]["reserved_usd"], state["entries"][0]["reserved_usd"])  # the bound grew
        self.assertEqual(result.request_id, "req_2")

        for kind, replies in (("schema_mismatch", (bad, bad)), ("invalid_json", (response("not json"), response("{")))):
            with self.subTest(second_failure=kind):
                transport = Replies(*replies)
                with self.assertRaises(LLMResponseError) as ctx:
                    self.call(self.client(transport, **BASETEN))
                self.assertEqual((ctx.exception.kind, ctx.exception.request_id, len(transport.calls)), (kind, "req_2", 2))
        for kind, reply in (("length", response('{"title": "Sun', finish_reason="length")), ("empty", response(None))):
            with self.subTest(not_retried=kind):
                transport = Replies(reply, response(json.dumps(GOOD)))
                with self.assertRaises(LLMResponseError) as ctx:
                    self.call(self.client(transport, **BASETEN))
                self.assertEqual((ctx.exception.kind, len(transport.calls)), (kind, 1))
        transport = Replies(bad, response(json.dumps(GOOD)))
        with self.assertRaises(LLMResponseError) as ctx:  # meta: one request, no second chance
            self.call(self.client(transport))
        self.assertEqual((ctx.exception.kind, len(transport.calls)), ("schema_mismatch", 1))

    def test_reasoning_effort_can_be_set_per_call_and_none_removes_it(self):
        client = self.client(FakeTransport(response(json.dumps(GOOD))))
        self.assertEqual(client.prepare(MESSAGES, SCHEMA, name="s").body["reasoning_effort"], "low")
        self.assertEqual(client.prepare(MESSAGES, SCHEMA, name="s", reasoning_effort="Medium").body["reasoning_effort"],
                         "medium")
        self.assertNotIn("reasoning_effort", client.prepare(MESSAGES, SCHEMA, name="s", reasoning_effort="none").body)
        for bad in ("xhigh", "extreme", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                client.prepare(MESSAGES, SCHEMA, name="s", reasoning_effort=bad)
        baseten = self.client(FakeTransport(response(json.dumps(GOOD))), **BASETEN)
        self.assertEqual(baseten.prepare(MESSAGES, SCHEMA, name="s", reasoning_effort="xhigh").body["reasoning_effort"],
                         "xhigh")
        with self.assertRaises(ValueError):
            baseten.prepare(MESSAGES, SCHEMA, name="s", reasoning_effort="minimal")
        transport = FakeTransport(response(json.dumps(GOOD)))
        self.call(self.client(transport), reasoning_effort="high")
        self.call(self.client(transport), reasoning_effort="none")
        self.call(self.client(transport))
        self.assertEqual([call.get("reasoning_effort") for call in transport.calls], ["high", None, "low"])


class ReplyTests(LLMTestCase):
    def test_bad_replies_raise_typed_errors_and_settle_at_actual_usage(self):
        cases = [("invalid_json", response("not json {")),
                 ("invalid_json", response("```json\n" + json.dumps(GOOD) + "\n```")),
                 ("schema_mismatch", response(json.dumps({"title": 3, "sections": []}))),
                 ("schema_mismatch", response(json.dumps({"title": "x", "sections": [{"type": "drop", "chordCount": 8}]}))),
                 ("schema_mismatch", response(json.dumps({"title": "x"}))),
                 ("schema_mismatch", response(json.dumps({**GOOD, "extra": 1}))),
                 ("schema_mismatch", response(json.dumps({"title": "x", "sections": [{"type": "verse", "chordCount": 8.5}]}))),
                 ("schema_mismatch", response(json.dumps([GOOD]))),
                 ("length", response('{"title": "Sun', finish_reason="length")),
                 ("empty", response(None))]
        for kind, reply in cases:
            with self.subTest(kind=kind, content=reply["choices"][0]["message"]["content"]):
                with self.assertRaises(LLMResponseError) as ctx:
                    self.call(self.client(FakeTransport(reply)))
                self.assertEqual(ctx.exception.kind, kind)
                self.assertEqual(ctx.exception.request_id, "req_1")
                entry = self.ledger()["entries"][-1]
                self.assertEqual((entry["status"], entry["request_id"]), ("failed", "req_1"))
                self.assertAlmostEqual(entry["settled_usd"], USAGE_COST, places=8)
                self.assertTrue(entry["error"].startswith(kind))

    def test_sdk_transport_sends_one_request_and_captures_the_request_id(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=response(json.dumps(GOOD)), headers={"x-request-id": "req_sdk"})

        result = self.call(self.sdk_client(handler))
        self.assertEqual((result.request_id, result.data, result.usage["cached_tokens"]), ("req_sdk", GOOD, 400))
        (request,) = seen
        self.assertEqual(str(request.url), "https://api.meta.ai/v1/chat/completions")
        self.assertEqual(request.headers["authorization"], f"Bearer {KEY}")
        body = json.loads(request.content)
        self.assertEqual((body["model"], body["max_completion_tokens"], body["reasoning_effort"]),
                         ("muse-spark-1.3", 2048, "low"))
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertNotIn("timeout", body)
        self.assertEqual(self.ledger()["entries"][0]["request_id"], "req_sdk")

    def test_http_errors_raise_once_without_retry(self):
        for status, billed in ((400, False), (429, False), (500, True), (503, True)):
            with self.subTest(status=status):
                seen = []

                def handler(request, status=status):
                    seen.append(request)
                    return httpx.Response(status, json={"error": {"message": "nope", "type": "server_error"}},
                                          headers={"x-request-id": f"req_{status}"})

                client = self.sdk_client(handler)
                reserve = client.prepare(MESSAGES, SCHEMA, name="song_form").reserve_usd
                with self.assertRaises(LLMResponseError) as ctx:
                    self.call(client)
                self.assertEqual((ctx.exception.kind, ctx.exception.status_code, ctx.exception.request_id),
                                 ("http", status, f"req_{status}"))
                self.assertEqual(len(seen), 1)  # max_retries=0
                entry = self.ledger()["entries"][-1]
                self.assertEqual((entry["status"], entry["request_id"]), ("failed", f"req_{status}"))
                self.assertAlmostEqual(entry["settled_usd"], reserve if billed else 0.0, places=8)

    def test_a_200_reply_that_is_not_a_json_completion_keeps_its_request_id(self):
        # an HTML page (a proxy, or a base URL missing /v1), a body that is not JSON, JSON that is no object
        for content_type, body in (("text/html", b"<html>upstream maintenance</html>"),
                                   ("application/json", b"{not json"), ("application/json", b"[1, 2]")):
            with self.subTest(content_type=content_type, body=body):
                def handler(request, content_type=content_type, body=body):
                    return httpx.Response(200, content=body,
                                          headers={"content-type": content_type, "x-request-id": "req_200"})

                client = self.sdk_client(handler)
                reserve = client.prepare(MESSAGES, SCHEMA, name="song_form").reserve_usd
                with self.assertRaises(LLMResponseError) as ctx:
                    self.call(client)
                exc = ctx.exception
                self.assertEqual((exc.kind, exc.request_id, exc.status_code), ("bad_response", "req_200", 200))
                self.assertIn(f"(content type {content_type})", str(exc))
                self.assertIsNone(exc.__context__)  # the parser's exception would hold the body
                entry = self.ledger()["entries"][-1]
                self.assertEqual((entry["status"], entry["request_id"]), ("failed", "req_200"))
                self.assertAlmostEqual(entry["settled_usd"], reserve, places=8)  # usage unknown

    def test_a_reply_json_loads_rejects_is_invalid_json_with_nothing_chained(self):
        digits = "7" * (sys.get_int_max_str_digits() + 1)  # past the limit json.loads raises a plain ValueError
        for content in ('{"title": ' + digits + ', "sections": []}', f"not JSON, and it echoes {KEY}"):
            with self.subTest(content=content[:24]):
                with self.assertRaises(LLMResponseError) as ctx:
                    self.call(self.client(FakeTransport(response(content))))
                exc = ctx.exception
                self.assertEqual((exc.kind, exc.request_id), ("invalid_json", "req_1"))
                self.assertIsNone(exc.__cause__)
                self.assertIsNone(exc.__context__)  # a JSONDecodeError holds the whole reply
                self.assertNotIn(KEY, str(exc))
                entry = self.ledger()["entries"][-1]
                self.assertEqual((entry["status"], entry["request_id"]), ("failed", "req_1"))
                self.assertAlmostEqual(entry["settled_usd"], USAGE_COST, places=8)
                self.assertEqual(Ledger(self.ledger_path).snapshot()["outstanding_usd"], 0)

    def test_any_other_failure_reading_the_reply_is_settled_logged_and_typed(self):
        crash = mock.patch.object(llm, "schema_errors", side_effect=RuntimeError(f"checker crashed on {KEY}"))
        huge = {"prompt_tokens": 10 ** 400, "completion_tokens": 1}  # too large to convert to a float price
        for reply, patch, usage_known in ((response(json.dumps(GOOD)), crash, True),
                                          (response(json.dumps(GOOD), usage=huge), contextlib.nullcontext(), False)):
            with self.subTest(usage_known=usage_known):
                client = self.client(FakeTransport(reply))
                reserve = client.prepare(MESSAGES, SCHEMA, name="song_form").reserve_usd
                with (patch, self.assertLogs("app.services.llm", "WARNING") as logs,
                      self.assertRaises(LLMResponseError) as ctx):
                    self.call(client)
                exc = ctx.exception
                self.assertEqual((exc.kind, exc.request_id), ("bad_response", "req_1"))
                self.assertIsNone(exc.__cause__)
                self.assertIsNone(exc.__context__)
                entry = self.ledger()["entries"][-1]
                self.assertEqual((entry["status"], entry["request_id"]), ("failed", "req_1"))
                self.assertAlmostEqual(entry["settled_usd"], USAGE_COST if usage_known else reserve, places=8)
                self.assertEqual(entry["usage"] is not None, usage_known)
                self.assertEqual(Ledger(self.ledger_path).snapshot()["outstanding_usd"], 0)
                (line,) = [r.getMessage() for r in logs.records if r.getMessage().startswith("llm failed")]
                self.assertIn("request_id=req_1", line)
                for text in (line, "".join(traceback.format_exception(exc)),
                             self.ledger_path.read_text(encoding="utf-8")):
                    self.assertNotIn(KEY, text)

    def test_the_key_never_appears_in_logs_errors_tracebacks_or_the_ledger(self):
        stream = io.StringIO()
        capture = logging.StreamHandler(stream)
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(capture)
        root.setLevel(logging.DEBUG)  # includes the openai SDK's own DEBUG lines
        echo = {"error": {"message": f"Incorrect API key provided: {KEY}", "type": "invalid_request_error"}}

        def echo_401(request):  # a provider that echoes the key back
            return httpx.Response(401, json=echo, headers={"x-request-id": "req_401"})

        def failure(client):
            try:
                self.call(client)
            except LLMError as exc:
                logging.getLogger("caller").exception("planner failed")  # what a route or uvicorn logs
                return exc
            self.fail("the call did not raise")

        try:
            self.call(self.sdk_client(lambda request: httpx.Response(
                200, json=response(json.dumps(GOOD)), headers={"x-request-id": "req_ok"})))
            failures = [failure(self.sdk_client(echo_401)),
                        failure(self.client(FakeTransport(TimeoutError(f"timed out, key {KEY}"))))]
            with mock.patch.object(Ledger, "settle", side_effect=LedgerError("disk full")):
                failures.append(failure(self.sdk_client(echo_401)))  # raised while settling the 401
            LLMConfig.from_env({"MODEL_API_KEY": KEY, "LLM_API_KEY": KEY})
        finally:
            root.removeHandler(capture)
            root.setLevel(old_level)
        logs = stream.getvalue()
        self.assertIn("request_id=req_ok", logs)  # the capture saw this module's lines
        self.assertIn("Request options", logs)  # and the SDK's DEBUG lines
        self.assertEqual(logs.count("planner failed\nTraceback"), 3)  # and each caller's traceback
        self.assertEqual([type(exc) for exc in failures], [LLMResponseError, LLMTimeout, LedgerError])
        self.assertIn("[redacted]", str(failures[0]))
        for exc in failures:  # nothing chains the raw SDK or transport exception
            self.assertIsNone(exc.__cause__)
            self.assertIsNone(exc.__context__)
        tracebacks = ["".join(traceback.format_exception(exc)) for exc in failures]
        for text in (logs, *tracebacks, self.ledger_path.read_text(encoding="utf-8"), repr(self.config())):
            self.assertNotIn(KEY, text)


if __name__ == "__main__":
    unittest.main()
