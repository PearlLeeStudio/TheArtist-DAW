import json
import os
from unittest.mock import patch

from app.services.env_flags import meta_budget_unlimited
from app.services.limits import SpendLimiter
from app.services.llm import BudgetExceeded, Ledger, LLMClient
from tests.test_llm import LLMTestCase, FakeTransport, GOOD, USAGE_COST, response


class UnlimitedBudgetTest(LLMTestCase):
    def test_default_still_enforces_caps_and_public_unlimited_is_explicit(self):
        self.assertFalse(meta_budget_unlimited({}))
        env = {"THEARTIST_PUBLIC_HOST": "1", "THEARTIST_META_UNLIMITED": "1",
               "THEARTIST_META_SESSION_LIMIT_USD": "0", "THEARTIST_META_DAILY_LIMIT_USD": "0"}
        self.assertIsNone(SpendLimiter().admit(None, estimate_usd=10, env=env))
        with self.assertRaises(ValueError):
            meta_budget_unlimited({"THEARTIST_META_UNLIMITED": "typo"})

    def test_unlimited_calls_keep_costs_tokens_and_request_ids_without_dollar_refusals(self):
        env = {"THEARTIST_META_UNLIMITED": "1", "THEARTIST_META_BUDGET_USD": "0",
               "THEARTIST_META_LEDGER": str(self.ledger_path)}
        transport = FakeTransport(response(json.dumps(GOOD)))
        with patch.dict(os.environ, env):
            ledger = Ledger.from_env()
            client = LLMClient(self.config(), ledger, transport)
            result = self.call(client, max_request_usd=.000001)
        self.assertEqual(result.data, GOOD)
        self.assertEqual(result.cost_usd, USAGE_COST)
        self.assertEqual(result.request_id, "req_1")
        self.assertIsNone(ledger.snapshot()["cap_usd"])
        self.assertEqual(ledger.snapshot()["spent_usd"], USAGE_COST)
        self.assertEqual(ledger.snapshot()["outstanding_usd"], 0)
        self.assertEqual(self.ledger()["entries"][0]["usage"]["completion_tokens"], 500)
        # Re-enabling a cap does not erase the usage recorded in development.
        with self.assertRaises(BudgetExceeded):
            Ledger(self.ledger_path, 0).reserve(label="test", provider="meta", model="muse-spark-1.3", reserved_usd=.01)
