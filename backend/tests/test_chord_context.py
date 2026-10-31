import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.models.schemas import ContextMeasure, Suggestion
from app.services.chord_context import sequence_tokens, rank_with_context
from app.services.score_completion import complete_sparse_harmony
from tests.test_score_verification import reading


class ContextTest(unittest.TestCase):
    def test_written_order_preserves_both_sides_and_one_or_two_chords(self):
        tokenizer = SimpleNamespace(bar_id=3, encode_chord=lambda symbol: {"C": 10, "Dm": 11, "G7": 12}[symbol])
        context = [ContextMeasure(measure=2, chords=["G7"]), ContextMeasure(measure=0, chords=["C"]),
                   ContextMeasure(measure=1, chords=[None, None])]
        candidate = Suggestion(label="test", chords={"1": ["Dm", "G7"]})
        ids, positions = sequence_tokens(tokenizer, [1, 4], context, candidate, [1])
        self.assertEqual(ids, [1, 4, 3, 10, 3, 11, 12, 3, 12])
        self.assertEqual(positions, [5, 6, 8])
        self.assertEqual(context[1].chords, ["C"])

    def test_known_future_chord_changes_neural_candidate_ranking(self):
        from app.services import inference
        torch = inference.torch
        tokenizer = SimpleNamespace(bar_id=3, encode_chord=lambda symbol: {"C": 4, "Dm": 5, "G7": 6, "Am": 7}[symbol])
        class Model:
            max_seq_len = 32
            def __call__(self, inputs):
                logits = torch.zeros(1, inputs.shape[1], 8)
                # Prior chord probabilities equal. The fixed later chord is
                # much likelier after Dm than Am in this controlled model.
                if 5 in inputs:
                    logits[0, -1, 6] = 8
                else:
                    logits[0, -1, 6] = -8
                return logits
        candidates = [Suggestion(label="Am", chords={"1": ["Am"]}), Suggestion(label="Dm", chords={"1": ["Dm"]})]
        context = [ContextMeasure(measure=0, chords=["C"]), ContextMeasure(measure=2, chords=["G7"])]
        result = rank_with_context(SimpleNamespace(model=Model(), device="cpu"), tokenizer, candidates, [1], context, [1])
        self.assertEqual(result[0].label, "Dm")
        self.assertEqual(result[0].chords, {"1": ["Dm"]})

    def test_sparse_notes_reach_own_model_with_every_known_bar_without_overwriting_source(self):
        draft = reading(count=3, basis="printed")
        draft.measures[1].chords, draft.measures[1].notes = [], ["D4"]
        draft.measures[1].chordBasis = "unreadable"
        draft.measures[2].chords = ["G7"]
        result = SimpleNamespace(model_key="ft_f1", suggestions=[Suggestion(label="test", chords={"1": ["Dm", "Dm"]})])
        with patch("app.services.inference.generate_ai_result", return_value=result) as generate:
            completed = complete_sparse_harmony(draft)
        self.assertEqual([bar.chords for bar in generate.call_args.args[2]], [["C"], [], ["G7"]])
        self.assertEqual(completed.measures[1].chords, ["Dm"])
        self.assertEqual(completed.measures[1].notes, ["D4"])
        self.assertEqual(completed.measures[1].model, "ft_f1")
        self.assertTrue(completed.measures[1].needsReview)
        self.assertEqual(completed.measures[2].chords, ["G7"])

    def test_unread_notation_and_explicit_no_chord_never_trigger_harmonization(self):
        for draft in (reading(chords=[], notes=[]), reading(chords=[], no_chord=True)):
            with patch("app.services.inference.generate_ai_result") as generate:
                complete_sparse_harmony(draft)
            generate.assert_not_called()

    def test_unavailable_model_is_visible_and_does_not_invent_chords(self):
        draft = reading(chords=[], notes=["D4"])
        with patch("app.services.inference.generate_ai_result", return_value=None):
            result = complete_sparse_harmony(draft)
        self.assertEqual(result.measures[0].chords, [])
        self.assertIn("unavailable", result.warnings[-1])


if __name__ == "__main__":
    unittest.main()
