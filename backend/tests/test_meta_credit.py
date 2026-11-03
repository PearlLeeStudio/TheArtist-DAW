"""The credit stop line, the provider's no-credit answer, and what a paused Meta means for each path.

No network: every Meta reply comes from a fake transport or an in-process httpx mock.
"""

import base64
import json
import os
import re
import time
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from app.models.reharmonize import Change, ReharmCandidate, Slot
from app.services import limits, llm, planner, reharmonize_agent as agent
from app.services.llm import CreditExhausted, Ledger, LLMClient, LLMConfigError, LLMResponseError, SpendCapReached
from tests.test_capabilities import CLIENT, body, discovered
from tests.test_llm import GOOD, KEY, FakeTransport, LLMTestCase, response
from tests.test_reharmonize import FakeScorer, request, tool_response

PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
VECTOR_PDF = Path(__file__).resolve().parent / "fixtures" / "vector-score-c.pdf"


class PausedStateTestCase(LLMTestCase):
    """Each test starts and ends with no provider hold in this process."""

    def setUp(self):
        super().setUp()
        holds = patch.dict(llm._no_credit_until, {}, clear=True)
        holds.start()
        self.addCleanup(holds.stop)


class CreditLineTests(PausedStateTestCase):
    def reserve(self, ledger, usd, label="test"):
        return ledger.reserve(label=label, provider="meta", model="muse-spark-1.3", reserved_usd=usd)

    def test_the_line_holds_even_with_the_dollar_caps_off(self):
        ledger = Ledger(self.ledger_path, 0, unlimited=True, credit_usd=1.0)
        first = self.reserve(ledger, 0.6)
        ledger.settle(first, settled_usd=0.4, status="settled")
        with self.assertRaises(CreditExhausted) as caught:
            self.reserve(ledger, 0.65)  # 0.40 + 0.65 would pass 1.00
        self.assertEqual(str(caught.exception), llm.PAUSED_TEXT)
        self.assertNotIn("$", str(caught.exception))  # the browser never sees an amount
        second = self.reserve(ledger, 0.6)  # exactly filling the line still fits
        ledger.settle(second, settled_usd=0.57, status="settled")
        # Less than the $0.05 floor is left: Meta is paused, even for a call that would fit
        with self.assertRaises(CreditExhausted):
            self.reserve(ledger, 0.001)
        self.assertEqual(len(self.ledger()["entries"]), 2)

    def test_the_line_starts_at_the_ledger_total_when_its_value_is_first_seen(self):
        before = Ledger(self.ledger_path, 25.0)
        entry = self.reserve(before, 5.0)
        before.settle(entry, settled_usd=4.0, status="settled")
        self.reserve(before, 0.5, "crashed worker")  # left open: it stays counted
        line = Ledger(self.ledger_path, 25.0, credit_usd=1.0)
        self.assertEqual(line.credit_left(), 1.0)
        self.assertNotIn("credit", self.ledger())  # reading writes nothing
        entry = self.reserve(line, 0.6)
        self.assertEqual((self.ledger()["credit"]["usd"], self.ledger()["credit"]["base_usd"]), (1.0, 4.5))
        self.assertAlmostEqual(line.credit_left(), 0.4)
        line.settle(entry, settled_usd=0.25, status="settled")
        self.assertAlmostEqual(line.credit_left(), 0.75)
        with self.assertRaises(CreditExhausted):
            self.reserve(line, 0.8)
        # A new reading of the console restarts the line at the total recorded by then
        fresh = Ledger(self.ledger_path, 25.0, credit_usd=2.0)
        self.assertEqual(fresh.credit_left(), 2.0)
        self.reserve(fresh, 1.5)
        self.assertEqual((self.ledger()["credit"]["usd"], self.ledger()["credit"]["base_usd"]), (2.0, 4.75))

    def test_zero_pauses_at_once_and_a_bad_value_is_a_configuration_error(self):
        with self.assertRaises(CreditExhausted):
            self.reserve(Ledger(self.ledger_path, 25.0, credit_usd=0), 0.000001)
        env = {"THEARTIST_META_LEDGER": str(self.ledger_path)}
        for raw in ("-1", "nan", "inf", "plenty", "50$"):
            with self.subTest(raw=raw), self.assertRaises(LLMConfigError) as caught:
                Ledger.from_env({**env, "THEARTIST_META_CREDIT_USD": raw})
            # The text can reach the browser through the planner and Second ear: the variable, never its value
            self.assertIn("THEARTIST_META_CREDIT_USD", str(caught.exception))
            self.assertNotIn(raw, str(caught.exception))
        self.assertIsNone(Ledger.from_env(env).credit_usd)
        self.assertIsNone(Ledger.from_env(env).credit_left())
        self.assertEqual(Ledger.from_env({**env, "THEARTIST_META_CREDIT_USD": " 12.5 "}).credit_usd, 12.5)

    def test_every_role_that_spends_the_meta_account_is_held_by_the_one_line(self):
        env = {"THEARTIST_META_CREDIT_USD": "3", "THEARTIST_META_LEDGER": str(self.ledger_path),
               "THEARTIST_JUDGE_LEDGER": str(self.ledger_path.with_name("judge.json"))}
        shared = Ledger.from_env(env, role="judge")  # no provider of its own: the default client
        self.assertEqual((shared.path, shared.credit_usd), (self.ledger_path.resolve(), 3.0))
        # A judge on the meta provider spends the same key, so it reserves in the Meta ledger under the line
        meta_judge = Ledger.from_env({**env, "LLM_JUDGE_PROVIDER": "meta"}, role="judge")
        self.assertEqual((meta_judge.path, meta_judge.credit_usd), (self.ledger_path.resolve(), 3.0))
        # Without a line it keeps its own ledger and cap; a partner provider never has the Meta line
        own = Ledger.from_env({**env, "LLM_JUDGE_PROVIDER": "meta", "THEARTIST_META_CREDIT_USD": ""}, role="judge")
        self.assertEqual((own.path, own.credit_usd), (self.ledger_path.with_name("judge.json").resolve(), None))
        partner = Ledger.from_env({**env, "LLM_JUDGE_PROVIDER": "baseten"}, role="judge")
        self.assertEqual((partner.path, partner.credit_usd), (self.ledger_path.with_name("judge.json").resolve(), None))

    def test_the_client_stops_before_the_transport_once_the_line_is_reached(self):
        transport = FakeTransport(response(json.dumps(GOOD)))
        client = LLMClient(self.config(), Ledger(self.ledger_path, 25.0, unlimited=True, credit_usd=0.001), transport)
        with self.assertRaises(CreditExhausted) as caught:
            self.call(client)
        self.assertEqual(transport.calls, [])
        self.assertEqual((caught.exception.attempts, caught.exception.cost_usd), (0, 0.0))


