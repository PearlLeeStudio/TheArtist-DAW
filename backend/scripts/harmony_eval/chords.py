"""Chord-symbol normalization and the editor's two-slot alignment.

A symbol becomes (root pitch class, triad, seventh family, bass pitch class), so
enharmonic spellings and the common quality spellings compare equal. Added
tones, omissions and alterations carry no triad or seventh information here and
are ignored; the half-diminished idiom (m7b5, ø) is read before alterations are
dropped. Anything else is None.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import NamedTuple

TRIADS = ("maj", "min", "dim", "aug", "sus")
SEVENTHS = ("none", "maj7", "dom7", "min7", "halfdim7", "dim7", "sixth")
_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ROOT = re.compile(r"([A-G])(#{1,2}|b{1,2})?")
_BASS = re.compile(r"/([A-G](?:#|b)?)\Z")
_SIXTH = ("6", "6/9", "69")
_HALF_DIMINISHED = re.compile(r"m(?:7|9|11|13)?b5")
# A canonical quality: a sus chord (with the dominant extension written before "sus"), or a
# triad word and one extension; "5" (power chord) and "2" (add9 shorthand) score as major triads.
_QUALITY = re.compile(r"(?P<pre>7|9|11|13)?sus(?:2|4)?"
                      r"|(?P<triad>maj|m|dim|aug)?(?P<ext>maj(?:7|9|11|13)?|6/9|69|6|7|9|11|13|5|2)?")
# Alterations, additions and "alt": dropped after the half-diminished check.
_IGNORED = re.compile(r"[#b+-](?:4|5|6|9|11|13)|(?:add|omit|no)\d+|alt")
# Δ with its extension (Δ9 is maj9, not "maj7" + "9"), a bare Δ as maj7
_DELTA = re.compile(r"[Δ∆](7|9|11|13)?")
_UNICODE = (("♯", "#"), ("♭", "b"), ("°7", "dim7"), ("°", "dim"), ("º", "dim"), ("ø7", "m7b5"),
            ("Ø7", "m7b5"), ("ø", "m7b5"), ("Ø", "m7b5"))
# Quality words in the order that keeps "dim" from being read as a minor "min"
# and "maj" from being read as "ma" + digit; a capital M alone means major.
_WORDS = ((re.compile(r"(?i)dim(?:inished)?"), "dim"), (re.compile(r"(?i)aug(?:mented)?"), "aug"),
          (re.compile(r"(?i)sus(?:pended)?"), "sus"), (re.compile(r"(?i)maj(?:or)?"), "maj"),
          (re.compile(r"(?i)ma(?=\d)"), "maj"), (re.compile(r"M(?=\d|aj|\Z)"), "maj"),
          (re.compile(r"(?i)min(?:or)?"), "m"), (re.compile(r"mi(?=\d|\Z)"), "m"),
          (re.compile(r"\Ao(?=\d|\Z)"), "dim"))


class Chord(NamedTuple):
    root: int
    triad: str
    seventh: str
    bass: int


def pitch_class(name: str) -> int | None:
    """``Eb`` -> 3, ``B#`` -> 0; None for anything that is not a note name."""
    match = _ROOT.fullmatch(name or "")
    if match is None:
        return None
    letter, accidental = match.groups()
    return (_NATURAL[letter] + (accidental or "").count("#") - (accidental or "").count("b")) % 12


def _canonical_quality(text: str) -> str:
    text = _DELTA.sub(lambda match: "maj" + (match[1] or "7"), text)
    for source, target in _UNICODE:
        text = text.replace(source, target)
    text = text.replace("(", "").replace(")", "").replace(",", "")
    if text.startswith("-"):
        text = "m" + text[1:]
    elif text.startswith("+"):
        text = "aug" + text[1:]
    for pattern, replacement in _WORDS:
        text = pattern.sub(replacement, text)
    return text


def _quality(text: str) -> tuple[str, str] | None:
    """(triad, seventh family) of a canonical quality string; None when it is not a chord quality."""
    if _HALF_DIMINISHED.fullmatch(text):
        return "dim", "halfdim7"
    text = _IGNORED.sub("", text).replace("+", "")
    match = _QUALITY.fullmatch(text)
    if match is None:
        return None
    if "sus" in text:
        return "sus", "dom7" if match["pre"] else "none"
    triad_word, extension = match["triad"] or "", match["ext"] or ""
    triad = {"": "maj", "maj": "maj", "m": "min", "dim": "dim", "aug": "aug", "sus": "sus"}[triad_word]
    if extension.startswith("maj"):
        seventh = "maj7"
    elif extension in _SIXTH:
        seventh = "sixth"
    elif extension in ("", "5", "2"):
        seventh = "none"
    elif triad_word == "maj":
        seventh = "maj7"
    elif triad_word == "m":
        seventh = "min7"
    elif triad_word == "dim":
        seventh = "dim7"
    else:
        seventh = "dom7"
    return triad, seventh


def normalize(symbol: object) -> Chord | None:
    if not isinstance(symbol, str):
        return None
    text = symbol.strip().replace("♯", "#").replace("♭", "b")
    root_match = _ROOT.match(text)
    if root_match is None:
        return None
    root = pitch_class(root_match[0])
    rest = text[root_match.end():]
    bass = root
    bass_match = _BASS.search(rest)
    if bass_match is not None:
        bass = pitch_class(bass_match[1])
        rest = rest[:bass_match.start()]
    quality = _quality(_canonical_quality(rest))
    if root is None or bass is None or quality is None:
        return None
    return Chord(root, quality[0], quality[1], bass)


def align(chords: Sequence[str | None]) -> tuple[str | None, str | None]:
    """The editor's two slots per bar, as the import fills them.

    One chord fills both slots and two map slot-wise; no chord, or more than two,
    leaves both slots empty (the import keeps such a bar unresolved for review).
    """
    symbols = [symbol for symbol in chords if symbol]
    if len(symbols) == 1:
        return symbols[0], symbols[0]
    if len(symbols) == 2:
        return symbols[0], symbols[1]
    return None, None
