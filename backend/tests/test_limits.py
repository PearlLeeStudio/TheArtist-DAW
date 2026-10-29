"""Judge-server lockdown (THEARTIST_PUBLIC_HOST) and the daily Meta spend limits, with a temp ledger; no network."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.routing import Mount

import app.main
from app.routes import generate as generate_routes
from app.routes import score_import as score_import_routes
from app.services import limits, llm, planner, score_import
from app.services.limits import Caller, SpendLimiter
from app.services.llm import Ledger, LLMClient, LLMConfig
from app.services.score_import import ScoreInputError
from tests.test_export import spec
from tests.test_plan_api import body as plan_body
from tests.test_planner import ACCEPT, VALID_PLAN, Replies, completion
from tests.test_score_import import GOOD, body as score_body
from tests.vector_score_fixture import build_vector_score_pdf
from tests.test_section_api import sse_events

CLIENT = TestClient(app.main.app)
PLAN, PLAN_STREAM, IMPORT = "/api/plan/song", "/api/plan/song/stream", "/api/import/score"
KEY = "sk-limits-test-never-shown"
SESSION = {limits.SESSION_HEADER: "browser-a"}
JUDGE = {limits.JUDGE_CODE_HEADER: "open-sesame"}
SCORE_USAGE = {"prompt_tokens": 1000, "completion_tokens": 500}  # settles at $0.003375
_LIMIT_VARS = (limits.PUBLIC_HOST_VAR, limits.LIMITS_VAR, limits.SESSION_LIMIT_VAR, limits.DAILY_LIMIT_VAR,
               limits.JUDGE_CODE_VAR, limits.JUDGE_LIMIT_VAR, "THEARTIST_META_ENABLED", app.main.WARMUP_VAR,
               "THEARTIST_WARMUP_KEYS")


def meta_client(ledger_path, transport) -> LLMClient:
    config = LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                       api_key=KEY, key_source="MODEL_API_KEY")
    return LLMClient(config, Ledger(ledger_path, 25.0), transport)


class LimitsCase(unittest.TestCase):
    """A fresh limiter and a temp ledger per test; `env` sets the limiter's environment for the test."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="limits-test-", dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        self.ledger_path = Path(tmp.name) / "meta_ledger.json"
        self.limiter = SpendLimiter()
        self.patch(mock.patch.object(limits, "limiter", self.limiter))
        self.patch(mock.patch.dict(os.environ, {"THEARTIST_META_LEDGER": str(self.ledger_path)}))
        for name in _LIMIT_VARS:
            os.environ.pop(name, None)

    def patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def env(self, **values):
        os.environ.update(values)


