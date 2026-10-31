import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.models.schemas import ContextMeasure, Suggestion
from app.services.chord_context import context_scores, sequence_tokens, rank_with_context
from app.services.score_completion import complete_sparse_harmony
from tests.test_score_verification import reading


class ContextTest(unittest.TestCase):
    def test_peft_context_scoring_keeps_lora_and_saved_modules_without_hf_kwargs(self):
        from app.services import inference
        from peft import LoraConfig, TaskType, get_peft_model
        torch = inference.torch
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(7)
            base = inference.MusicTransformer(vocab_size=24, d_model=16, n_heads=2,
                d_ff=32, n_layers=1, max_seq_len=32, dropout=0)
            wrapped = get_peft_model(base, LoraConfig(r=2, lora_alpha=4,
                target_modules=['w_q', 'w_v'], modules_to_save=['embedding', 'output_proj'],
                task_type=TaskType.FEATURE_EXTRACTION)).eval()
            with torch.no_grad():
                for name, parameter in wrapped.named_parameters():
                    if 'lora_B' in name or 'modules_to_save.default' in name:
                        parameter.add_(torch.randn_like(parameter) * .2)
        loaded = SimpleNamespace(model=wrapped, device='cpu')
        tokenizer = SimpleNamespace(bar_id=3, encode_chord=lambda s: {'C': 4, 'Dm': 5, 'G7': 6}[s])
        context = [ContextMeasure(measure=0, chords=['C', None]), ContextMeasure(measure=2, chords=['G7', None])]
        candidate = Suggestion(label='test', chords={'1': ['Dm', 'G7']})
        before = {name: value.clone() for name, value in wrapped.state_dict().items()}
        scores = context_scores(loaded, tokenizer, [candidate], [1], context, [1])
        self.assertEqual(len(scores), 1)
        self.assertTrue(torch.isfinite(torch.tensor(scores)).all())
        with wrapped.disable_adapter():
            plain = context_scores(loaded, tokenizer, [candidate], [1], context, [1])
        self.assertNotAlmostEqual(scores[0], plain[0], places=5)
        self.assertEqual(scores, context_scores(loaded, tokenizer, [candidate], [1], context, [1]))
        self.assertTrue(all(torch.equal(before[name], value) for name, value in wrapped.state_dict().items()))

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
