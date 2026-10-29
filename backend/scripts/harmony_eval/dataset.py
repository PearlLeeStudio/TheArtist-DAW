"""Deterministic scores for the harmony evaluation.

Synthetic: progressions from the product's rule-based generator (one fixed seed per
genre, all 13 genres, keys spread over both modes) and a short canonical list.
Real songs (--songs): eight-bar excerpts of the owner's private held-out songs,
cut where every bar fits the editor's two slots. The product's own voicing code
turns each bar's chord symbols into note events in six realizations of
controlled difficulty, the same for both. The real-song dataset is written only
outside the repository.

Run from backend/:
    uv run python -m scripts.harmony_eval.dataset [--out PATH]
    uv run python -m scripts.harmony_eval.dataset --songs SONGS.jsonl [--private-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from app.models.schemas import ContextMeasure
from app.services.chord_generator import (
    MAJOR_INTERVALS, MINOR_INTERVALS, NOTE_TO_SEMITONE, _parse_key, generate_suggestions,
)
from app.services.harmony_analysis import NoteEvent, estimate_key
from app.services.song_builder import BASS_BASE_MIDI, _bass_pc, _harmony_voicing
from app.services.voice_leading import _CHORD_TONES, _NOTE_PC, _parse
from scripts.harmony_eval import (
    DATASET_PATH, PRIVATE_DIR, REAL_SONGS_DATASET_NAME, PrivateDataError, outside_repo, repo_relative,
)
from scripts.harmony_eval.chords import normalize

SEED = 20261029
BARS = 8
RECORDS = 42
VARIANTS = ("block", "rootless", "inversion", "melody", "sparse", "waltz")
REAL_SONGS_EXCERPTS = 40
REAL_SONGS_METERS = {"4/4": (4, 4), "3/4": (3, 4)}
# The corpus preprocessing writes C major for every song whose source has no key
PLACEHOLDER_KEY = "C major"
_CORPUS_KEY = re.compile(r"([A-G](?:#|b)?)(maj|min)")
_CORPUS_CHORD = re.compile(r"([A-G](?:#|b)?)([^/]*)(?:/([A-G](?:#|b)?))?")
# The corpus writes a major triad "Ebmaj"; the product writes the bare root
_PRODUCT_QUALITY = {"maj": "", "min": "m"}
# One progression per genre, keys spread over major and minor, flats and sharps.
GENRE_KEYS = (
    ("jazz", "Bb major"), ("pop", "C major"), ("rock", "E major"), ("blues", "A major"),
    ("bossa", "D minor"), ("classical", "G major"), ("country", "D major"), ("rnb_soul", "Eb major"),
    ("hip_hop", "A minor"), ("electronic", "F# minor"), ("funk", "F major"), ("folk", "E minor"),
    ("gospel", "Ab major"),
)
# (name, genre, key, bars): a bar is [chord, chord-or-None]; None = one chord fills the bar.
CANONICAL = (
    ("ii-V-I major", "jazz", "C major",
     [["Dm7", "G7"], ["Cmaj7", None], ["Dm7", "G7"], ["Cmaj7", "A7"],
      ["Dm7", "G7"], ["Em7", "Am7"], ["Dm7", "G7"], ["Cmaj7", None]]),
    ("ii-V-i minor", "jazz", "A minor",
     [["Bm7b5", "E7"], ["Am7", None], ["Dm7", "G7"], ["Cmaj7", None],
      ["Bm7b5", "E7"], ["Am7", None], ["Dm7", "E7"], ["Am6", None]]),
    ("I-vi-IV-V", "pop", "G major",
     [["G", None], ["Em", None], ["C", None], ["D", None],
      ["G", None], ["Em", None], ["C", "D"], ["G", None]]),
    ("12-bar blues", "blues", "F major",
     [["F7", None], ["Bb7", None], ["F7", None], ["F7", None], ["Bb7", None], ["Bb7", None],
      ["F7", None], ["F7", None], ["C7", None], ["Bb7", None], ["F7", None], ["C7", None]]),
    ("bossa maj7/m7 loop", "bossa", "D major",
     [["Dmaj7", None], ["Dmaj7", None], ["Em7", None], ["A7", None],
      ["F#m7", None], ["Bm7", None], ["Em7", None], ["A7", None]]),
    ("classical period", "classical", "C major",
     [["C", None], ["G/B", None], ["Am", None], ["G", None],
      ["C", None], ["C/E", "F"], ["Dm/F", "G7"], ["C", None]]),
)
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_SHARP_KEYS = frozenset({"G major", "D major", "A major", "E major", "B major", "F# major", "C# major",
                         "E minor", "B minor", "F# minor", "C# minor", "G# minor", "D# minor", "A# minor"})
_LETTERS = "CDEFGAB"
_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
HARMONY_STAFF, BASS_STAFF = 0, 1
MELODY_OCTAVE = 12
EIGHTH = 0.5


def _names(key: str) -> tuple[str, ...]:
    return _SHARP_NAMES if key in _SHARP_KEYS else _FLAT_NAMES


def _spelling(pitch: int, key: str) -> str:
    return f"{_names(key)[pitch % 12]}{pitch // 12 - 1}"


def _scale(key: str) -> frozenset[int]:
    root, minor = _parse_key(key)
    return frozenset((root + step) % 12 for step in (MINOR_INTERVALS if minor else MAJOR_INTERVALS))


def _step(pitch: int, scale: frozenset[int], direction: int) -> int:
    """The nearest scale tone above (1) or below (-1) the pitch; a whole step when neither fits."""
    for distance in (1, 2):
        if (pitch + direction * distance) % 12 in scale:
            return pitch + direction * distance
    return pitch + direction * 2


def _chord_tone_name(symbol: str, steps: int, pitch_class: int, key: str) -> str:
    """The chord tone spelled from the root letter (D7's third is F#), else the key's spelling. A name
    the product's voicing cannot read (E#, B#, Cb, Fb) would strike the root instead, so it takes the
    key's spelling too."""
    letter = _LETTERS[(_LETTERS.index(symbol[0]) + steps) % 7]
    accidental = (pitch_class - _NATURAL[letter]) % 12
    name = {0: letter, 1: letter + "#", 11: letter + "b"}.get(accidental)
    return name if name in _NOTE_PC else _names(key)[pitch_class]


def _note(pitch: int, onset: float, duration: float, staff: int, key: str) -> dict:
    return {"pitch": pitch, "spelling": _spelling(pitch, key), "onset": onset, "duration": duration,
            "staff": staff}


def _strike(notes: list[dict], pitches: Sequence[int], onset: float, duration: float, staff: int, key: str) -> None:
    notes.extend(_note(pitch, onset, duration, staff, key) for pitch in pitches)


def _slots(bar: Sequence[str | None]) -> tuple[str, str]:
    first, second = bar[0], bar[1] if len(bar) > 1 else None
    return first, second or first


def _bass(symbol: str) -> list[int]:
    pitch_class = _bass_pc(symbol)
    return [] if pitch_class is None else [BASS_BASE_MIDI + pitch_class]


def _inverted(symbol: str, rng: random.Random, key: str) -> str:
    """The symbol with its bass on the third or fifth; a written slash chord is kept."""
    parsed = _parse(symbol)
    if parsed is None or "/" in symbol:
        return symbol
    root_pc, quality, _ = parsed
    tones = _CHORD_TONES.get(quality, _CHORD_TONES["maj"])
    steps = rng.choice((2, 4))  # letter steps to the third or the fifth
    pitch_class = (root_pc + tones[1 if steps == 2 else 2]) % 12
    return f"{symbol}/{_chord_tone_name(symbol, steps, pitch_class, key)}"


def _melody(symbol: str, start: float, rng: random.Random, scale: frozenset[int], key: str) -> list[dict]:
    """Four eighth notes on chord tones with a passing tone, or a neighbor tone on the strong beat."""
    tones = [pitch + MELODY_OCTAVE for pitch in _harmony_voicing(symbol)]
    if len(tones) < 3:
        return []
    first, second, third = tones[0], tones[1], tones[2]
    pattern = rng.choice((
        (first, second, third, second),                              # chord tones only
        (first, _step(first, scale, 1), second, third),              # passing tone off the beat
        (_step(third, scale, 1), third, second, first),              # upper neighbor on the strong beat
        (second, _step(second, scale, -1), second, first),           # lower neighbor off the beat
    ))
    return [_note(pitch, start + index * EIGHTH, EIGHTH, HARMONY_STAFF, key) for index, pitch in enumerate(pattern)]


def _realize_bar(bar: Sequence[str | None], variant: str, rng: random.Random, key: str,
                 scale: frozenset[int], meter: tuple[int, int] = (4, 4)
                 ) -> tuple[list[str | None], list[dict], tuple[int, int]]:
    """(truth chords, note events, time signature) of one bar in the given realization.

    The two slots split the bar, two beats each in 4/4 and one and a half in 3/4; waltz is 3/4 whatever
    the meter.
    """
    notes: list[dict] = []
    first, second = _slots(bar)
    truth: list[str | None] = [bar[0], bar[1] if len(bar) > 1 else None]
    if variant == "waltz":
        _strike(notes, _bass(first), 0.0, 1.0, BASS_STAFF, key)
        for beat in (1.0, 2.0):
            _strike(notes, _harmony_voicing(first), beat, 1.0, HARMONY_STAFF, key)
        return [first, None], notes, (3, 4)
    if variant == "sparse":
        _strike(notes, _harmony_voicing(first), 0.0, 1.0, HARMONY_STAFF, key)
        _strike(notes, _bass(first), 0.0, 1.0, BASS_STAFF, key)
        return [first, None], notes, meter
    slot_beats = meter[0] * 4 / meter[1] / 2
    if variant == "inversion":
        # A one-chord bar is one inversion over both halves, as its truth says
        first = _inverted(first, rng, key)
        second = first if truth[1] is None else _inverted(second, rng, key)
        truth = [first, None if truth[1] is None else second]
    for slot, symbol in enumerate((first, second)):
        onset = slot * slot_beats
        voicing = _harmony_voicing(symbol)
        if variant == "rootless":
            root_pc = _parse(symbol)[0]
            _strike(notes, [pitch for pitch in voicing if pitch % 12 != root_pc], onset, slot_beats,
                    HARMONY_STAFF, key)
            continue
        _strike(notes, voicing, onset, slot_beats, HARMONY_STAFF, key)
        _strike(notes, _bass(symbol), onset, slot_beats, BASS_STAFF, key)
        if variant == "melody":
            notes.extend(_melody(symbol, onset, rng, scale, key)[:int(slot_beats / EIGHTH)])
    return truth, notes, meter


def _generated(seed: int) -> list[tuple[str, str, str, list[list[str | None]]]]:
    """One eight-bar progression per genre from the product's generator, options A/B/C in turn."""
    progressions = []
    context = [ContextMeasure(measure=index, chords=[None, None]) for index in range(BARS)]
    for number, (genre, key) in enumerate(GENRE_KEYS):
        suggestions = generate_suggestions(key, genre, context, list(range(BARS)), seed=seed + number)
        option = suggestions[number % len(suggestions)]
        bars = []
        for index in range(BARS):
            first, second = option.chords[str(index)]
            bars.append([first, None if second == first else second])
        progressions.append((genre, genre, key, bars))
    return progressions


def build_dataset(seed: int = SEED) -> list[dict]:
    """RECORDS synthetic scores: progression and realization cycle with coprime periods, so every
    variant gets the same number of records and no progression repeats a variant."""
    progressions = [*_generated(seed), *CANONICAL]
    records = []
    for number in range(RECORDS):
        name, genre, key, bars = progressions[number % len(progressions)]
        variant = VARIANTS[number % len(VARIANTS)]
        rng = random.Random(f"{seed}:{number}")
        scale = _scale(key)
        realized = [_realize_bar(bar, variant, rng, key, scale) for bar in bars]
        meter = realized[0][2]
        slug = name.lower().replace(" ", "-").replace("/", "-")
        records.append({
            "id": f"{number:02d}-{slug}-{variant}",
            "source": "canonical" if (name, genre, key, bars) in CANONICAL else "generator",
            "progression": name, "genre": genre, "key": key, "timeSignature": list(meter), "variant": variant,
            "bars": [{"index": index, "chords": truth, "notes": notes}
                     for index, (truth, notes, _) in enumerate(realized)],
        })
    return records


def normalize_key(text: object) -> str | None:
    """A corpus key in the product's spelling: "Ebmaj" -> "Eb major", "Amin" -> "A minor"; None otherwise."""
    match = _CORPUS_KEY.fullmatch(text) if isinstance(text, str) else None
    if match is None or match[1] not in NOTE_TO_SEMITONE:
        return None
    return f"{match[1]} {'major' if match[2] == 'maj' else 'minor'}"


def product_symbol(symbol: object) -> str | None:
    """A corpus chord in the product's spelling ("Ebmaj" -> "Eb", "F#m7" as is).

    None when the voicing code has no chord-tone row for the quality: it would sound another
    chord than the truth names (as "Am" did before the table knew "m").
    """
    match = _CORPUS_CHORD.fullmatch(symbol) if isinstance(symbol, str) else None
    if match is None:
        return None
    root, quality, bass = match.groups()
    quality = _PRODUCT_QUALITY.get(quality, quality)
    if root not in _NOTE_PC or (bass is not None and bass not in _NOTE_PC) \
            or (quality and quality not in _CHORD_TONES):
        return None
    mapped = root + quality + (f"/{bass}" if bass else "")
    return mapped if normalize(mapped) is not None else None


def _editor_bar(chords: object) -> tuple[list[str | None] | None, str | None]:
    """(the bar as [chord, chord-or-None], None), or (None, why it cannot fill the editor's two slots)."""
    if not isinstance(chords, list) or not chords:
        return None, "no_chord"
    if len(chords) > 2:
        return None, "more_than_two_chords"
    mapped = [product_symbol(symbol) for symbol in chords]
    if None in mapped:
        return None, "unrealizable_chord"
    first, second = mapped[0], mapped[1] if len(mapped) > 1 else None
    return [first, None if second == first else second], None


def load_songs(path: Path) -> tuple[list[dict], Counter[str], Counter[str]]:
    """(songs in the product's spelling, songs dropped by reason, bars left out by reason).

    A song needs a 4/4 or 3/4 meter and a key; a bar that cannot fill the editor's two
    slots stays in place as None, so no excerpt spans it.
    """
    songs: list[dict] = []
    dropped: Counter[str] = Counter()
    left_out: Counter[str] = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        song = json.loads(line)
        meter = REAL_SONGS_METERS.get(song.get("time_signature"))
        key = normalize_key(song.get("key"))
        if meter is None or key is None:
            dropped["meter" if meter is None else "key"] += 1
            continue
        bars = []
        for chords in song.get("bars") or []:
            bar, reason = _editor_bar(chords)
            bars.append(bar)
            if reason:
                left_out[reason] += 1
        songs.append({"id": str(song.get("id")), "title": song.get("title"), "source": song.get("source"),
                      "genre": song.get("genre") or "unknown", "key": key, "meter": meter, "bars": bars})
    return songs, dropped, left_out


def _excerpt_starts(bars: Sequence[object], rng: random.Random) -> list[int]:
    """One or two starts of eight-bar runs whose every bar fills the two slots: a random run, then a
    random run that does not overlap it when the song has one."""
    starts = [start for start in range(len(bars) - BARS + 1) if all(bars[start:start + BARS])]
    if not starts:
        return []
    first = rng.choice(starts)
    others = [start for start in starts if abs(start - first) >= BARS]
    return [first, rng.choice(others)] if others else [first]


def _estimated_key(bars: Sequence[Sequence[str | None]], meter: tuple[int, int]) -> str | None:
    """The product's key estimate over the excerpt's chords in block voicing, harmony and bass."""
    beats = meter[0] * 4 / meter[1]
    events = [NoteEvent(pitch, number * beats + slot * beats / 2, beats / 2, number)
              for number, bar in enumerate(bars) for slot, symbol in enumerate(_slots(bar))
              for pitch in (*_harmony_voicing(symbol), *_bass(symbol))]
    return estimate_key(events, time_signature=meter).key


def build_real_dataset(songs: Sequence[dict], seed: int = SEED, total: int = REAL_SONGS_EXCERPTS) -> list[dict]:
    """About `total` eight-bar excerpts of the private songs, realized like the synthetic scores.

    Every genre present gets an even share (the remainder goes to genres drawn with the seed),
    filled with one excerpt per song before any song gives its second. The k-th excerpt of the
    i-th genre takes variant (i + k) mod 6, so no genre gets only the easy or only the hard
    realizations. Every engine gets the song's key, except the corpus placeholder C major,
    which the product's own estimate over the excerpt's chords replaces.
    """
    rng = random.Random(f"{seed}:real-songs")
    by_genre: dict[str, list[tuple[dict, list[int]]]] = {}
    for number, song in enumerate(songs):
        starts = _excerpt_starts(song["bars"], random.Random(f"{seed}:song:{number}"))
        if starts:
            by_genre.setdefault(song["genre"], []).append((song, starts))
    genres = sorted(by_genre)
    share, extra = divmod(total, len(genres)) if genres else (0, 0)
    favored = set(rng.sample(genres, extra))
    chosen: list[tuple[str, dict, int]] = []
    for genre_index, genre in enumerate(genres):
        candidates = by_genre[genre]
        rng.shuffle(candidates)
        picks = [(song, starts[0]) for song, starts in candidates]
        picks += [(song, starts[1]) for song, starts in candidates if len(starts) > 1]
        chosen.extend((VARIANTS[(genre_index + k) % len(VARIANTS)], song, start)
                      for k, (song, start) in enumerate(picks[:share + (genre in favored)]))
    records = []
    for number, (variant, song, start) in enumerate(chosen):
        bars = song["bars"][start:start + BARS]
        key, key_source = song["key"], "file"
        if key == PLACEHOLDER_KEY:
            estimated = _estimated_key(bars, song["meter"])
            key, key_source = (estimated, "estimated") if estimated else (key, key_source)
        excerpt_rng = random.Random(f"{seed}:real:{number}")
        scale = _scale(key)
        realized = [_realize_bar(bar, variant, excerpt_rng, key, scale, song["meter"]) for bar in bars]
        records.append({
            "id": f"{number:02d}-{song['genre']}-{variant}", "song": song["id"], "start": start,
            "source": song["source"], "genre": song["genre"], "key": key, "keySource": key_source,
            "fileKey": song["key"], "timeSignature": list(realized[0][2]), "variant": variant,
            "bars": [{"index": index, "chords": truth, "notes": notes}
                     for index, (truth, notes, _) in enumerate(realized)],
        })
    return records


def dumps(records: list[dict]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)


def load_dataset(path: Path = DATASET_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the synthetic harmony-evaluation dataset, or with "
                                     "--songs the real-song one, outside the repository.")
    parser.add_argument("--out", type=Path, help=f"synthetic dataset path (default {repo_relative(DATASET_PATH)})")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--songs", type=Path, metavar="SONGS.jsonl",
                        help="the owner's private real songs (a file outside the repository)")
    parser.add_argument("--private-dir", type=Path, default=PRIVATE_DIR,
                        help="folder outside the repository for the real-song dataset "
                             "(default ../.tooling/score-inspection/harmony-eval)")
    args = parser.parse_args(argv)
    if args.songs is not None:
        if args.out is not None:
            parser.error("--out is the synthetic dataset; the real-song dataset goes only to --private-dir")
        try:
            songs_path = outside_repo(args.songs)
            out = outside_repo(args.private_dir) / REAL_SONGS_DATASET_NAME
        except PrivateDataError as exc:
            parser.error(str(exc))
        songs, dropped, left_out = load_songs(songs_path)
        records = build_real_dataset(songs, args.seed)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dumps(records), encoding="utf-8")
        bars = sum(len(record["bars"]) for record in records)
        print(f"wrote {out}: {len(records)} excerpts ({bars} bars) from {len({r['song'] for r in records})} of "
              f"{len(songs)} usable songs (dropped {dict(dropped)}, bars left out {dict(left_out)}), "
              f"seed {args.seed}")
        return 0
    out = args.out or DATASET_PATH
    records = build_dataset(args.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(records), encoding="utf-8")
    bars = sum(len(record["bars"]) for record in records)
    notes = sum(len(bar["notes"]) for record in records for bar in record["bars"])
    print(f"wrote {repo_relative(out)}: {len(records)} records, {bars} bars, {notes} notes, seed {args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