class ProviderNoCreditTests(PausedStateTestCase):
    def test_a_402_pauses_meta_for_the_hold_and_is_not_billed(self):
        def no_credit(request):
            return httpx.Response(402, json={"error": {"message": "Your credit balance is too low", "type": "billing_error"}},
                                  headers={"x-request-id": "req_402"})

        with self.assertRaises(CreditExhausted) as caught:
            self.call(self.sdk_client(no_credit))
        self.assertEqual(caught.exception.request_id, "req_402")
        self.assertNotIn("balance", str(caught.exception))  # the provider's words go to the server log only
        entry = self.ledger()["entries"][-1]
        self.assertEqual((entry["status"], entry["settled_usd"]), ("failed", 0.0))
        # The next request stops before any network I/O, and discovery reports the pause
        transport = FakeTransport(response(json.dumps(GOOD)))
        with self.assertRaises(CreditExhausted):
            self.call(self.client(transport))
        self.assertEqual(transport.calls, [])
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": KEY, "THEARTIST_META_UNLIMITED": "1"}, clear=True):
            self.assertEqual(llm.meta_availability(), "paused")
            # When the hold ends, the next request asks Meta again
            for endpoint in llm._no_credit_until:
                llm._no_credit_until[endpoint] = time.monotonic() - 1
            self.assertIsNone(llm.meta_availability())
        self.assertEqual(llm._no_credit_until, {})
        self.assertEqual(self.call(self.client(transport)).data, GOOD)

    def test_only_the_providers_codes_pause_meta_never_its_free_text(self):
        cases = [
            (429, {"message": "You exceeded your current quota, please check your plan and billing details.",
                   "code": "insufficient_quota"}, True),
            (403, {"message": "Forbidden", "code": "credits_exhausted"}, True),
            (400, {"message": "Request refused", "type": "payment_required"}, True),
            (429, {"message": "rate limited"}, False),
            (429, {"message": "Rate limit reached. Visit https://console.example/settings/billing to raise your limits.",
                   "type": "rate_limit_error"}, False),
            # A message can echo the request (a file name): a visitor must not be able to pause everyone
            (400, {"message": "Unsupported file billing-payment-required.png: insufficient credit balance"}, False),
            (500, {"message": "billing service unavailable", "code": "insufficient_quota"}, False),
        ]
        for status, error, pauses in cases:
            with self.subTest(status=status, error=error):
                llm._no_credit_until.clear()
                client = self.sdk_client(lambda request, status=status, error=error:
                                         httpx.Response(status, json={"error": error}))
                expected = CreditExhausted if pauses else LLMResponseError
                with self.assertRaises(expected):
                    self.call(client)
                self.assertEqual(bool(llm._no_credit_until), pauses)


