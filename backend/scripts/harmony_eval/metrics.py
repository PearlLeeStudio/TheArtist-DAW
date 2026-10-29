"""Slot scoring and aggregation.

Truth and proposal are both aligned to the editor's two slots per bar. Matches
are cumulative down the chord: a triad match needs the root, a seventh match the
triad, and exact needs all of those plus the bass; the bass is also scored on its
own, so an inversion heard as the wrong chord over the right bass still counts
there. A slot without a proposal counts as wrong in the "all" columns and is left
out of the "covered" ones. A truth slot whose symbol does not normalize is left out
of every column and counted as unscored truth.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from scripts.harmony_eval.chords import Chord, align, normalize

FIELDS = ("root", "triad", "seventh", "bass", "exact")
CONFIDENCE_LEVELS = ("high", "medium", "low")


@dataclass(frozen=True)
class SlotScore:
    covered: bool
    unparseable: bool
    root: bool
    triad: bool
    seventh: bool
    bass: bool
    exact: bool
    confidence: str | None


def score_slot(truth: Chord, proposal: str | None, confidence: str | None) -> SlotScore:
    if proposal is None:
        return SlotScore(False, False, False, False, False, False, False, None)
    chord = normalize(proposal)
    if chord is None:
        return SlotScore(True, True, False, False, False, False, False, confidence)
    root = chord.root == truth.root
    triad = root and chord.triad == truth.triad
    seventh = triad and chord.seventh == truth.seventh
    bass = chord.bass == truth.bass
    return SlotScore(True, False, root, triad, seventh, bass, seventh and bass, confidence)


def score_bar(truth_chords: Sequence[str | None], proposal_chords: Sequence[str | None],
              confidence: str | None) -> list[SlotScore]:
    """The two slot scores of a bar; empty when the truth itself has no two-slot form or no parseable symbol."""
    truth_slots = align(truth_chords)
    if truth_slots[0] is None:
        return []
    proposal_slots = align(proposal_chords)
    scores = []
    for truth_symbol, proposal in zip(truth_slots, proposal_slots):
        truth = normalize(truth_symbol)
        if truth is not None:
            scores.append(score_slot(truth, proposal, confidence))
    return scores


def unscored_slots(truth_chords: Sequence[str | None]) -> int:
    """Truth slots score_bar leaves out because their symbol does not normalize."""
    truth_slots = align(truth_chords)
    if truth_slots[0] is None:
        return 0
    return sum(normalize(symbol) is None for symbol in truth_slots)


class Tally:
    """Counts over slot scores, with the accuracy of each confidence level kept apart.

    add_bar also counts the truth slots left unscored, so an unreadable truth symbol shows
    in the summary instead of silently shrinking the slot count.
    """

    def __init__(self) -> None:
        self.slots = 0
        self.covered = 0
        self.unparseable = 0
        self.unscored_truth = 0
        self.hits: Counter[str] = Counter()
        self.by_confidence: dict[str, Counter[str]] = {}

    def add_bar(self, truth_chords: Sequence[str | None], proposal_chords: Sequence[str | None],
                confidence: str | None) -> list[SlotScore]:
        scores = score_bar(truth_chords, proposal_chords, confidence)
        self.extend(scores)
        self.unscored_truth += unscored_slots(truth_chords)
        return scores

    def add(self, score: SlotScore) -> None:
        self.slots += 1
        if not score.covered:
            return
        self.covered += 1
        self.unparseable += score.unparseable
        for name in FIELDS:
            self.hits[name] += getattr(score, name)
        if score.confidence is not None:
            level = self.by_confidence.setdefault(score.confidence, Counter())
            level["slots"] += 1
            level["root"] += score.root
            level["exact"] += score.exact

    def extend(self, scores: Iterable[SlotScore]) -> None:
        for score in scores:
            self.add(score)

    def summary(self) -> dict:
        all_slots = {name: _ratio(self.hits[name], self.slots) for name in FIELDS}
        covered = {name: _ratio(self.hits[name], self.covered) for name in FIELDS}
        calibration = {level: {"slots": counts["slots"], "root": _ratio(counts["root"], counts["slots"]),
                               "exact": _ratio(counts["exact"], counts["slots"])}
                       for level, counts in self.by_confidence.items()}
        return {"slots": self.slots, "covered": self.covered, "coverage": _ratio(self.covered, self.slots),
                "unparseable": self.unparseable, "unscored_truth": self.unscored_truth, "all": all_slots,
                "on_covered": covered, "calibration": calibration}


def _ratio(hits: int, total: int) -> float | None:
    return None if total == 0 else round(hits / total, 4)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile; None without values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return round(ordered[rank - 1], 3)


def call_stats(calls: Sequence[dict]) -> dict:
    """Latency percentiles, cost and reply bookkeeping over an engine's call records."""
    latencies = [call["latency_ms"] for call in calls]
    attempts = sum(call.get("attempts", 1) for call in calls)
    failed = Counter(call["status"] for call in calls if call["status"] != "ok")
    # Each retry was earned by one reply that was not the requested JSON; a call that still
    # failed that way after its retry adds its last reply.
    invalid_replies = (attempts - len(calls)) + failed["invalid_json"] + failed["schema_mismatch"]
    return {"calls": len(calls), "attempts": attempts, "retries": attempts - len(calls),
            "retry_rate": _ratio(attempts - len(calls), len(calls)),
            "json_validity": None if attempts == 0 else round(1 - invalid_replies / attempts, 4),
            "failed": dict(failed), "latency_ms_p50": percentile(latencies, .5),
            "latency_ms_p95": percentile(latencies, .95),
            "cost_usd": round(sum(call["cost_usd"] for call in calls), 6),
            "bars_sent": sum(call["bars"] for call in calls),
            "request_ids": [call["request_id"] for call in calls if call.get("request_id")]}
