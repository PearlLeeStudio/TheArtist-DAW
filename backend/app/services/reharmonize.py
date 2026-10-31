"""Bounded harmonic search followed by learned, two-sided sequence reranking.

The pitch distance is a symmetric nearest-pitch-class proxy, not performed voice
leading. Mode labels mean set membership in parallel modes of the stated tonic,
not a claim that a mode was detected. No melody is inferred from chord symbols.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations
import re

from app.models.reharmonize import Change, ReharmCandidate, ReharmRequest, Slot

ROOTS = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
INTERVALS = {
    "maj": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10), "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9), "dim": (0, 3, 6),
    "aug": (0, 4, 8), "sus4": (0, 5, 7), "sus2": (0, 2, 7), "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9), "9": (0, 2, 4, 7, 10), "m9": (0, 2, 3, 7, 10),
    "maj9": (0, 2, 4, 7, 11), "11": (0, 2, 4, 5, 7, 10), "m11": (0, 2, 3, 5, 7, 10),
    "13": (0, 2, 4, 5, 7, 9, 10), "m13": (0, 2, 3, 5, 7, 9, 10),
    "add9": (0, 2, 4, 7), "mMaj7": (0, 3, 7, 11),
    "7b9": (0, 1, 4, 7, 10), "7#9": (0, 3, 4, 7, 10),
    "7#11": (0, 4, 6, 7, 10), "7b13": (0, 4, 7, 8, 10),
}
ALIASES = {"": "maj", "min": "m", "min7": "m7", "min9": "m9", "min11": "m11",
           "min13": "m13", "min6": "m6", "mM7": "mMaj7", "minmaj7": "mMaj7", "M7": "maj7",
           "M9": "maj9", "sus": "sus4"}
MODES = {
    "ionian": (0, 2, 4, 5, 7, 9, 11), "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10), "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10), "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}
_SYMBOL = re.compile(r"([A-G][#b]?)([^/]*)(?:/([A-G][#b]?))?\Z")


def pitch(note: str) -> int:
    return (NATURAL[note[0]] + {"": 0, "#": 1, "b": -1}[note[1:]]) % 12


@lru_cache(maxsize=2048)
def chord(symbol: str) -> tuple[int, frozenset[int], int, str]:
    match = _SYMBOL.fullmatch(symbol)
    if not match:
        raise ValueError(f"Unsupported chord symbol for substitution search: {symbol}")
    root, quality, bass = match.groups()
    quality = quality.replace("(", "").replace(")", "")
    quality = ALIASES.get(quality, quality)
    if quality not in INTERVALS:
        raise ValueError(f"Unsupported chord quality for substitution search: {symbol}")
    root_pc = pitch(root)
    pcs = frozenset({(root_pc + interval) % 12 for interval in INTERVALS[quality]} | ({pitch(bass)} if bass else set()))
    return root_pc, pcs, pitch(bass) if bass else root_pc, quality


def distance(a: int, b: int) -> int:
    return min((a - b) % 12, (b - a) % 12)


def pitch_distance(a: frozenset[int], b: frozenset[int]) -> float:
    return (sum(min(distance(p, q) for q in b) for p in a) / len(a)
            + sum(min(distance(q, p) for p in a) for q in b) / len(b)) / 2


def context_window(req: ReharmRequest):
    first = min(s.measureIndex for s in req.selectedSlots)
    last = max(s.measureIndex for s in req.selectedSlots)
    return [bar for bar in req.context if first - 8 <= bar.measure <= last + 8]


def _metrics(symbols, changed):
    edges = {(i - 1, i) for i in changed if i > 0} | {(i, i + 1) for i in changed if i + 1 < len(symbols)}
    edges = [(a, b) for a, b in sorted(edges) if symbols[a] and symbols[b]]
    if not edges:
        return 0.0, 0.0
    pairs = [(chord(symbols[a]), chord(symbols[b])) for a, b in edges]
    return (sum(pitch_distance(a[1], b[1]) for a, b in pairs) / len(pairs),
            sum(distance(a[2], b[2]) for a, b in pairs) / len(pairs))


def search(req: ReharmRequest, family: str, *, limit: int = 6) -> list[ReharmCandidate]:
    """Enumerate only selected occupied slots; every result changes at most 1–2 symbols."""
    if family not in ("common_tones", "modal", "dominant"):
        raise ValueError("Unknown substitution family.")
    symbols = [symbol for bar in req.context for symbol in bar.chords]
    # Validate precisely the same local context that the model will score.
    for bar in context_window(req):
        for symbol in bar.chords:
            if symbol:
                chord(symbol)
    tonic = pitch(req.key.split()[0])
    scales = {name: {(tonic + p) % 12 for p in scale} for name, scale in MODES.items()}
    home = scales["aeolian" if req.key.endswith("minor") else "ionian"]
    selected = sorted(s.measureIndex * 2 + s.slotIndex for s in req.selectedSlots)

    def make(replacements):
        version = list(symbols)
        changes = []
        for i, after in sorted(replacements):
            before = symbols[i]
            before_pcs, after_pcs = chord(before)[1], chord(after)[1]
            version[i] = after
            changes.append(Change(address=Slot(measureIndex=i // 2, slotIndex=i % 2), before=before, after=after,
                                  commonTones=len(before_pcs & after_pcs),
                                  modes=[name for name, scale in scales.items() if after_pcs <= scale]))
        indexes = [i for i, _ in replacements]
        motion, bass = _metrics(version, indexes)
        old_motion, old_bass = _metrics(symbols, indexes)
        shared = sum(c.commonTones / len(chord(c.before)[1]) for c in changes) / len(changes)
        # Less movement and shared tones are useful pruning heuristics, never quality probabilities.
        score = 2 * shared - motion - .12 * bass - .15 * (len(changes) - 1)
        identity = ";".join(f"{i}:{symbol}" for i, symbol in sorted(replacements))
        return ReharmCandidate(id=identity, family=family, changes=changes,
                               pitchDistance=round(motion, 3), originalPitchDistance=round(old_motion, 3),
                               bassMotion=round(bass, 3), originalBassMotion=round(old_bass, 3),
                               mathScore=round(score, 4))

    singles = []
    for i in selected:
        root, original, bass, quality = chord(symbols[i])
        following = chord(symbols[i + 1]) if i + 1 < len(symbols) and symbols[i + 1] else None
        options = []
        for candidate_root in ROOTS:
            for candidate_quality in INTERVALS:
                after = candidate_root + candidate_quality
                cr, pcs, cb, cq = chord(after)
                # Keep an explicitly written pedal/inversion bass; it is not an invitation to replace it.
                if "/" in symbols[i]:
                    after += "/" + symbols[i].split("/")[1]
                    cr, pcs, cb, cq = chord(after)
                if pcs == original and cb == bass:
                    continue
                common = len(pcs & original)
                if req.mode != "auto" and not pcs <= scales[req.mode]:
                    continue
                if family == "common_tones" and common < 2:
                    continue
                if family == "modal" and (pcs <= home or not any(pcs <= s for s in scales.values()) or common < 1):
                    continue
                if family == "dominant":
                    dominant = {"7", "9", "13", "7b9", "7#9", "7#11", "7b13"}
                    tritone = quality in dominant and cq in dominant and (cr - root) % 12 == 6
                    approaches = following and cq in dominant and (cr - following[0]) % 12 in (1, 7)
                    if not (tritone or approaches):
                        continue
                # Reject needless density jumps before any neural/API work.
                if abs(len(pcs) - len(original)) > 1:
                    continue
                options.append(make([(i, after)]))
        singles.extend(sorted(options, key=lambda c: (-c.mathScore, c.id))[:6])
    candidates = list(singles)
    if req.maxChanges == 2:
        # Bounded beam: pair only the best single changes, then recompute shared boundaries.
        for a, b in combinations(sorted(singles, key=lambda c: -c.mathScore)[:12], 2):
            ca, cb = a.changes[0], b.changes[0]
            ia, ib = ca.address.measureIndex * 2 + ca.address.slotIndex, cb.address.measureIndex * 2 + cb.address.slotIndex
            if ia != ib:
                candidates.append(make([(ia, ca.after), (ib, cb.after)]))
    candidates.sort(key=lambda c: (-c.mathScore, c.id))
    # Avoid presenting only extensions of one root as the entire shortlist.
    result, signatures = [], set()
    for item in candidates:
        signature = tuple((c.address.measureIndex, c.address.slotIndex, chord(c.after)[0]) for c in item.changes)
        if signature not in signatures:
            signatures.add(signature)
            result.append(item)
        if len(result) == limit:
            break
    return result


class ContextScorer:
    """Load one chosen checkpoint once, and score only a small mathematical shortlist."""
    def __init__(self, req: ReharmRequest):
        from app.services import inference
        key = req.modelKey or inference.DEFAULT_MODEL
        if key not in inference.CHECKPOINTS:
            raise ValueError("Unknown Music Transformer checkpoint.")
        registry = inference.ModelRegistry.get()
        self.loaded = registry.load_model(key)
        if self.loaded is None:
            raise ValueError("The selected Music Transformer is unavailable; no fallback candidates were returned.")
        self.tokenizer = registry.tokenizer
        self.label = inference.MODEL_LABELS.get(key, key)
        # Project exact parsed qualities into the trained chord vocabulary. Slash
        # bass is handled by the mathematical score; this tokenizer has no bass tokens.
        self.context = [bar.model_copy(update={"chords": [self._token_symbol(s) if s else None for s in bar.chords]})
                        for bar in context_window(req)]
        self.header = inference.build_prompt(self.tokenizer, req.key, None, req.timeSignature, [], [])
        self.selected = sorted({s.measureIndex for s in req.selectedSlots})
        self.cache = {}

    @staticmethod
    def _token_symbol(symbol):
        root, _, _, quality = chord(symbol)
        return ROOTS[root] + quality

    def score(self, candidates):
        from app.models.schemas import Suggestion
        from app.services.chord_context import context_scores
        missing = [c for c in candidates if c.id not in self.cache]
        suggestions = []
        for item in missing:
            bars = {str(b.measure): list(b.chords) for b in self.context if b.measure in self.selected}
            for change in item.changes:
                bars[str(change.address.measureIndex)][change.address.slotIndex] = self._token_symbol(change.after)
            # sequence_tokens understands nulls, even though the older Suggestion schema does not.
            suggestions.append(Suggestion.model_construct(label=item.id, chords=bars))
        if suggestions:
            scores = context_scores(self.loaded, self.tokenizer, suggestions, self.header, self.context, self.selected)
            self.cache.update({c.id: score for c, score in zip(missing, scores)})
        return sorted([c.model_copy(update={"modelScore": round(self.cache[c.id], 5)}) for c in candidates],
                      key=lambda c: -c.modelScore)
