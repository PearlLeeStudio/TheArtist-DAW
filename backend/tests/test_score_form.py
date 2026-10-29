"""Whole-score harmony/form orchestration with a real client and fake transport only."""

import copy
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from app.models.score_import import ImportedSection
from app.services import harmony_meta, score_form, score_import
from app.services.llm import BudgetExceeded, Ledger, LLMClient, LLMConfig, LLMResponseError
from app.services.score_context import ScoreContextError, score_context, validate_score_context
from tests.test_score_assistance import draft, request, source_measure


class ScoreFormTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.form_reply = {"sections": [{"section": "intro", "startMeasure": 0, "length": 2,
                                         "evidence": "Bars 1–2 establish the tonic before the repeated phrase."},
                                        {"section": "verse", "startMeasure": 2, "length": 6,
                                         "evidence": "Bars 3–8 repeat a contrasting six-bar harmonic phrase."}]}
        self.ledger = mock.Mock(spec=Ledger)
        self.ledger.cap_usd = 25.0
        self.ledger.reserve.return_value = "fake-reservation"
        self.ledger.settle.return_value = .003
        client = LLMClient(LLMConfig(provider="meta", base_url="https://api.meta.ai/v1",
                                    model="muse-spark-1.3", api_key="test-no-network"), self.ledger, self.transport)
        patcher = mock.patch.object(harmony_meta, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        network = mock.patch("app.services.llm.OpenAITransport", side_effect=AssertionError("No network in score tests"))
        network.start()
        self.addCleanup(network.stop)

    def transport(self, body):
        self.requests.append(body)
        name = body["response_format"]["json_schema"]["name"]
        payload = json.loads(body["messages"][1]["content"])
        result = self.form_reply if name == "score_form" else {"measures": [
            {"index": bar["index"], "chords": ["Dm7b5"], "confidence": "low",
             "evidence": "D and Ab admit this possible harmonization in the whole-score context."}
            for bar in payload["measures"]]}
        return {"id": f"reply-{len(self.requests)}", "model": "muse-spark-1.3",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}, {"x-request-id": f"request-{len(self.requests)}"}

    def test_whole_score_form_is_bounded_inferred_and_attributed(self):
        source = draft(8)
        before_meta = mock.Mock()
        result = score_form.infer_score_form(source, before_meta=before_meta)
        self.assertEqual([s.section for s in result.sections], ["intro", "verse"])
        self.assertTrue(all(s.basis == "inferred" for s in result.sections))
        self.assertEqual(result.formAnalysis.requestId, "request-1")
        self.assertEqual(result.formAnalysis.sectionsProposed, 2)
        self.assertEqual(result.analysisSource, "mixed")
        self.assertEqual(result.measures, source.measures)
        before_meta.assert_called_once_with(.10)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["timeout"], 45.0)
        self.assertEqual(self.requests[0]["max_completion_tokens"], 4096)
        payload = json.loads(self.requests[0]["messages"][1]["content"])
        self.assertEqual(len(payload["measures"]), 8)
        self.assertNotIn("Private", json.dumps(payload))
        self.assertLessEqual(self.ledger.reserve.call_args.kwargs["reserved_usd"], .10)

    def test_partial_source_sections_including_unknown_types_are_preserved_and_only_gaps_are_added(self):
        source = draft(8)
        existing = ImportedSection(section=None, label="Original private heading", startMeasure=0, length=2,
                                   basis="explicit", note="Read from the score")
        source.sections = [existing]
        self.form_reply["sections"] = self.form_reply["sections"][1:]
        result = score_form.infer_score_form(source)
        self.assertEqual(result.sections[0], existing)
        self.assertEqual(result.sections[1].section, "verse")
        self.assertEqual(result.formAnalysis.sectionsProposed, 1)
        context = json.loads(self.requests[0]["messages"][1]["content"])
        self.assertEqual(context["sections"][0], {"section": None, "startMeasure": 0, "length": 2, "basis": "explicit"})
        self.assertNotIn("Original private heading", json.dumps(context))

    def test_fully_covered_sections_require_no_request_and_ambiguous_form_is_an_honest_empty_answer(self):
        source = draft(8)
        source.sections = [ImportedSection(section=None, label="Part", startMeasure=0, length=8,
                                          basis="explicit", note="")]
        self.assertIs(score_form.infer_score_form(source), source)
        self.assertEqual(self.requests, [])
        self.form_reply = {"sections": []}
        result = score_form.infer_score_form(draft(8))
        self.assertEqual(result.sections, [])
        self.assertEqual(result.formAnalysis.sectionsProposed, 0)
        self.assertIn("could not establish", result.warnings[0])

    def test_uncertain_function_can_be_a_neutral_inferred_section(self):
        self.form_reply = {"sections": [{"section": None, "startMeasure": 0, "length": 8,
                                         "evidence": "Bars 1–8 repeat one phrase; its song function is unclear."}]}
        result = score_form.infer_score_form(draft(8))
        self.assertEqual((result.sections[0].section, result.sections[0].label, result.sections[0].basis),
                         (None, "Section", "inferred"))

    def test_overlaps_out_of_range_and_empty_evidence_fail_with_the_real_request_id(self):
        for section in ({"section": "verse", "startMeasure": 7, "length": 2, "evidence": "Past end"},
                        {"section": "verse", "startMeasure": 0, "length": 4, "evidence": "Overlaps source"},
                        {"section": "verse", "startMeasure": 2, "length": 4, "evidence": " "}):
            with self.subTest(section=section):
                source = draft(8)
                source.sections = [ImportedSection(section="intro", label="Intro", startMeasure=0, length=2,
                                                  basis="explicit", note="Printed")]
                self.form_reply = {"sections": [section]}
                with self.assertRaises(LLMResponseError) as caught:
                    score_form.infer_score_form(source)
                self.assertEqual(caught.exception.request_id, f"request-{len(self.requests)}")
                self.assertEqual(len(source.sections), 1)

    def test_pipeline_reviews_two_batches_then_infers_form_with_one_combined_spend_admission(self):
        source = draft(20)
        for bar in source.measures:
            bar.chords, bar.chordBasis, bar.confidence = ["C"], "inferred", "high"
        self.form_reply = {"sections": [{"section": None, "startMeasure": 0, "length": 20,
                                         "evidence": "The twenty-bar harmonic flow is one undivided passage."}]}
        before_meta = mock.Mock()
        parsed = SimpleNamespace(measures=[source_measure(i) for i in range(20)])
        with mock.patch("app.services.score_analysis.analyze_local_score", return_value=source), \
                mock.patch("app.services.score_pdf.parse_vector_score", return_value=parsed):
            result = score_import.import_score(request(), before_meta=before_meta)
        before_meta.assert_called_once_with(.30)
        self.assertEqual(len(self.requests), 3)
        first, second, form = [json.loads(body["messages"][1]["content"]) for body in self.requests]
        self.assertEqual(first["scoreContext"], second["scoreContext"])
        self.assertEqual(len(first["scoreContext"]["measures"]), 20)
        self.assertEqual(first["scoreContext"]["measures"][0]["chords"], ["C"])
        self.assertEqual(form["measures"][0]["chords"], ["Dm7b5"])
        self.assertEqual(form["measures"][19]["analysisSource"], "local")
        self.assertEqual([m.requestId for m in result.measures[:8]], ["request-1"] * 8)
        self.assertEqual([m.requestId for m in result.measures[8:16]], ["request-2"] * 8)
        self.assertEqual(result.formAnalysis.requestId, "request-3")
        self.assertTrue(any("4 were not reviewed" in warning for warning in result.warnings))

    def test_complete_context_bounds_fail_before_any_spend_or_transport(self):
        context = score_context(draft(8))
        malformed = copy.deepcopy(context)
        malformed["measures"][1]["index"] = 9
        with self.assertRaises(ScoreContextError):
            validate_score_context(malformed)
        source = draft(512)
        for bar in source.measures:
            bar.chords = ["C7(b9,#11)"] * 16
            bar.chordBasis = "inferred"
        admission = mock.Mock()
        with mock.patch("app.services.score_analysis.analyze_local_score", return_value=source):
            with self.assertRaises(score_import.ScoreInputError) as caught:
                score_import.import_score(request(), before_meta=admission)
        self.assertEqual(caught.exception.status_code, 422)
        admission.assert_not_called()
        self.assertEqual(self.requests, [])
        self.ledger.reserve.assert_not_called()

    def test_budget_rejection_and_form_failure_never_return_a_successful_draft(self):
        reject = mock.Mock(side_effect=BudgetExceeded("no budget", spent_usd=0, outstanding_usd=0, request_usd=.30, cap_usd=.10))
        with self.assertRaises(BudgetExceeded):
            score_form.infer_score_form(draft(8), before_meta=reject)
        self.assertEqual(self.requests, [])
        self.form_reply = {"sections": [{"section": "verse", "startMeasure": 99, "length": 1, "evidence": "bad range"}]}
        with mock.patch("app.services.score_analysis.analyze_local_score", return_value=draft(8)), \
                mock.patch("app.services.score_pdf.parse_vector_score", return_value=SimpleNamespace(measures=[source_measure(i) for i in range(8)])):
            with self.assertRaises(LLMResponseError):
                score_import.import_score(request())
        self.assertEqual(len(self.requests), 2)


if __name__ == "__main__":
    unittest.main()
