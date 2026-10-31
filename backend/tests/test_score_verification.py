import unittest
from unittest.mock import Mock, patch

from app.models.score_import import ImportedMeasure, ScoreImportRequest, ScoreImportResponse
from app.services import score_verification as verify
from app.services.llm import LLMTimeout
from app.services.score_analysis import LocalScoreUnsupported
from app.services.score_import import ScoreInputError


def reading(source="local", *, chords=None, count=1, basis="inferred", notes=None, no_chord=False):
    return ScoreImportResponse(
        title="Private file title", key="C major", timeSignature=[4, 4], sections=[], warnings=[],
        analysisSource=source, mode="infer_harmony",
        model="muse-spark-1.3" if source == "meta" else None,
        requestId="request-check" if source == "meta" else None,
        measures=[ImportedMeasure(
            chords=chords if chords is not None else ["C"], sourceLabel=f"Bar {index + 1}",
            needsReview=False, note="Source evidence", chordBasis=basis, confidence="medium",
            notes=notes if notes is not None else ["C4", "E4", "G4"], noChord=no_chord,
            analysisSource=source, model="muse-spark-1.3" if source == "meta" else None,
            requestId="request-check" if source == "meta" else None,
        ) for index in range(count)])


class ScoreVerificationTest(unittest.TestCase):
    def test_meta_empty_bar_retains_local_hypothesis_with_visible_disagreement(self):
        result = verify.compare_readings(reading(), reading("meta", chords=[]))
        self.assertEqual(result.measures[0].chords, ["C"])
        self.assertEqual(result.measures[0].analysisSource, "local")
        self.assertEqual(result.analysisSource, "mixed")
        self.assertEqual(result.verification.disputedMeasures, [0])
        self.assertIn("Meta supplied no chord", result.measures[0].note)

    def setUp(self):
        self.request = ScoreImportRequest(filename="private-name.pdf", mimeType="application/pdf",
                                          dataBase64="", engine="verified", mode="infer_harmony")

    def test_local_precedes_one_bounded_meta_call_with_complete_musical_context(self):
        order = []
        def local(_):
            order.append("local")
            return reading(count=2)
        def meta(*args, **kwargs):
            order.append("meta")
            context = kwargs["local_context"]
            self.assertEqual(len(context["measures"]), 2)
            self.assertNotIn("title", context)
            self.assertNotIn("filename", context)
            self.assertEqual(context["measures"][0]["pitchClasses"], [0, 4, 7])
            return reading("meta", count=2)
        admit = Mock(side_effect=lambda _: order.append("admit"))
        with patch.object(verify, "analyze_local_score", side_effect=local), \
             patch.object(verify, "_import_meta_score", side_effect=meta) as call:
            result = verify.import_verified_score(self.request, {"type": "file"}, before_meta=admit)
        self.assertEqual(order, ["local", "admit", "meta"])
        call.assert_called_once()
        admit.assert_called_once_with(1.35)
        self.assertEqual(result.verification.status, "compared")

    def test_printed_symbols_and_no_chord_are_preserved_with_disagreements_flagged(self):
        for source in (reading(chords=["Cmaj7"], basis="printed"),
                       reading(chords=[], basis="printed", no_chord=True)):
            result = verify.compare_readings(source, reading("meta", chords=["Am"]))
            self.assertEqual(result.measures[0].chords, source.measures[0].chords)
            self.assertEqual(result.measures[0].noChord, source.measures[0].noChord)
            self.assertEqual(result.measures[0].analysisSource, "local")
            self.assertIsNone(result.measures[0].model)
            self.assertEqual(result.analysisSource, "mixed")
            self.assertTrue(result.measures[0].needsReview)
            self.assertEqual(result.verification.disputedMeasures, [0])

    def test_pitch_disagreement_is_visible_even_when_chord_labels_match(self):
        result = verify.compare_readings(reading(), reading("meta", notes=["C4", "Eb4", "G4"]))
        self.assertEqual(result.verification.disputedMeasures, [0])
        self.assertEqual(result.measures[0].confidence, "low")
        self.assertIn("note evidence", result.measures[0].note)

    def test_unequal_counts_never_zip_or_truncate_the_local_reading(self):
        result = verify.compare_readings(reading(count=3, basis="printed"), reading("meta", count=2))
        self.assertEqual(len(result.measures), 3)
        self.assertEqual([bar.chords for bar in result.measures], [["C"]] * 3)
        self.assertEqual(result.verification.status, "unaligned")
        self.assertEqual(result.verification.comparedMeasures, 0)
        self.assertEqual(result.verification.disputedMeasures, [0, 1, 2])

    def test_key_and_meter_disagreement_mark_every_bar(self):
        meta = reading("meta", count=2)
        meta.key, meta.timeSignature = "G major", [3, 4]
        result = verify.compare_readings(reading(count=2), meta)
        self.assertEqual(result.verification.disputedMeasures, [0, 1])
        self.assertEqual(len(result.verification.notes), 2)

    def test_unsupported_local_file_is_explicitly_not_cross_checked(self):
        with patch.object(verify, "analyze_local_score", side_effect=LocalScoreUnsupported("unsupported")), \
             patch.object(verify, "_import_meta_score", return_value=reading("meta")) as meta:
            result = verify.import_verified_score(self.request, {})
        meta.assert_called_once_with(self.request, {}, local_context=None)
        self.assertEqual(result.verification.status, "local_unavailable")
        self.assertEqual(result.verification.comparedMeasures, 0)
        self.assertTrue(result.measures[0].needsReview)

    def test_failed_meta_call_does_not_fall_back_to_successful_local_result(self):
        with patch.object(verify, "analyze_local_score", return_value=reading()), \
             patch.object(verify, "_import_meta_score", side_effect=LLMTimeout("timed out")):
            with self.assertRaises(LLMTimeout):
                verify.import_verified_score(self.request, {})

    def test_large_local_score_opens_all_bars_without_spending_or_comparison_claim(self):
        admit = Mock()
        with patch.object(verify, "analyze_local_score", return_value=reading(count=129)), \
             patch.object(verify, "_import_meta_score") as meta:
            result = verify.import_verified_score(self.request, {}, before_meta=admit)
        self.assertEqual(len(result.measures), 129)
        self.assertEqual(result.analysisSource, "local")
        self.assertEqual(result.verification.status, "local_only")
        self.assertEqual(result.verification.comparedMeasures, 0)
        admit.assert_not_called()
        meta.assert_not_called()

    def test_agreement_does_not_upgrade_confidence_or_remove_review_flags(self):
        local, meta = reading(basis="printed"), reading("meta", basis="printed")
        meta.measures[0].confidence = "low"
        meta.measures[0].needsReview = True
        result = verify.compare_readings(local, meta)
        self.assertEqual(result.measures[0].confidence, "low")
        self.assertTrue(result.measures[0].needsReview)
        self.assertEqual(result.verification.disputedMeasures, [])


if __name__ == "__main__":
    unittest.main()
