"""The discovery envelope's meta block and the Meta flag's HTTP mapping; no network."""

import base64
import json
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import app.main
from app.services import llm
from app.services.contracts import capabilities

CLIENT = TestClient(app.main.app)
KEY = "sk-capabilities-test-never-shown"
PDF = b"%PDF-1.7\n(not a vector score)\n%%EOF"


def discovered(env):
    """The capabilities data computed under exactly this environment."""
    with mock.patch.dict(os.environ, env, clear=True):
        return capabilities().model_dump(mode="json")["data"]


def body(engine):
    return {"filename": "score.pdf", "mimeType": "application/pdf",
            "dataBase64": base64.b64encode(PDF).decode("ascii"), "engine": engine}


class CapabilitiesMetaTest(unittest.TestCase):
    def test_meta_block_reports_the_flag_the_key_presence_and_the_provider_without_the_key(self):
        data = discovered({"MODEL_API_KEY": KEY})
        self.assertEqual(data["meta"], {"enabled": True, "configured": True, "provider": "meta", "model": "muse-spark-1.3"})
        self.assertNotIn(KEY, json.dumps(data))
        self.assertNotIn("MODEL_API_KEY", json.dumps(data["meta"]))
        self.assertEqual(data["tools"][0], "capabilities")  # the rest of the envelope is untouched
        self.assertTrue(any("THEARTIST_META_ENABLED=0" in text for text in data["limitations"]))

    def test_configured_is_false_without_a_key_and_enabled_is_false_with_the_flag_off(self):
        self.assertEqual(discovered({})["meta"], {"enabled": True, "configured": False, "provider": "meta",
                                                  "model": "muse-spark-1.3"})
        self.assertEqual(discovered({"MODEL_API_KEY": "   "})["meta"]["configured"], False)
        for value in ("0", "off", "False"):
            with self.subTest(value=value):
                block = discovered({"THEARTIST_META_ENABLED": value, "MODEL_API_KEY": KEY})["meta"]
                self.assertEqual((block["enabled"], block["configured"]), (False, True))
        self.assertFalse(discovered({"THEARTIST_META_ENABLED": "maybe"})["meta"]["enabled"])  # a typo disables too

    def test_a_broken_or_partner_configuration_is_reported_not_raised(self):
        broken = discovered({"LLM_PROVIDER": "nope", "MODEL_API_KEY": KEY})["meta"]
        self.assertEqual(broken, {"enabled": True, "configured": False, "provider": None, "model": None})
        no_host = discovered({"LLM_PROVIDER": "custom", "LLM_BASE_URL": "http://[::1/v1", "LLM_MODEL": "m",
                              "LLM_API_KEY": KEY})["meta"]
        self.assertEqual((no_host["configured"], no_host["provider"]), (False, None))
        baseten = discovered({"LLM_PROVIDER": "baseten", "BASETEN_API_KEY": KEY})["meta"]
        self.assertEqual(baseten, {"enabled": True, "configured": True, "provider": "baseten",
                                   "model": "meta-models/muse-spark-open-1026"})
        self.assertEqual(discovered({"LLM_PROVIDER": "baseten"})["meta"]["configured"], False)

    def test_score_import_with_the_flag_off_is_503_for_meta_engines_and_the_local_reader_still_answers(self):
        env = {"THEARTIST_META_ENABLED": "0", "MODEL_API_KEY": KEY}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "_clients", {}):
            for engine in ("meta", "auto"):
                with self.subTest(engine=engine):
                    response = CLIENT.post("/api/import/score", json=body(engine))
                    self.assertEqual(response.status_code, 503, response.text)
                    self.assertIn("disabled", response.json()["detail"])
                    self.assertIn("local reader", response.json()["detail"])
            self.assertEqual(llm._clients, {})  # nothing was built, let alone called
            local = CLIENT.post("/api/import/score", json=body("local"))
            self.assertEqual(local.status_code, 422, local.text)  # this PDF is not a vector score: a local answer
            self.assertEqual(CLIENT.get("/api/capabilities").json()["data"]["meta"]["enabled"], False)
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": KEY}, clear=True):
            self.assertEqual(CLIENT.get("/api/capabilities").json()["data"]["meta"]["enabled"], True)


if __name__ == "__main__":
    unittest.main()