class LimiterTest(LimitsCase):
    """The limiter alone: pools, the judge code, the ledger's day total and the UTC day."""

    def admit(self, caller, usd):
        return self.limiter.admit(caller, estimate_usd=usd)

    def refused(self, caller, usd, status):
        with self.assertRaises(HTTPException) as ctx:
            self.admit(caller, usd)
        self.assertEqual(ctx.exception.status_code, status, ctx.exception.detail)
        return ctx.exception

    def test_off_by_default_admits_everything_without_headers(self):
        self.assertFalse(limits.limits_enabled())
        self.assertIsNone(self.admit(None, 100.0))
        self.assertIsNone(self.admit(Caller(), 100.0))

    def test_session_allowance_counts_worst_cases_until_they_settle(self):
        self.env(THEARTIST_META_LIMITS="1")
        a = Caller(session="browser-a")
        for _ in range(10):  # the $1.00 default holds ten $0.10 planner runs
            self.assertIsNotNone(self.admit(a, 0.10))
        refusal = self.refused(a, 0.10, 429)
        self.assertIn("This session's daily Meta allowance is used up: $1.00 admitted today", refusal.detail)
        self.assertTrue(1 <= int(refusal.headers["Retry-After"]) <= 86400)
        self.assertIsNotNone(self.admit(Caller(session="browser-b"), 0.10))  # another session, its own allowance
        c = Caller(session="browser-c")
        admission = self.admit(c, 1.0)
        self.refused(c, 0.01, 429)
        self.limiter.settle(admission, 0.02)  # the run cost $0.02: the rest of the allowance is back
        self.assertIsNotNone(self.admit(c, 0.98))
        self.refused(c, 0.01, 429)

    def test_a_request_without_a_session_is_400_and_bad_numbers_are_503(self):
        self.env(THEARTIST_META_LIMITS="1", THEARTIST_META_SESSION_LIMIT_USD="0.25")
        for caller in (None, Caller(), Caller(session="x" * (limits.MAX_SESSION_CHARS + 1))):
            self.assertIn(limits.SESSION_HEADER, self.refused(caller, 0.1, 400).detail)
        a = Caller(session="a")
        self.assertIsNotNone(self.admit(a, 0.25))
        self.refused(a, 0.01, 429)
        self.env(THEARTIST_META_DAILY_LIMIT_USD="ten")
        self.assertIn("THEARTIST_META_DAILY_LIMIT_USD", self.refused(a, 0.0, 503).detail)
        self.env(THEARTIST_META_DAILY_LIMIT_USD="-1")
        self.refused(a, 0.0, 503)

    def test_judge_code_is_one_pool_of_its_own_and_a_wrong_code_is_403(self):
        self.env(THEARTIST_META_LIMITS="1", THEARTIST_JUDGE_CODE="open-sesame")
        judge = Caller(session="browser-j", judge_code="open-sesame")
        for _ in range(3):  # the $5.00 default holds three $1.35 score readings
            self.assertIsNotNone(self.admit(judge, 1.35))
        self.assertIn("The judge code's daily Meta allowance", self.refused(judge, 1.35, 429).detail)
        self.refused(Caller(judge_code="open-sesame"), 1.35, 429)  # one pool for everyone with the code, session or not
        self.assertIsNotNone(self.admit(Caller(session="browser-j"), 0.5))  # without the code: the session's own pool
        self.assertIsNotNone(self.admit(Caller(judge_code="open-sesame"), 0.5))
        self.refused(Caller(session="a", judge_code="wrong"), 0.01, 403)
        self.env(THEARTIST_JUDGE_CODE="")
        self.refused(Caller(session="a", judge_code="open-sesame"), 0.01, 403)

    def test_daily_cap_counts_the_ledgers_entries_of_the_utc_day(self):
        self.env(THEARTIST_META_LIMITS="1", THEARTIST_META_DAILY_LIMIT_USD="1.00")
        ledger = Ledger(self.ledger_path, 25.0)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="milliseconds")
        with mock.patch.object(llm, "_utc_now", return_value=yesterday):
            old = ledger.reserve(label="old", provider="meta", model="muse-spark-1.3", reserved_usd=5.0)
            ledger.settle(old, settled_usd=5.0, status="settled")
        closed = ledger.reserve(label="t", provider="meta", model="muse-spark-1.3", reserved_usd=0.5)
        ledger.settle(closed, settled_usd=0.40, status="failed")  # a failed call still cost its settlement
        ledger.reserve(label="open", provider="meta", model="muse-spark-1.3", reserved_usd=0.50)  # counts while open
        self.assertIsNotNone(self.admit(Caller(session="a"), 0.10))  # 0.40 + 0.50 + 0.10 fills the cap exactly
        refusal = self.refused(Caller(session="b"), 0.11, 429)
        self.assertIn("This server's daily Meta limit is reached: $0.90 spent or reserved today", refusal.detail)
        self.ledger_path.write_text("{not json", encoding="utf-8")
        self.assertIn("ledger", self.refused(Caller(session="c"), 0.01, 503).detail)

    def test_allowances_reset_with_the_utc_day(self):
        self.env(THEARTIST_META_LIMITS="1", THEARTIST_META_SESSION_LIMIT_USD="0.10")
        a = Caller(session="a")
        admission = self.admit(a, 0.10)
        self.refused(a, 0.01, 429)
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        with mock.patch.object(limits, "_utc_now", return_value=tomorrow):
            self.assertIsNotNone(self.admit(a, 0.10))
            self.limiter.settle(admission, 0.0)  # yesterday's run settling gives today nothing back
            self.refused(a, 0.01, 429)