class DiscoveryTests(PausedStateTestCase):
    def test_a_reached_line_reports_paused_without_any_amount_and_writes_nothing(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path), "THEARTIST_META_UNLIMITED": "1"}
        open_line = discovered({**env, "THEARTIST_META_CREDIT_USD": "12.34"})
        self.assertEqual((open_line["meta"]["available"], open_line["meta"]["unavailableReason"]), (True, None))
        self.assertNotIn("12.34", json.dumps(open_line))
        self.assertTrue(discovered({**env, "THEARTIST_META_CREDIT_USD": "0.05"})["meta"]["available"])
        for credit in ("0", "0.049"):
            with self.subTest(credit=credit):
                block = discovered({**env, "THEARTIST_META_CREDIT_USD": credit})["meta"]
                self.assertEqual((block["enabled"], block["configured"]), (True, True))
                self.assertEqual((block["available"], block["unavailableReason"], block["fullFileScoreImport"]),
                                 (False, "paused", False))
                self.assertEqual(block["judge"], {"available": False, "unavailableReason": "paused"})
        self.assertEqual(discovered({**env, "THEARTIST_META_CREDIT_USD": "lots"})["meta"]["unavailableReason"],
                         "unconfigured")
        self.assertFalse(self.ledger_path.parent.exists())

    def test_discovery_says_whether_a_line_is_set_but_never_its_value(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path), "THEARTIST_META_UNLIMITED": "1"}
        for credit, expected in (("50", True), (" 7.25 ", True), ("lots", True), ("", False), ("   ", False)):
            with self.subTest(credit=credit):
                block = discovered({**env, "THEARTIST_META_CREDIT_USD": credit})["meta"]
                self.assertIs(block["creditStop"], expected)
                if credit.strip():
                    self.assertNotIn(credit.strip(), json.dumps(block))
        self.assertIs(discovered(env)["meta"]["creditStop"], False)
        self.assertFalse(self.ledger_path.parent.exists())

    def test_the_file_reader_is_offered_only_while_its_worst_case_fits(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path), "THEARTIST_META_UNLIMITED": "1"}
        tight = discovered({**env, "THEARTIST_META_CREDIT_USD": "1.0"})["meta"]  # a whole-file read reserves ~$1.45
        self.assertEqual((tight["available"], tight["fullFileScoreImport"]), (True, False))
        self.assertTrue(discovered({**env, "THEARTIST_META_CREDIT_USD": "2"})["meta"]["fullFileScoreImport"])

    def test_the_ledgers_dollar_cap_pauses_meta_too_when_the_caps_are_on(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_LEDGER": str(self.ledger_path)}
        self.assertEqual(discovered({**env, "THEARTIST_META_BUDGET_USD": "0.04"})["meta"]["unavailableReason"], "paused")
        self.assertTrue(discovered({**env, "THEARTIST_META_BUDGET_USD": "1"})["meta"]["available"])
        self.assertTrue(discovered({**env, "THEARTIST_META_BUDGET_USD": "0.04", "THEARTIST_META_UNLIMITED": "1"})
                        ["meta"]["available"])  # caps off: only a credit line would pause it

    def test_a_judge_on_another_provider_is_reported_on_its_own(self):
        env = {"THEARTIST_META_LEDGER": str(self.ledger_path), "LLM_JUDGE_PROVIDER": "baseten", "BASETEN_API_KEY": KEY,
               "THEARTIST_JUDGE_LEDGER": str(self.ledger_path.with_name("judge.json"))}
        block = discovered(env)["meta"]  # no MODEL_API_KEY: Meta is unconfigured, the Baseten judge is not
        self.assertEqual((block["available"], block["unavailableReason"]), (False, "unconfigured"))
        self.assertEqual(block["judge"], {"available": True, "unavailableReason": None})

    def test_a_paused_score_reading_is_refused_before_anything_is_sent(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_CREDIT_USD": "0", "THEARTIST_META_LEDGER": str(self.ledger_path)}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "_clients", {}), \
                mock.patch.object(llm.OpenAITransport, "__call__", side_effect=AssertionError("network")) as sent:
            response = CLIENT.post("/api/import/score", json=body("meta"))
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("paused", response.json()["detail"])
        self.assertIn("local reader", response.json()["detail"])
        self.assertNotIn("$", response.json()["detail"])
        sent.assert_not_called()

    def test_the_planner_and_second_ear_report_pauses_and_caps_without_figures(self):
        paused = CreditExhausted(llm.PAUSED_TEXT)
        self.assertEqual((planner._kind(paused), planner._message(paused)), ("disabled", llm.PAUSED_TEXT))
        cap = SpendCapReached("LLM budget cap reached: spent $9.98 + outstanding $0 + this request $0.04 > cap $10.00",
                              spent_usd=9.98, outstanding_usd=0, request_usd=0.04, cap_usd=10)
        self.assertEqual(planner._kind(cap), "budget")
        self.assertNotIn("$", planner._message(cap))
        per_request = llm.BudgetExceeded("request reservation $0.0523 exceeds the per-request cap $0.05",
                                         spent_usd=0, outstanding_usd=0, request_usd=0.0523, cap_usd=0.05)
        self.assertNotIn("$", planner._message(per_request))
        # A provider's own words can name a balance: the trace keeps the status, the log keeps the words
        refused = LLMResponseError("HTTP 400 from meta (muse-spark-1.3): Your balance is $0.03", kind="http",
                                   request_id="req_9", status_code=400)
        self.assertEqual(planner._message(refused), "Meta could not complete the request (HTTP 400)")

    def test_a_paused_verified_reading_names_the_pause_instead_of_the_file(self):
        env = {"MODEL_API_KEY": KEY, "THEARTIST_META_CREDIT_USD": "0", "THEARTIST_META_LEDGER": str(self.ledger_path)}
        png = {"filename": "score.png", "mimeType": "image/png", "engine": "verified", "dataBase64": PNG_1X1}
        pdf = {"filename": "vector-score-c.pdf", "mimeType": "application/pdf", "engine": "verified",
               "mode": "infer_harmony", "dataBase64": base64.b64encode(VECTOR_PDF.read_bytes()).decode("ascii")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "_clients", {}), \
                mock.patch.object(llm.OpenAITransport, "__call__", side_effect=AssertionError("network")) as sent:
            image = CLIENT.post("/api/import/score", json=png)
            score = CLIENT.post("/api/import/score", json=pdf)
        # An image needs Meta: the pause is named, not a file the readers could not recover
        self.assertEqual(image.status_code, 503, image.text)
        self.assertIn("paused", image.json()["detail"])
        self.assertNotIn("Neither reader", image.json()["detail"])
        # A vector PDF opens from the local reader and says why Meta did not compare it
        self.assertEqual(score.status_code, 200, score.text)
        verification = score.json()["verification"]
        self.assertEqual(verification["status"], "local_fallback")
        self.assertIn("Meta is paused on this server", verification["notes"][0])
        sent.assert_not_called()


class TokenEstimateTests(unittest.TestCase):
    def test_text_beyond_ascii_is_reserved_at_its_utf8_bytes(self):
        """A byte-level tokenizer needs at most a token per byte, so Korean, CJK or emoji in a review or a plan
        cannot bill more than the reservation the credit line admitted; ASCII keeps its estimate."""
        def tokens(text):
            return llm._estimated_text_tokens([{"role": "user", "content": text}], {})
        self.assertLess(tokens("C" * 300), 300 / 3 + 20)
        self.assertGreaterEqual(tokens("가" * 300), 3 * 300)
        self.assertGreaterEqual(tokens("🎵" * 300), 4 * 300)
        self.assertGreaterEqual(tokens("\ud800" * 3), 9)  # a lone surrogate is counted, not an encoding error


class HostedStopLineTests(unittest.TestCase):
    COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "compose.yaml"

    def test_the_hosted_app_carries_a_stop_line_that_the_server_env_file_can_replace(self):
        app_service = self.COMPOSE.read_text(encoding="utf-8").split("\n  https:\n")[0]
        found = re.search(r"^      THEARTIST_META_CREDIT_USD: \$\{THEARTIST_META_CREDIT_USD:-([^}]+)\}$",
                          app_service, re.M)
        self.assertIsNotNone(found, "the hosted app service must set a default credit stop line")
        default = float(found.group(1))
        Ledger(self.COMPOSE.with_name("never-written.json"), credit_usd=default)  # the server's own value check
        self.assertGreater(default, 1.45)  # room for a whole-file read's worst case, so the reader is offered


def candidate(id, family, after, score, slot=0):
    return ReharmCandidate(id=id, family=family, changes=[Change(
        address=Slot(measureIndex=1, slotIndex=slot), before="Dm7", after=after, commonTones=2, modes=[])],
        pitchDistance=0, originalPitchDistance=0, bassMotion=0, originalBassMotion=0, mathScore=0, modelScore=score)


def costly_search(calls):
    """A transport that answers every turn with a search billed at 10,000 input and 4,000 output tokens
    ($0.0295), more than the first turn's ~$0.022 estimate, as a long tool history can be."""
    def transport(body):
        calls.append(body)
        reply = tool_response("search_substitutions", {"families": ["common_tones", "modal"]})
        reply["usage"] = {"prompt_tokens": 10000, "completion_tokens": 4000}
        return reply, {"x-request-id": f"req-{len(calls)}"}
    return transport


class ReharmonizeWithoutMetaTests(PausedStateTestCase):
    def assert_local(self, result, reason):
        self.assertEqual((result.selection, result.metaUnavailable, result.metaModel), ("local", reason, "not used"))
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(len({c.id for c in result.candidates}), 3)
        scores = [c.modelScore for c in result.candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_a_paused_meta_is_never_called_and_the_three_are_chosen_from_every_family(self):
        with patch.object(agent.llm, "meta_availability", return_value="paused"), \
                patch.object(agent.llm, "get_client", side_effect=AssertionError("Meta must not be called")):
            result = agent.propose(request(), scorer=FakeScorer())
        self.assert_local(result, "paused")
        self.assertEqual((result.requestIds, result.costUsd, result.toolCalls), ([], 0.0, []))
        self.assertEqual({c.family for c in result.candidates}, {"common_tones", "modal", "dominant"})

    def test_a_stop_during_the_search_keeps_the_meta_record_and_finishes_without_meta(self):
        # The first turn fits; its spend leaves the credit line under its floor, or no room under the dollar
        # cap for the second. The line refuses with CreditExhausted, the cap with SpendCapReached
        for ledger in (Ledger(self.ledger_path, 25.0, credit_usd=0.07), Ledger(self.ledger_path, 0.04)):
            with self.subTest(credit=ledger.credit_usd, cap=ledger.cap_usd):
                if self.ledger_path.exists():
                    self.ledger_path.unlink()
                calls = []
                client = LLMClient(self.config(), ledger, costly_search(calls))
                result = agent.propose(request(), client=client, scorer=FakeScorer())
                self.assertEqual(len(calls), 1)
                self.assert_local(result, "paused")
                self.assertEqual((result.requestIds, result.toolCalls), (["req-1"], ["search_substitutions"]))
                self.assertGreater(result.costUsd, 0)

    def test_an_explicit_client_without_a_key_and_a_used_up_allowance_skip_meta(self):
        transport = FakeTransport(tool_response("search_substitutions", {"families": ["common_tones", "modal"]}))
        self.assert_local(agent.propose(request(), client=self.client(transport, api_key=""), scorer=FakeScorer()),
                          "unconfigured")
        with patch.object(agent.llm, "get_client", side_effect=AssertionError("Meta must not be called")):
            self.assert_local(agent.propose(request(), scorer=FakeScorer(), meta_allowed=False), "limit")
        self.assertEqual(transport.calls, [])

    def test_the_route_answers_a_used_up_allowance_without_meta_and_keeps_other_refusals(self):
        from app.routes.reharmonize import reharmonize_route
        with patch("app.routes.reharmonize.limits.limiter") as limiter, \
                patch.object(agent.llm, "meta_availability", return_value=None), \
                patch.object(agent, "ContextScorer", return_value=FakeScorer()), \
                patch.object(agent.llm, "get_client", side_effect=AssertionError("Meta must not be called")):
            limiter.admit.side_effect = HTTPException(status_code=429, detail="allowance used up")
            self.assert_local(reharmonize_route(request()), "limit")
            limiter.settle.assert_called_once_with(None, 0.0)
            # The limiter cannot read its ledger, or refuses its settings: the search still runs without Meta
            for detail, reason in ((limits.LEDGER_UNREADABLE, "paused"),
                                   ("Meta limits are misconfigured: THEARTIST_META_DAILY_LIMIT_USD must be a "
                                    "non-negative number", "unconfigured")):
                with self.subTest(reason=reason):
                    limiter.admit.side_effect = HTTPException(status_code=503, detail=detail)
                    self.assert_local(reharmonize_route(request()), reason)
            limiter.admit.side_effect = HTTPException(status_code=400, detail="no session id")
            with self.assertRaises(HTTPException) as caught:
                reharmonize_route(request())
            self.assertEqual(caught.exception.status_code, 400)

    def test_a_search_that_will_not_call_meta_asks_no_admission(self):
        from app.routes.reharmonize import reharmonize_route
        with patch("app.routes.reharmonize.limits.limiter") as limiter, \
                patch.object(agent.llm, "meta_availability", return_value="paused"), \
                patch.object(agent, "ContextScorer", return_value=FakeScorer()):
            limiter.admit.side_effect = AssertionError("no admission for a search without Meta")
            self.assert_local(reharmonize_route(request()), "paused")
            limiter.admit.assert_not_called()

    def test_a_ledger_that_cannot_be_written_picks_without_meta_and_names_no_path(self):
        transport = FakeTransport(tool_response("search_substitutions", {"families": ["common_tones", "modal"]}))
        client = self.client(transport)
        failure = llm.LedgerError(f"cannot write the ledger {self.ledger_path}: [Errno 28] No space left on device")
        with patch.object(Ledger, "reserve", side_effect=failure):
            result = agent.propose(request(), client=client, scorer=FakeScorer())
        self.assert_local(result, "paused")
        self.assertNotIn(str(self.ledger_path), result.model_dump_json())
        self.assertEqual(transport.calls, [])
        # Any ledger fault that still reaches the route is named without the path
        from app.routes.reharmonize import reharmonize_route
        with patch("app.routes.reharmonize.limits.limiter"), patch.object(agent.llm, "meta_availability", return_value=None), \
                patch.object(agent, "propose", side_effect=failure), self.assertRaises(HTTPException) as caught:
            reharmonize_route(request())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn(str(self.ledger_path), caught.exception.detail)

    def test_a_providers_error_words_stay_out_of_the_search_error(self):
        from app.routes.reharmonize import reharmonize_route
        refused = LLMResponseError("HTTP 400 from meta (muse-spark-1.3): Your balance is $0.03", kind="http",
                                   request_id="req_9", status_code=400)
        with patch("app.routes.reharmonize.limits.limiter"), patch.object(agent.llm, "meta_availability", return_value=None), \
                patch.object(agent, "propose", side_effect=refused), self.assertRaises(HTTPException) as caught:
            reharmonize_route(request())
        self.assertEqual((caught.exception.status_code, caught.exception.detail),
                         (502, "Meta could not complete the search (HTTP 400, request req_9)."))

    def test_a_no_credit_answer_mid_search_keeps_its_request_id(self):
        replies = iter([
            httpx.Response(200, json=tool_response("search_substitutions", {"families": ["common_tones", "modal"]}),
                           headers={"x-request-id": "req-1"}),
            httpx.Response(402, json={"error": {"type": "billing_error", "message": "no credit"}},
                           headers={"x-request-id": "req_402"}),
        ])
        result = agent.propose(request(), client=self.sdk_client(lambda request: next(replies)), scorer=FakeScorer())
        self.assert_local(result, "paused")
        self.assertEqual(result.requestIds, ["req-1", "req_402"])

    def test_the_searchs_own_cost_cap_stays_an_error_named_without_figures(self):
        from app.routes.reharmonize import reharmonize_route
        over = llm.BudgetExceeded("request reservation $0.2000 exceeds the per-request cap $0.1300",
                                  spent_usd=0, outstanding_usd=0, request_usd=.2, cap_usd=.13)
        with patch("app.routes.reharmonize.limits.limiter"), patch.object(agent, "propose", side_effect=over), \
                self.assertRaises(HTTPException) as caught:
            reharmonize_route(request())
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.detail, "The reharmonization search reached its cost limit.")

    def test_too_few_substitutes_without_meta_is_a_plain_error(self):
        with patch.object(agent, "search", return_value=[]), self.assertRaisesRegex(ValueError, "Only 0 substitutes"):
            agent.propose(request(), scorer=FakeScorer(), meta_allowed=False)

    def test_local_choice_spans_families_and_roots_before_repeating_one(self):
        pool = [candidate("a", "common_tones", "F6", -1.0), candidate("b", "common_tones", "Fmaj7", -1.1),
                candidate("d", "modal", "Fm", -1.2), candidate("e", "modal", "Bbmaj7", -2.0),
                candidate("c", "dominant", "Ab7", -3.0)]
        # modal's best (Fm) repeats a's root on the same slot, so its next candidate is offered instead
        self.assertEqual([c.id for c in agent.local_choice(pool)], ["a", "e", "c"])
        one_family = [candidate("a", "common_tones", "F6", -1.0), candidate("b", "common_tones", "Fmaj7", -1.1),
                      candidate("x", "common_tones", "Am7", -2.0)]
        # a repeated root is offered only when nothing else is left; the three stay in score order
        self.assertEqual([c.id for c in agent.local_choice(one_family)], ["a", "b", "x"])


if __name__ == "__main__":
    unittest.main()
