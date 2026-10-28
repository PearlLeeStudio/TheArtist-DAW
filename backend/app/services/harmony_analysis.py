"""Deterministic harmony candidates from *already read*, time-aligned notes.

This module does not read PDFs, perform optical music recognition, or call a
model. A note's onset/duration are global quarter-note beats, not seconds or
per-measure offsets; measure is its zero-based source measure. Key names use
``C major`` / ``A minor`` (single sharp/flat roots are accepted). Optional note
spellings such as ``Bb`` preserve the written scale degree.

Every note start/end creates a slice. Short stepwise passing/neighbor tones are
downweighted before chord matching; notes from an entire bar are never unioned
into one chord. At least three comparably supported, non-ornamental pitch classes
must support a chord identity. A held dyad plus a short passing/neighbor tone stays
unresolved instead of manufacturing a new harmony. Scores/confidence are
transparent ranking heuristics, not calibrated probabilities. Candidate ties and
key alternatives remain visible. The engine never forces two slots per measure.
The explicit exception is a two-tone tritone shell: it can suggest both possible
rootless dominant-seventh roots, always marked ambiguous with low confidence and
missing structural root/fifth evidence. It never claims an observed full chord.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from bisect import bisect_left, bisect_right
from math import exp, isfinite, sqrt
import re
from typing import Iterable, Literal

MAX_NOTE_EVENTS = 20_000
_EPS = 1e-8
_STRUCTURAL_SUPPORT_RATIO = .5
_LETTERS = "CDEFGAB"
_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_FLATS = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
_SHARPS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_MINOR = (0, 2, 3, 5, 7, 8, 10)
_ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII")
_NOTE = re.compile(r"([A-Ga-g])([#b]?)\Z")
_KEY = re.compile(r"([A-Ga-g][#b]?)\s+(major|minor)\Z", re.IGNORECASE)
_SIGNATURE_MAJOR = ("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#")
_SIGNATURE_MINOR = ("Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#")


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (positive and value <= 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    if value > 1_000_000:
        raise ValueError(f"{name} exceeds the analysis limit")
    return float(value)


def _pitch(name: str) -> int:
    match = _NOTE.fullmatch(name)
    if not match:
        raise ValueError("note spelling must be a letter A-G with at most one # or b")
    return (_NATURAL[match[1].upper()] + {"": 0, "#": 1, "b": -1}[match[2]]) % 12


@dataclass(frozen=True)
class NoteEvent:
    pitch: int
    onset: float
    duration: float
    measure: int = 0
    voice: str = ""
    staff: str = ""
    spelling: str | None = None

    def __post_init__(self) -> None:
        if type(self.pitch) is not int or not 0 <= self.pitch <= 127:
            raise ValueError("pitch must be an integer MIDI note 0..127")
        onset = _number(self.onset, "onset")
        duration = _number(self.duration, "duration", positive=True)
        if duration < _EPS or onset + duration > 1_000_000:
            raise ValueError("note time is outside the analysis limits")
        if type(self.measure) is not int or self.measure < 0:
            raise ValueError("measure must be a zero-based nonnegative integer")
        if not isinstance(self.voice, str) or not isinstance(self.staff, str):
            raise ValueError("voice and staff must be strings")
        if len(self.voice) > 80 or len(self.staff) > 80:
            raise ValueError("voice/staff labels must be at most 80 characters")
        if self.spelling is not None:
            if not isinstance(self.spelling, str) or _pitch(self.spelling) != self.pitch % 12:
                raise ValueError("note spelling must agree with its MIDI pitch")

    @property
    def end(self) -> float:
        return self.onset + self.duration


@dataclass(frozen=True)
class KeyCandidate:
    key: str
    score: float


@dataclass(frozen=True)
class KeyEstimate:
    key: str | None
    source: Literal["provided", "inferred", "none"]
    confidence: float
    alternatives: tuple[KeyCandidate, ...]
    pitch_class_durations: tuple[float, ...]


@dataclass(frozen=True)
class NoteEvidence:
    pitch: int
    spelling: str | None
    onset: float
    duration: float
    voice: str
    staff: str
    weight: float
    ornamental: bool


@dataclass(frozen=True)
class ChordCandidate:
    symbol: str
    roman: str | None
    root: str
    quality: str
    bass: str
    inversion: int | None
    score: float
    confidence: float
    chord_pitch_classes: tuple[int, ...]
    missing_pitch_classes: tuple[int, ...]
    non_chord_pitches: tuple[int, ...]
    evidence: str
    rootless_shell: bool = False


@dataclass(frozen=True)
class HarmonySegment:
    start: float
    end: float
    measure: int
    kind: Literal["harmony", "insufficient", "rest"]
    candidates: tuple[ChordCandidate, ...]
    notes: tuple[NoteEvidence, ...]
    uncertain: bool
    reason: str


@dataclass(frozen=True)
class HarmonyAnalysis:
    key: KeyEstimate
    segments: tuple[HarmonySegment, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Template:
    quality: str
    intervals: tuple[int, ...]
    missing_costs: tuple[float, ...]
    complexity: float


# Missing fifths cost less than missing thirds/sevenths. Added extensions must
# be sufficiently sustained to outweigh their explicit complexity cost.
_TEMPLATES = (
    _Template("maj", (0, 4, 7), (.9, .9, .35), 0),
    _Template("min", (0, 3, 7), (.9, .9, .35), 0),
    _Template("dim", (0, 3, 6), (.9, .9, .7), .04),
    _Template("aug", (0, 4, 8), (.9, .9, .7), .1),
    _Template("sus2", (0, 2, 7), (.9, .9, .35), .12),
    _Template("sus4", (0, 5, 7), (.9, .9, .35), .12),
    _Template("7", (0, 4, 7, 10), (.9, .9, .3, .85), .18),
    _Template("maj7", (0, 4, 7, 11), (.9, .9, .3, .85), .18),
    _Template("m7", (0, 3, 7, 10), (.9, .9, .3, .85), .18),
    _Template("m7b5", (0, 3, 6, 10), (.9, .9, .7, .85), .22),
    _Template("dim7", (0, 3, 6, 9), (.9, .9, .7, .85), .24),
    _Template("6", (0, 4, 7, 9), (.9, .9, .3, .75), .28),
    _Template("m6", (0, 3, 7, 9), (.9, .9, .3, .75), .28),
    _Template("add9", (0, 4, 7, 2), (.9, .9, .3, .75), .5),
    _Template("9", (0, 4, 7, 10, 2), (.9, .9, .3, .85, .75), .65),
    _Template("maj9", (0, 4, 7, 11, 2), (.9, .9, .3, .85, .75), .7),
    _Template("m9", (0, 3, 7, 10, 2), (.9, .9, .3, .85, .75), .65),
    _Template("11", (0, 4, 7, 10, 2, 5), (.9, .6, .25, .85, .45, .75), .85),
    _Template("m11", (0, 3, 7, 10, 2, 5), (.9, .9, .25, .85, .45, .75), .85),
    _Template("13", (0, 4, 7, 10, 2, 9), (.9, .9, .25, .85, .4, .8), .95),
)


def _parse_key(key: str) -> tuple[str, int, bool]:
    if not isinstance(key, str):
        raise ValueError("key must be a name such as 'C major' or 'A minor'")
    match = _KEY.fullmatch(key.strip())
    if not match:
        raise ValueError("key must be a name such as 'C major' or 'A minor'")
    root = match[1][0].upper() + match[1][1:]
    mode = match[2].lower()
    return f"{root} {mode}", _pitch(root), mode == "minor"


def _metric_weight(onset: float, bar_beats: float) -> float:
    beat = onset % bar_beats
    if min(beat, bar_beats - beat) < _EPS:
        return 1.15
    if abs(beat - bar_beats / 2) < _EPS:
        return 1.08
    return 1.0 if abs(beat - round(beat)) < _EPS else .9


def _ornament_weights(notes: tuple[NoteEvent, ...], bar_beats: float) -> dict[int, float]:
    """Only label short stepwise tones with unambiguous same-voice neighbors."""
    groups: dict[tuple[str, str], list[tuple[int, NoteEvent]]] = {}
    for index, note in enumerate(notes):
        groups.setdefault((note.staff, note.voice), []).append((index, note))
    weights: dict[int, float] = {}
    for group in groups.values():
        by_end = sorted(group, key=lambda item: item[1].end)
        by_onset = sorted(group, key=lambda item: item[1].onset)
        end_times = [note.end for _, note in by_end]
        onset_times = [note.onset for _, note in by_onset]
        for index, note in group:
            if note.duration > .75:
                continue
            before = by_end[bisect_left(end_times, note.onset - .25):bisect_right(end_times, note.onset + _EPS)]
            after = by_onset[bisect_left(onset_times, note.end - _EPS):bisect_right(onset_times, note.end + .25)]
            if not before or not after:
                continue
            latest = max(n.end for _, n in before)
            earliest = min(n.onset for _, n in after)
            previous = [n for _, n in before if abs(n.end - latest) < _EPS]
            following = [n for _, n in after if abs(n.onset - earliest) < _EPS]
            if len(previous) != 1 or len(following) != 1:
                continue
            a, b = previous[0].pitch, following[0].pitch
            step_in, step_out = note.pitch - a, b - note.pitch
            if not 0 < abs(step_in) <= 2 or not 0 < abs(step_out) <= 2:
                continue
            passing = step_in * step_out > 0
            neighbor = a == b
            if passing or neighbor:
                # Accented non-chord tones retain more influence than weak ones.
                weights[index] = .4 if _metric_weight(note.onset, bar_beats) > 1 else .18
    return weights


def _estimate_key(notes: tuple[NoteEvent, ...], ornaments: dict[int, float],
                  bar_beats: float, supplied: str | None, key_signature: int | None) -> KeyEstimate:
    histogram = [0.0] * 12
    for index, note in enumerate(notes):
        histogram[note.pitch % 12] += note.duration * ornaments.get(index, 1.0) * _metric_weight(note.onset, bar_beats)
    durations = tuple(round(value, 6) for value in histogram)
    if supplied is not None:
        key, _, _ = _parse_key(supplied)
        return KeyEstimate(key, "provided", 1.0, (KeyCandidate(key, 1.0),), durations)
    total = sum(histogram)
    if total == 0:
        return KeyEstimate(None, "none", 0.0, (), durations)

    # Explicit tonal preference weights: tonic/dominant/third are strongest;
    # chromatic tones still contribute rather than being silently discarded.
    major = (4, .3, 1.4, .3, 2.5, 1.8, .3, 3, .3, 1.6, .5, 1.1)
    minor = (4, .3, 1.1, 2.5, .3, 1.8, .6, 3, 1.8, .5, 1.5, 1.0)
    last_end = max(note.end for note in notes)
    last_bass = min(note.pitch for note in notes if abs(note.end - last_end) < _EPS) % 12
    candidates: list[KeyCandidate] = []
    for is_minor, profile in ((False, major), (True, minor)):
        norm = sqrt(sum(value * value for value in profile))
        for tonic in range(12):
            weighted = sum(histogram[pc] * profile[(pc - tonic) % 12] for pc in range(12)) / (total * norm)
            score = weighted + .14 * histogram[tonic] / total + (.08 if tonic == last_bass else 0)
            name = (_SHARPS if is_minor and tonic in (1, 6, 8) else _FLATS)[tonic]
            if key_signature is not None:
                signature_root = (_SIGNATURE_MINOR if is_minor else _SIGNATURE_MAJOR)[key_signature + 7]
                if tonic == _pitch(signature_root):
                    # A signature guides the relative major/minor pair but
                    # never declares its mode or overrides actual note evidence.
                    score += .12
                    name = signature_root
            candidates.append(KeyCandidate(f"{name} {'minor' if is_minor else 'major'}", round(score, 6)))
    candidates.sort(key=lambda item: (-item.score, item.key))
    gap = candidates[0].score - candidates[1].score
    coverage = min(1.0, sum(value > 0 for value in histogram) / 7)
    confidence = round(min(.95, max(.05, gap * 7)) * coverage, 4)
    return KeyEstimate(candidates[0].key, "inferred", confidence, tuple(candidates[:5]), durations)


def _spell(pc: int, key: str | None, evidence: tuple[NoteEvent, ...] = ()) -> str:
    written = [note.spelling for note in evidence if note.pitch % 12 == pc and note.spelling]
    if written:
        spelling = max(dict.fromkeys(written), key=written.count)
        return spelling[0].upper() + spelling[1:]
    if key is None:
        return _FLATS[pc]
    _, tonic, minor = _parse_key(key)
    root_name = key.split(" ")[0]
    root_letter = _LETTERS.index(root_name[0])
    scale = _MINOR if minor else _MAJOR
    interval = (pc - tonic) % 12
    degree = min(range(7), key=lambda i: (
        abs(((interval - scale[i] + 6) % 12) - 6),
        0 if ((interval - scale[i] + 6) % 12) - 6 <= 0 else 1,
    ))
    letter = _LETTERS[(root_letter + degree) % 7]
    accidental = ((pc - _NATURAL[letter] + 6) % 12) - 6
    if abs(accidental) <= 1:
        return letter + ("#" if accidental == 1 else "b" if accidental == -1 else "")
    return _FLATS[pc]


def _roman(root: str, quality: str, key: str | None) -> str | None:
    if key is None:
        return None
    _, tonic, minor = _parse_key(key)
    root_letter = _LETTERS.index(key[0])
    degree = (_LETTERS.index(root[0]) - root_letter + 7) % 7
    scale = _MINOR if minor else _MAJOR
    interval = (_pitch(root) - tonic) % 12
    alteration = ((interval - scale[degree] + 6) % 12) - 6
    prefix = "#" * alteration if alteration > 0 else "b" * -alteration
    numeral = _ROMANS[degree]
    if quality in {"min", "m7", "m6", "m9", "m11", "dim", "dim7", "m7b5"}:
        numeral = numeral.lower()
    suffix = {"maj": "", "min": "", "dim": "°", "dim7": "°7", "aug": "+",
              "m7b5": "ø7", "m7": "7", "m6": "6", "m9": "9", "m11": "11"}.get(quality, quality)
    return prefix + numeral + suffix


def _rootless_shells(active: tuple[tuple[int, NoteEvent], ...], structural_pcs: set[int],
                     key: KeyEstimate, confidence_cap: float) -> tuple[ChordCandidate, ...]:
    """A tritone is compatible with two dominant 3rd/7th shells, not one chord.

    The missing classes here lack structural support, even if a fleeting melody
    ornament happens to touch one. Raw note evidence remains unchanged.
    """
    first, second = sorted(structural_pcs)
    if (second - first) % 12 != 6:
        return ()
    roots = ((first - 4) % 12, (second - 4) % 12)
    active_notes = tuple(note for _, note in active)
    bass_midi = min(note.pitch for note in active_notes)
    bass_pc = bass_midi % 12
    bass_name = _spell(bass_pc, key.key, active_notes)
    if key.key:
        _, tonic, minor = _parse_key(key.key)
        diatonic = {(tonic + interval) % 12 for interval in (_MINOR if minor else _MAJOR)}
    else:
        tonic, diatonic = -1, set()
    interpretations = []
    for root in roots:
        tones = tuple((root + interval) % 12 for interval in (0, 4, 7, 10))
        # Fleeting, unsupported melody tones cannot flip the identity of an
        # unchanged structural shell. They stay in the evidence, while only
        # the shell and tonal context order these inherently ambiguous roots.
        score = 4 - .9 - .3 - .18
        score += .12 if root in diatonic else 0
        score += .08 if set(tones) <= diatonic else 0
        score += .05 if root == tonic else 0
        interpretations.append((score, root, tones))
    interpretations.sort(key=lambda item: (-item[0], item[1]))
    alternatives = ", ".join(_spell(root, key.key) + "7" for _, root, _ in interpretations)
    result = []
    for score, root, tones in interpretations:
        root_name = _spell(root, key.key)
        missing = tuple(pc for pc in tones if pc not in structural_pcs)
        non_chord = tuple(sorted({note.pitch for note in active_notes if note.pitch % 12 not in tones}))
        inversion = (0, 4, 7, 10).index((bass_pc - root) % 12) if bass_pc in tones else None
        symbol = root_name + "7" + (f"/{bass_name}" if bass_pc != root else "")
        confidence = min(.35, confidence_cap, .25 * exp((score - interpretations[0][0]) / .7))
        evidence = (f"Ambiguous rootless dominant shell: structural pitch classes {first}, {second} can be "
                    f"third/seventh tones. Alternatives: {alternatives}. Root/fifth lack structural support "
                    f"(pitch classes {', '.join(map(str, missing))}); this is not an observed complete chord. "
                    f"Read MIDI: {', '.join(str(pitch) for pitch in sorted({note.pitch for note in active_notes}))}; bass {bass_name}.")
        result.append(ChordCandidate(symbol, _roman(root_name, "7", key.key), root_name, "7", bass_name,
                                     inversion, round(score, 6), round(confidence, 4), tones, missing,
                                     non_chord, evidence, rootless_shell=True))
    return tuple(result)


def _rank(active: tuple[tuple[int, NoteEvent], ...], weights: dict[int, float], ornaments: dict[int, float],
          key: KeyEstimate, top_n: int, confidence_cap: float) -> tuple[ChordCandidate, ...]:
    by_pc: dict[int, float] = {}
    structural_support: dict[int, float] = {}
    for index, note in active:
        by_pc[note.pitch % 12] = by_pc.get(note.pitch % 12, 0) + weights[index]
        if index not in ornaments:
            # Doubling the same fleeting melody tone in another octave must
            # not manufacture duration support for an extra harmonic degree.
            structural_support[note.pitch % 12] = max(structural_support.get(note.pitch % 12, 0), weights[index])
    strongest = max(structural_support.values(), default=0)
    structural_pcs = {pc for pc, weight in structural_support.items()
                      if weight >= strongest * _STRUCTURAL_SUPPORT_RATIO}
    if len(structural_pcs) == 2:
        return _rootless_shells(active, structural_pcs, key, confidence_cap)
    if len(structural_pcs) < 3:
        return ()
    total = sum(by_pc.values())
    bass_midi = min(note.pitch for _, note in active)
    bass_pc = bass_midi % 12
    active_notes = tuple(note for _, note in active)
    ranked: list[tuple[float, int, _Template, tuple[int, ...], tuple[int, ...], float]] = []
    if key.key:
        _, tonic, minor = _parse_key(key.key)
        diatonic = {(tonic + interval) % 12 for interval in (_MINOR if minor else _MAJOR)}
    else:
        tonic, diatonic = -1, set()
    for root in range(12):
        # No rootless-chord assertion when a simpler explanation has actual
        # root evidence. Rootless voicings can be interpreted in a later layer.
        if root not in by_pc:
            continue
        for template in _TEMPLATES:
            tones = tuple((root + interval) % 12 for interval in template.intervals)
            if len(set(tones) & structural_pcs) < 3:
                continue
            missing = tuple(pc for pc in tones if pc not in by_pc)
            foreign = sum(weight for pc, weight in by_pc.items() if pc not in tones)
            covered = 1 - foreign / total
            missing_cost = sum(cost for pc, cost in zip(tones, template.missing_costs) if pc not in by_pc)
            score = 4 * covered - 2 * foreign / total - missing_cost - template.complexity
            score += .24 if bass_pc == root else .12 if bass_pc in tones else -.2
            score += .12 if root in diatonic else 0
            score += .08 if set(tones) <= diatonic else 0
            score += .05 if root == tonic else 0
            ranked.append((score, root, template, tones, missing, covered))
    ranked.sort(key=lambda item: (-item[0], len(item[3]), item[1], item[2].quality))
    if not ranked:
        return ()
    margin = ranked[0][0] - ranked[1][0] if len(ranked) > 1 else 1
    confidence = min(confidence_cap, min(.95, max(.05, .35 + margin * .65)) * ranked[0][5])
    result: list[ChordCandidate] = []
    for score, root, template, tones, missing, covered in ranked[:top_n]:
        root_name = _spell(root, key.key, active_notes)
        bass_name = _spell(bass_pc, key.key, active_notes)
        suffix = "" if template.quality == "maj" else "m" if template.quality == "min" else template.quality
        symbol = root_name + suffix + (f"/{bass_name}" if bass_pc != root else "")
        non_chord = tuple(sorted({note.pitch for _, note in active if note.pitch % 12 not in tones}))
        inversion = template.intervals.index((bass_pc - root) % 12) if bass_pc in tones else None
        confidence_here = confidence * exp((score - ranked[0][0]) / .7)
        notes_text = ", ".join(str(pitch) for pitch in sorted({note.pitch for _, note in active}))
        evidence = f"Active MIDI pitches: {notes_text}; bass {bass_name} ({bass_midi}); weighted chord coverage {covered:.0%}."
        evidence += f" Structural chord pitch classes: {', '.join(map(str, sorted(set(tones) & structural_pcs)))}."
        if non_chord:
            evidence += f" Non-chord pitches: {', '.join(map(str, non_chord))}."
        if missing:
            evidence += f" Missing template pitch classes: {', '.join(map(str, missing))}."
        result.append(ChordCandidate(symbol, _roman(root_name, template.quality, key.key), root_name,
                                     template.quality, bass_name, inversion, round(score, 6),
                                     round(confidence_here, 4), tones, missing, non_chord, evidence))
    return tuple(result)


def _validated_notes(events: Iterable[NoteEvent]) -> tuple[NoteEvent, ...]:
    notes_list: list[NoteEvent] = []
    for note in events:
        if not isinstance(note, NoteEvent):
            raise ValueError("events must contain validated NoteEvent instances")
        notes_list.append(note)
        if len(notes_list) > MAX_NOTE_EVENTS:
            raise ValueError(f"analysis accepts at most {MAX_NOTE_EVENTS} note events")
    return tuple(sorted(notes_list, key=lambda note: (note.onset, note.pitch, note.duration,
                                                     note.measure, note.staff, note.voice, note.spelling or "")))


def _bar_beats(time_signature: tuple[int, int]) -> float:
    if not isinstance(time_signature, (tuple, list)) or len(time_signature) != 2:
        raise ValueError("time_signature must contain numerator and denominator")
    numerator, denominator = time_signature
    if type(numerator) is not int or not 1 <= numerator <= 32 or type(denominator) is not int \
            or denominator not in (1, 2, 4, 8, 16, 32):
        raise ValueError("time_signature must use numerator 1..32 and a power-of-two denominator 1..32")
    return numerator * 4 / denominator


def _key_options(key: str | None, key_signature: int | None, timing_is_estimated: bool) -> str | None:
    if key_signature is not None and (type(key_signature) is not int or not -7 <= key_signature <= 7):
        raise ValueError("key_signature must be an integer flat/sharp count -7..7")
    if type(timing_is_estimated) is not bool:
        raise ValueError("timing_is_estimated must be a boolean")
    return _parse_key(key)[0] if key is not None else None


def estimate_key(events: Iterable[NoteEvent], *, key: str | None = None,
                 key_signature: int | None = None, time_signature: tuple[int, int] = (4, 4),
                 timing_is_estimated: bool = False) -> KeyEstimate:
    """Estimate a whole-score key before analyzing measures with their own meters.

    Use global onsets for this call, then local quarter-beat onsets and the
    original zero-based measure index for individual ``analyze_harmony`` calls.
    A mixed-meter adapter may use this default meter for approximate global
    onset weighting; durations and the signature pair remain the main evidence.
    Estimated timing caps inferred-key confidence at .35, never a manual key.
    """
    key = _key_options(key, key_signature, timing_is_estimated)
    bar_beats = _bar_beats(time_signature)
    notes = _validated_notes(events)
    result = _estimate_key(notes, _ornament_weights(notes, bar_beats), bar_beats, key, key_signature)
    if timing_is_estimated and result.source == "inferred":
        return replace(result, confidence=min(.35, result.confidence))
    return result


def analyze_harmony(events: Iterable[NoteEvent], *, key: str | None = None,
                    time_signature: tuple[int, int] = (4, 4), top_n: int = 3,
                    total_duration: float | None = None, key_signature: int | None = None,
                    timing_is_estimated: bool = False) -> HarmonyAnalysis:
    """Analyze notes without I/O, model state, random choices or bar-slot padding.

    ``total_duration`` optionally retains leading/trailing rests. If supplied it
    must cover all events. Results are serializable with ``dataclasses.asdict``.
    Manual key always overrides the heuristic key estimate, including its Roman
    analysis; it never transposes the evidence pitches.
    ``key_signature`` is an optional -7..7 flat/sharp count, a soft major/minor
    pair prior rather than a declaration of mode. Geometry-derived or otherwise
    uncertain timing must set ``timing_is_estimated``; chord confidence is then
    capped at .55 and all sounding segments require review.
    ``top_n`` controls ordinary candidates. The two inherently ambiguous
    rootless-shell alternatives are both retained even when ``top_n=1``.
    """
    if type(top_n) is not int or not 1 <= top_n <= 10:
        raise ValueError("top_n must be an integer 1..10")
    key = _key_options(key, key_signature, timing_is_estimated)
    bar_beats = _bar_beats(time_signature)
    notes = _validated_notes(events)
    end = max((note.end for note in notes), default=0.0)
    if total_duration is not None:
        total_duration = _number(total_duration, "total_duration")
        if total_duration + _EPS < end:
            raise ValueError("total_duration must cover every note event")
        end = total_duration
    ornaments = _ornament_weights(notes, bar_beats)
    weights = {index: min(1.0, note.duration) * _metric_weight(note.onset, bar_beats) * ornaments.get(index, 1.0)
               for index, note in enumerate(notes)}
    estimate = _estimate_key(notes, ornaments, bar_beats, key, key_signature)
    if timing_is_estimated and estimate.source == "inferred":
        estimate = replace(estimate, confidence=min(.35, estimate.confidence))
    warnings: list[str] = []
    if estimate.source == "inferred" and estimate.confidence < .5:
        warnings.append("The global key is ambiguous; inspect its alternatives or provide a key.")
    if not notes:
        warnings.append("No note evidence was supplied; no chord has been inferred.")
    if timing_is_estimated:
        warnings.append("Note timing is estimated rather than read exactly; simultaneity, bass and chord boundaries require review.")
    boundaries = sorted({0.0, end, *(note.onset for note in notes), *(note.end for note in notes)})
    starts: dict[float, list[int]] = {}
    ends: dict[float, list[int]] = {}
    for index, note in enumerate(notes):
        starts.setdefault(note.onset, []).append(index)
        ends.setdefault(note.end, []).append(index)
    active: set[int] = set()
    segments: list[HarmonySegment] = []
    last_measure = 0
    for start, stop in zip(boundaries, boundaries[1:]):
        active.difference_update(ends.get(start, ()))
        active.update(starts.get(start, ()))
        if stop - start < _EPS:
            continue
        current = tuple((index, notes[index]) for index in sorted(active))
        evidence = tuple(NoteEvidence(note.pitch, note.spelling, note.onset, note.duration,
                                      note.voice, note.staff, round(weights[index], 6), index in ornaments)
                         for index, note in current)
        if current:
            last_measure = max(note.measure for _, note in current)
        candidates = _rank(current, weights, ornaments, estimate, top_n, .55 if timing_is_estimated else .95)
        if not current:
            kind, reason = "rest", "No active notes; no chord inferred."
        elif not candidates:
            kind, reason = "insufficient", "Fewer than three sufficiently supported structural pitch classes; harmony is unresolved."
        else:
            kind = "harmony"
            reason = ("Ambiguous rootless dominant shell; both possible roots are retained and need review."
                      if candidates[0].rootless_shell else
                      "Ranked from simultaneous notes, duration/metric weights and bass evidence.")
        if any(index in ornaments for index, _ in current):
            reason += " Short stepwise ornament(s) were downweighted."
        uncertain = not candidates or candidates[0].confidence < .65 or bool(candidates[0].missing_pitch_classes)
        if estimate.source == "inferred" and estimate.confidence < .5:
            uncertain = True
        segments.append(HarmonySegment(start, stop, last_measure, kind, candidates, evidence, uncertain, reason))
    return HarmonyAnalysis(estimate, tuple(segments), tuple(warnings))
