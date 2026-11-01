"""Compare the pre-speed loader supplied on stdin with the installed runtime.

Run in the CPU serving image with PYTHONPATH pointing to backend. No Meta calls,
downloads, checkpoint writes or service restarts. Retain all optimized models;
release each reference model before loading the next one to bound memory.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute():
        parser.error('--out must be absolute')
    from app.services import inference, chord_context
    from app.models.schemas import ContextMeasure, Suggestion
    torch = inference.torch
    torch.set_num_threads(2)
    source = sys.stdin.read()
    legacy = types.ModuleType('reference_inference')
    legacy.__file__ = inference.__file__
    sys.modules[legacy.__name__] = legacy
    exec(compile(source, inference.__file__, 'exec'), legacy.__dict__)
    registry = inference.ModelRegistry()
    tokenizer = registry.tokenizer
    rows = []

    def bare(loaded):
        return loaded.model.get_base_model() if isinstance(loaded.model, inference.PeftModel) else loaded.model

    def digest(model, inputs):
        with torch.inference_mode():
            return hashlib.sha256(model(inputs).numpy().tobytes()).hexdigest()

    context = [ContextMeasure(measure=i, chords=row) for i, row in enumerate([
        ['Cmaj7', 'Am7'], ['Dm7', 'G7'], ['C', None], ['F', 'G7'], ['Cmaj7', 'C']])]
    candidates = [Suggestion.model_construct(label=str(i), chords={'1': chords}) for i, chords in enumerate([
        ['Dm7', 'G7'], ['Fm7', 'Bb7'], ['Dm7b5', 'G7'], ['Dm7', None], ['Dm7', 'G7'], ['F', 'G7']])]
    header = inference.build_prompt(tokenizer, 'C major', None, (4, 4), [], [])
    prompt = torch.tensor([inference.build_prompt(tokenizer, 'C major', 'pop', (4, 4), context[:1], [1])])
    for key in inference.CHECKPOINTS:
        reference = legacy.ModelRegistry().load_model(key)
        loaded = registry.load_model(key)
        assert reference and loaded and reference.name == loaded.name == key
        old, new = bare(reference), bare(loaded)
        old_state, new_state = old.state_dict(), new.state_dict()
        assert old_state.keys() == new_state.keys(), key
        assert all(torch.equal(value, new_state[name]) for name, value in old_state.items()), key
        expected_hash = digest(old, prompt)
        assert digest(new, prompt) == expected_hash, key
        for seed in (17, 29):
            options = dict(max_new_tokens=30, temperature=.9, top_p=.9, use_cache=True,
                           repetition_penalty=1.2, no_repeat_ngram_size=3)
            before = old.generate(prompt, generator=torch.Generator().manual_seed(seed), **options)
            after = new.generate(prompt, generator=torch.Generator().manual_seed(seed), **options)
            assert torch.equal(before, after), (key, seed)
        expected_scores = []
        with torch.inference_mode():
            for candidate in candidates:
                ids, positions = chord_context.sequence_tokens(tokenizer, header, context, candidate, [1])
                logits = old(torch.tensor([ids[:-1]]))[0]
                indices = torch.tensor([p-1 for p in positions])
                targets = torch.tensor([ids[p] for p in positions])
                expected_scores.append(float(logits[indices].log_softmax(-1).gather(1, targets[:, None]).mean()))
        actual_scores = chord_context.context_scores(loaded, tokenizer, candidates, header, context, [1])
        torch.testing.assert_close(torch.tensor(actual_scores), torch.tensor(expected_scores), rtol=1e-5, atol=1e-6)
        rank = lambda values: sorted(range(len(values)), key=lambda i: -round(values[i], 5))
        assert rank(expected_scores) == rank(actual_scores), key
        row = dict(model=key, weights_equal=True, logits_sha256=expected_hash,
                   seeded_generations_equal=2, candidate_order_equal=True,
                   maximum_score_difference=max(abs(a-b) for a, b in zip(actual_scores, expected_scores)))
        rows.append(row)
        print(json.dumps(row), flush=True)
        del reference, old, old_state, new_state, before, after, logits
        gc.collect()
    # Loading every other adapter must leave earlier checkpoints untouched.
    for row in rows:
        assert digest(bare(registry.load_model(row['model'])), prompt) == row['logits_sha256'], row['model']
    report = dict(reference_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  models=len(rows), all_models_retained=True, cross_model_mutation=False,
                  torch=torch.__version__, device='cpu', threads=2, cases=rows)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('All checkpoint weights, seeded samples, rankings and post-load isolation checks passed.', flush=True)


if __name__ == '__main__':
    main()
