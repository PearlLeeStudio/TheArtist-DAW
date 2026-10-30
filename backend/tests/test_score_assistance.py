"""Explicit local-note assistance orchestration; parser and provider are fake."""

import base64
import json
from contextvars import ContextVar
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from app.models.score_import import ImportedMeasure, ScoreImportRequest, ScoreImportResponse
from app.services.score_assistance import enrich_local_harmony
from app.services.llm import BudgetExceeded, LLMTimeout


PDF = b"%PDF-1.7\n(synthetic assistance boundary)\n%%EOF"


def request(engine="auto"):
    return ScoreImportRequest(filename="private-note-source.pdf", mimeType="application/pdf",
                              dataBase64=base64.b64encode(PDF).decode("ascii"),
                              mode="infer_harmony", engine=engine)


def draft(count):
    return ScoreImportResponse(title="Private title is not music context", key="C major",
                               timeSignature=[4, 4], model=None, requestId=None,
                               analysisSource="local", mode="infer_harmony", sections=[], warnings=[],
                               measures=[ImportedMeasure(chords=[], sourceLabel=f"Source bar {index + 1}",
                                                         needsReview=True, note="Private annotation excluded",
                                                         notes=["D4", "Ab4"], bassNotes=["D4"],
                                                         analysisSource="local") for index in range(count)])