class LockdownTest(LimitsCase):
    """THEARTIST_PUBLIC_HOST: 403s for the DAW, warmup and the whole-file Meta score read; MIDI download, local
    reading and the bounded auto assist stay."""

    def setUp(self):
        super().setUp()
        self.env(THEARTIST_PUBLIC_HOST="1")

    def test_daw_warmup_and_meta_score_reading_are_403(self):
        res = CLIENT.get("/api/daw/targets")
        self.assertEqual(res.status_code, 403, res.text)
        self.assertIn("No DAW on this server", res.json()["detail"])
        self.assertEqual(CLIENT.post("/api/daw/open", json={"target": "logic", "spec": spec()}).status_code, 403)
        res = CLIENT.post("/api/models/warmup")
        self.assertEqual(res.status_code, 403, res.text)
        self.assertIn("warmup", res.json()["detail"].lower())
        reader = mock.patch.object(score_import_routes, "import_score",
                                   side_effect=ScoreInputError("reached the reader", 418))
        with reader as import_score:
            res = CLIENT.post(IMPORT, json=score_body(engine="meta"))
            self.assertEqual(res.status_code, 403, res.text)
            self.assertIn("auto", res.json()["detail"])
            self.assertEqual(import_score.call_count, 0)
            for engine in ("auto", "local"):  # auto is admitted only when it is about to call Meta
                res = CLIENT.post(IMPORT, json=score_body(engine=engine))
                self.assertEqual((res.status_code, res.json()["detail"]), (418, "reached the reader"))
            self.assertEqual(import_score.call_count, 2)
        self.assertEqual(CLIENT.post("/api/export/midi", json=spec()).status_code, 200)

    def test_the_mcp_mount_is_skipped_when_the_app_is_built_for_a_public_host(self):
        locked = app.main.create_app()
        self.assertEqual([route.path for route in locked.routes if isinstance(route, Mount)], [])
        self.assertIn("/mcp", [route.path for route in app.main.app.routes if isinstance(route, Mount)])
        self.assertIn("/mcp", [route.path for route in app.main.create_app({}).routes if isinstance(route, Mount)])
        with TestClient(locked) as client:  # the lifespan runs without an MCP session manager
            self.assertEqual(client.get("/api/health").json(), {"status": "ok"})
            self.assertEqual(client.post("/mcp/", json={}).status_code, 404)
            self.assertEqual(client.get("/api/daw/targets").status_code, 403)


