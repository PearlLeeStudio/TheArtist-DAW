"""Score completed chord sequences with the served causal Music Transformer.

This is candidate reranking, not a bidirectionally trained infilling model.
Known bars on both sides are retained in written order. No mask token is invented.
"""
from __future__ import annotations


def sequence_tokens(tokenizer, header, context, candidate, selected):
    """Return tokens and the positions whose conditional likelihood can change."""
    selected = set(selected)
    first = min(selected)
    known = {bar.measure: bar.chords for bar in context}
    ids, positions = list(header), []
    for index in sorted(set(known) | selected):
        ids.append(tokenizer.bar_id)
        chords = candidate.chords.get(str(index), []) if index in selected else known[index]
        for symbol in chords:
            if symbol is None:
                continue
            token = tokenizer.encode_chord(symbol)
            if token is None:
                raise ValueError("A context chord is outside the Music Transformer vocabulary.")
            if index >= first:
                positions.append(len(ids))
            ids.append(token)
    if not positions:
        raise ValueError("No chord tokens can be scored.")
    return ids, positions


def context_scores(loaded, tokenizer, suggestions, header, context, selected):
    """Mean log likelihood of target chords AND known later chords.

    Empty non-target bars stay empty; they are not replaced. Long/unsupported
    context raises before inference rather than silently clipping the suffix.
    """
    from app.services import inference

    prepared = [sequence_tokens(tokenizer, header, context, item, selected) for item in suggestions]
    limit = getattr(loaded.model, "max_seq_len", 512)
    if any(len(ids) > limit for ids, _ in prepared):
        raise ValueError(f"Whole-score chord comparison exceeds the {limit}-token model context.")
    scores = []
    with inference._HOSTED_INFERENCE_LOCK, inference.torch.inference_mode():
        for ids, positions in prepared:
            inputs = inference.torch.tensor([ids[:-1]], device=loaded.device)
            logits = loaded.model(inputs)[0]
            indices = inference.torch.tensor([p - 1 for p in positions], device=loaded.device)
            targets = inference.torch.tensor([ids[p] for p in positions], device=loaded.device)
            values = logits[indices].log_softmax(-1).gather(1, targets[:, None])
            scores.append(float(values.mean().item()))
    return scores


def rank_with_context(loaded, tokenizer, suggestions, header, context, selected):
    scores = context_scores(loaded, tokenizer, suggestions, header, context, selected)
    return [item for _, item in sorted(zip(scores, suggestions), key=lambda pair: -pair[0])]