def source_measure(index, note_count=2, *, rhythm_exact=True, warnings=()):
    return SimpleNamespace(index=index, time_signature=(4, 4), rhythm_exact=rhythm_exact,
                           warnings=list(warnings), notes=[
        SimpleNamespace(midi=62 if i % 2 == 0 else 68,
                        spelling="D4" if i % 2 == 0 else "Ab4",
                        onset=float(i // 2) / 4, duration=.25, staff=i % 2,
                        lyrics="Private source lyrics", comment="Do not send this comment")
        for i in range(note_count)
    ])


class ScoreAssistanceTest(unittest.TestCase):
    def setUp(self):
        parser = mock.patch("app.services.score_pdf.parse_vector_score")
        self.parser = parser.start()
        self.addCleanup(parser.stop)
        self.parser.return_value = SimpleNamespace(measures=[source_measure(index) for index in range(32)])
        proposer = mock.patch("app.services.harmony_meta.propose_harmony", side_effect=self.propose)
        self.proposer = proposer.start()
        self.addCleanup(proposer.stop)
        self.calls = []
        self.contexts = []
        self.empty_indices = set()
        self.proposal_confidence = "low"
        self.proposal_evidence = "Possible dyad harmonization; review required."

    def propose(self, measures, key, *, context=None, score_context=None):
        self.calls.append((measures, key, context))
        self.contexts.append(score_context)
        call = len(self.calls)
        return SimpleNamespace(model="muse-spark-1.3", request_id=f"req-assist-{call}", cost_usd=.002,
                               measures=[SimpleNamespace(index=measure["index"],
                                                         chords=() if measure["index"] in self.empty_indices else ("Dm7b5",),
                                                         confidence=self.proposal_confidence, evidence=self.proposal_evidence,
                                                         needs_review=True) for measure in measures])

    def test_batches_overlap_with_request_context_and_apply_in_source_order(self):
        marker = ContextVar('import_request', default=None)
        token = marker.set('this-request')
        self.addCleanup(marker.reset, token)
        gate = threading.Barrier(2)
        second_finished = threading.Event()
        admitted = mock.Mock()

        def concurrent(measures, key, **kwargs):
            self.assertEqual(marker.get(), 'this-request')
            admitted.assert_called_once()
            gate.wait(timeout=2)
            start = measures[0]['index']
            if start == 0:
                self.assertTrue(second_finished.wait(timeout=2))
            result = self.propose(measures, key, **kwargs)
            result.request_id = f'batch-{start}'
            if start != 0:
                second_finished.set()
            return result

        self.proposer.side_effect = concurrent
        result = enrich_local_harmony(request(), draft(20), before_meta=admitted)
        self.assertEqual([bar.requestId for bar in result.measures[:16]], ['batch-0'] * 8 + ['batch-8'] * 8)
        self.assertEqual(result.requestId, 'batch-8')
        self.assertEqual(self.contexts[0], self.contexts[1])
        self.assertEqual(len(self.calls), 2)

    def test_failure_waits_for_other_call_and_never_applies_partial_results(self):
        gate = threading.Barrier(2)
        completed = threading.Event()
        score = draft(20)
        original = score.model_dump()

        def concurrent(measures, key, **kwargs):
            gate.wait(timeout=2)
            if measures[0]['index'] == 0:
                raise LLMTimeout('first failed')
            result = self.propose(measures, key, **kwargs)
            completed.set()
            return result

        self.proposer.side_effect = concurrent
        with self.assertRaises(LLMTimeout):
            enrich_local_harmony(request(), score)
        self.assertTrue(completed.is_set())
        self.assertEqual(score.model_dump(), original)

    def test_admission_failure_starts_neither_batch(self):
        with self.assertRaises(RuntimeError):
            enrich_local_harmony(request(), draft(20), before_meta=mock.Mock(side_effect=RuntimeError('denied')))
        self.proposer.assert_not_called()

    def test_local_or_meta_mode_cannot_trigger_note_assistance(self):
        for engine in ("local", "meta"):
            with self.subTest(engine=engine):
                with self.assertRaisesRegex(ValueError, "explicitly selected auto"):
                    enrich_local_harmony(request(engine), draft(1))
        self.parser.assert_not_called()
        self.proposer.assert_not_called()

    def test_no_pending_measures_returns_the_local_draft_without_reading_or_calling_a_model(self):
        score = draft(2)
        score.measures[0].chords = ["C"]
        score.measures[0].chordBasis = "printed"
        score.measures[1].noChord = True
        before = score.model_dump()
        result = enrich_local_harmony(request(), score)
        self.assertIs(result, score)
        self.assertEqual(result.model_dump(), before)
        self.parser.assert_not_called()
        self.proposer.assert_not_called()

    def test_printed_chords_and_nc_are_preserved_but_even_confident_local_hypotheses_are_reviewed(self):
        score = draft(4)
        score.measures[0].chords = ["Am7"]
        score.measures[0].chordBasis = "inferred"
        score.measures[0].confidence = "high"
        score.measures[0].note = "A local interpretation, not a written chord."
        score.measures[2].chords = ["G7"]
        score.measures[2].chordBasis = "printed"
        score.measures[3].noChord = True
        kept = {index: score.measures[index].model_dump() for index in (2, 3)}
        original_notes = list(score.measures[1].notes)
        result = enrich_local_harmony(request(), score)
        self.assertEqual([measure["index"] for measure in self.calls[0][0]], [0, 1])
        self.assertEqual(self.calls[0][2], [{"index": 2, "chords": ["G7"]}])
        self.assertEqual(self.contexts[0]["measures"][0]["chords"], ["Am7"])
        self.assertEqual(self.contexts[0]["measures"][0]["chordBasis"], "inferred")
        self.assertEqual(result.measures[0].chords, ["Dm7b5"])
        for index, before in kept.items():
            self.assertEqual(result.measures[index].model_dump(), before)
        interpreted = result.measures[1]
        self.assertEqual(interpreted.chords, ["Dm7b5"])
        self.assertEqual(interpreted.analysisSource, "meta")
        self.assertEqual(interpreted.model, "muse-spark-1.3")
        self.assertEqual(interpreted.requestId, "req-assist-1")
        self.assertEqual(interpreted.chordBasis, "inferred")
        self.assertTrue(interpreted.needsReview)
        self.assertEqual(interpreted.notes, original_notes)
        self.assertEqual(result.analysisSource, "mixed")
        self.assertEqual(result.model, "muse-spark-1.3")

    def test_empty_missing_or_oversize_note_evidence_is_skipped_and_remaining_count_is_accurate(self):
        score = draft(5)
        self.parser.return_value.measures = [source_measure(0), source_measure(1, 0),
                                             source_measure(3, 513), source_measure(4)]
        self.empty_indices.add(4)
        result = enrich_local_harmony(request(), score)
        self.assertEqual([measure["index"] for measure in self.calls[0][0]], [0, 4])
        self.assertEqual(result.measures[4].chords, [])
        self.assertEqual(result.measures[4].chordBasis, "unreadable")
        self.assertEqual(result.measures[4].confidence, "low")
        self.assertEqual(result.measures[4].analysisSource, "meta")
        self.assertEqual(result.measures[4].model, "muse-spark-1.3")
        self.assertEqual(result.measures[4].requestId, "req-assist-1")
        self.assertIn("reviewed 2 of 5 eligible measures in 1 bounded calls", result.warnings[0])
        self.assertIn("1 received reviewable proposals", result.warnings[0])
        self.assertIn("4 remain unresolved", result.warnings[0])
        for index in (1, 2, 3):
            self.assertEqual(result.measures[index].analysisSource, "local")
            self.assertIsNone(result.measures[index].requestId)

    def test_two_calls_of_at_most_eight_targets_keep_per_measure_provenance_and_unattempted_bars(self):
        result = enrich_local_harmony(request(), draft(20))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([len(call[0]) for call in self.calls], [8, 8])
        self.assertTrue(all(sum(len(measure["notes"]) for measure in call[0]) <= 512 for call in self.calls))
        self.assertEqual([measure.requestId for measure in result.measures[:8]], ["req-assist-1"] * 8)
        self.assertEqual([measure.requestId for measure in result.measures[8:16]], ["req-assist-2"] * 8)
        self.assertTrue(all(measure.analysisSource == "meta" and measure.model == "muse-spark-1.3"
                            for measure in result.measures[:16]))
        self.assertTrue(all(not measure.chords and measure.analysisSource == "local" and measure.model is None
                            for measure in result.measures[16:]))
        self.assertEqual(result.requestId, "req-assist-2")
        self.assertIn("reviewed 16 of 20 eligible measures in 2 bounded calls", result.warnings[0])
        self.assertIn("16 received reviewable proposals", result.warnings[0])
        self.assertIn("4 were not reviewed and 4 remain unresolved", result.warnings[0])
        self.assertEqual(self.contexts[0], self.contexts[1])
        self.assertEqual(len(self.contexts[0]["measures"]), 20)
        self.assertTrue(all(not bar["chords"] for bar in self.contexts[1]["measures"]))
        # The first batch's interpretations are not silently relabeled as
        # printed evidence for the second model call.
        self.assertEqual(self.calls[1][2], [])

    def test_note_budget_splits_batches_before_512_notes_without_losing_unattempted_count(self):
        self.parser.return_value.measures = [source_measure(index, count)
                                             for index, count in enumerate((300, 300, 212, 1, 1))]
        result = enrich_local_harmony(request(), draft(5))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([sum(len(measure["notes"]) for measure in call[0]) for call in self.calls], [300, 512])
        self.assertTrue(all(len(call[0]) <= 8 for call in self.calls))
        self.assertIn("reviewed 3 of 5 eligible measures", result.warnings[0])
        self.assertIn("3 received reviewable proposals", result.warnings[0])
        self.assertIn("2 remain unresolved", result.warnings[0])

    def test_no_supported_targets_means_no_provider_call_and_an_honest_zero_attempt_summary(self):
        self.parser.return_value.measures = [source_measure(0, 0), source_measure(1, 513)]
        result = enrich_local_harmony(request(), draft(2))
        self.proposer.assert_not_called()
        self.assertEqual(result.analysisSource, "local")
        self.assertIsNone(result.model)
        self.assertIn("reviewed 0 of 2 eligible measures in 0 bounded calls", result.warnings[0])
        self.assertIn("2 remain unresolved", result.warnings[0])

    def test_provider_and_parser_failures_propagate_instead_of_returning_a_local_success(self):
        for error in (LLMTimeout("No answer"), BudgetExceeded("Budget exhausted", spent_usd=25,
                                                            outstanding_usd=0, request_usd=.03, cap_usd=25)):
            with self.subTest(error=type(error).__name__):
                self.proposer.side_effect = error
                with self.assertRaises(type(error)) as raised:
                    enrich_local_harmony(request(), draft(1))
                self.assertIs(raised.exception, error)
        self.proposer.reset_mock()
        self.parser.side_effect = ValueError("Local note evidence could not be reconstructed")
        with self.assertRaisesRegex(ValueError, "could not be reconstructed"):
            enrich_local_harmony(request(), draft(1))
        self.proposer.assert_not_called()

    def test_assistance_receives_only_musical_target_and_context_data(self):
        score = draft(2)
        score.measures[0].chords = ["G7"]
        score.measures[0].chordBasis = "printed"
        enrich_local_harmony(request(), score)
        targets, key, context = self.calls[0]
        self.assertEqual(key, "C major")
        self.assertEqual(context, [{"index": 0, "chords": ["G7"]}])
        self.assertEqual(set(targets[0]), {"index", "timeSignature", "timingIsEstimated", "readWarnings", "notes"})
        self.assertFalse(targets[0]["timingIsEstimated"])
        self.assertEqual(targets[0]["readWarnings"], [])
        self.assertEqual(set(targets[0]["notes"][0]), {"pitch", "spelling", "onset", "duration", "staff"})
        transmitted = json.dumps({"targets": targets, "key": key, "context": context})
        for private in ("private-note-source.pdf", "Private title", "Private annotation", "Private source lyrics", "Do not send"):
            self.assertNotIn(private, transmitted)

    def test_reader_uncertainty_caps_model_confidence_and_preserves_local_evidence(self):
        self.proposal_confidence = "high"
        warning = "Ottava is not applied; rhythmic timing remains approximate."
        score = draft(1)
        score.measures[0].note = warning
        original_notes = list(score.measures[0].notes)
        self.parser.return_value.measures = [source_measure(0, rhythm_exact=False, warnings=[warning])]
        result = enrich_local_harmony(request(), score)
        measure = result.measures[0]
        self.assertEqual(measure.confidence, "low")
        self.assertTrue(measure.needsReview)
        self.assertEqual(measure.analysisSource, "meta")
        self.assertEqual(measure.requestId, "req-assist-1")
        self.assertIn(warning, measure.note)
        self.assertIn("Possible dyad harmonization", measure.note)
        self.assertEqual(measure.notes, original_notes)
        self.assertTrue(self.calls[0][0][0]["timingIsEstimated"])
        self.assertIn(warning, self.calls[0][0][0]["readWarnings"])

    def test_each_source_uncertainty_flag_caps_confidence_but_certain_reading_does_not(self):
        self.proposal_confidence = "high"
        for exact, warnings, expected in ((False, [], "low"), (True, ["Unsupported notation needs review."], "low"),
                                          (True, [], "high")):
            with self.subTest(exact=exact, warnings=warnings):
                self.parser.return_value.measures = [source_measure(0, rhythm_exact=exact, warnings=warnings)]
                result = enrich_local_harmony(request(), draft(1))
                self.assertEqual(result.measures[0].confidence, expected)
                self.assertTrue(result.measures[0].needsReview)

    def test_reading_warnings_survive_long_model_evidence_and_note_length_limit(self):
        self.proposal_confidence = "high"
        self.proposal_evidence = "Model interpretation. " * 18
        warning = "Ottava span is unresolved; written pitches are not confirmed sounding octaves."
        score = draft(1)
        score.measures[0].note = "Read notes: " + ", ".join(["C4", "E4", "G4"] * 15) + ". " + warning
        self.parser.return_value.measures = [source_measure(0, warnings=[warning])]
        result = enrich_local_harmony(request(), score)
        self.assertIn(warning, result.measures[0].note)
        self.assertEqual(result.measures[0].confidence, "low")
        self.assertLessEqual(len(result.measures[0].note), 400)


if __name__ == "__main__":
    unittest.main()