class PlanLimitsTest(LimitsCase):
    """The planner routes behind the limiter on a public host: the session header, 429 before any call, settlement."""

    def setUp(self):
        super().setUp()
        self.env(THEARTIST_PUBLIC_HOST="1")
        self.patch(mock.patch.object(generate_routes, "TORCH_AVAILABLE", False))  # sections come from the rules composer
        self.transport = Replies(*[completion(VALID_PLAN), completion(ACCEPT)] * 3)  # plan + judgment, three runs
        client = meta_client(self.ledger_path, self.transport)
        self.patch(mock.patch.object(planner, "get_client", return_value=client))

    def test_a_meta_run_needs_the_session_header_and_is_charged_what_it_settled_for(self):
        res = CLIENT.post(PLAN, json=plan_body())
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn(limits.SESSION_HEADER, res.json()["detail"])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(CLIENT.post(PLAN, json=plan_body(planner="rules")).status_code, 200)  # no Meta, no header
        self.env(THEARTIST_META_SESSION_LIMIT_USD="0.11")
        first = CLIENT.post(PLAN, json=plan_body(), headers=SESSION)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertGreater(first.json()["spendUsd"], 0)
        # Charged what its two calls settled for ($0.0054), not the $0.10 worst case: run two fits $0.11, run three not
        second = CLIENT.post(PLAN_STREAM, json=plan_body(), headers=SESSION)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(sse_events(second.text)[-1][0], "complete")
        third = CLIENT.post(PLAN, json=plan_body(), headers=SESSION)
        self.assertEqual(third.status_code, 429, third.text)
        self.assertIn("This session's daily Meta allowance is used up", third.json()["detail"])
        self.assertIn("retry-after", third.headers)
        self.assertEqual(len(self.transport.calls), 4)

    def test_over_the_limit_is_429_before_any_meta_call_and_the_judge_code_has_its_own_allowance(self):
        self.env(THEARTIST_META_SESSION_LIMIT_USD="0.05", THEARTIST_JUDGE_CODE="open-sesame")  # under one run's $0.10
        for route in (PLAN, PLAN_STREAM):
            res = CLIENT.post(route, json=plan_body(), headers=SESSION)
            self.assertEqual(res.status_code, 429, res.text)
            self.assertIn("worst case $0.10 would pass $0.05", res.json()["detail"])
            self.assertTrue(res.headers["content-type"].startswith("application/json"))
        self.assertEqual(self.transport.calls, [])
        res = CLIENT.post(PLAN, json=plan_body(), headers={**SESSION, **JUDGE})
        self.assertEqual(res.status_code, 200, res.text)
        res = CLIENT.post(PLAN, json=plan_body(), headers={**SESSION, limits.JUDGE_CODE_HEADER: "wrong"})
        self.assertEqual(res.status_code, 403, res.text)
        self.assertEqual(len(self.transport.calls), 2)


class ScoreImportLimitsTest(LimitsCase):
    """Meta score reading behind the limiter (THEARTIST_META_LIMITS without the public host): a $1.35 worst case."""

    def setUp(self):
        super().setUp()
        self.env(THEARTIST_META_LIMITS="1")
        self.requests = []
        client = meta_client(self.ledger_path, self.transport)
        self.patch(mock.patch.object(score_import, "get_client", return_value=client))

    def transport(self, request):
        self.requests.append(request)
        return {"id": "completion-score", "model": "muse-spark-1.3",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(GOOD)}}],
                "usage": SCORE_USAGE}, {"x-request-id": "req-score"}

    def test_meta_reading_is_metered_per_session_at_its_worst_case_and_settled_at_cost(self):
        res = CLIENT.post(IMPORT, json=score_body())  # engine meta without a session
        self.assertEqual(res.status_code, 400, res.text)
        res = CLIENT.post(IMPORT, json=score_body(), headers=SESSION)  # the $1.00 default cannot hold a $1.35 reading
        self.assertEqual(res.status_code, 429, res.text)
        self.assertIn("worst case $1.35 would pass $1.00", res.json()["detail"])
        self.assertEqual(self.requests, [])
        self.env(THEARTIST_META_SESSION_LIMIT_USD="3.00")
        for engine in ("meta", "auto", "meta"):  # settled at $0.0034 each; at their worst case only two would fit
            res = CLIENT.post(IMPORT, json=score_body(engine=engine), headers=SESSION)
            self.assertEqual(res.status_code, 200, (engine, res.text))
            self.assertEqual(res.json()["analysisSource"], "meta")
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(Ledger(self.ledger_path).snapshot()["entries"], 3)
        res = CLIENT.post(IMPORT, json=score_body(engine="local"))  # the local reader is not metered
        self.assertEqual(res.status_code, 422, res.text)

    def test_an_auto_import_the_local_reader_finishes_is_never_charged(self):
        # A readable vector PDF costs nothing, so the $1.00 default must not refuse it at Meta's worst case
        body = score_body(build_vector_score_pdf(), engine="auto", mode="infer_harmony")
        for _ in range(3):
            res = CLIENT.post(IMPORT, json=body, headers=SESSION)
            self.assertEqual(res.status_code, 200, res.text)
            self.assertEqual(res.json()["analysisSource"], "local")
        self.assertEqual(self.requests, [])
        self.assertEqual(limits.limiter.admit(Caller("browser-a"), estimate_usd=1.0).estimate_usd, 1.0)  # pool untouched


if __name__ == "__main__":
    unittest.main()
