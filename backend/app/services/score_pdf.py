"""Deterministic extraction of supported vector notation, without a model call.

The PDF text origins, not font bounding boxes, locate music glyphs. Staff lines,
barlines and stems remain vector geometry. Unsupported notation is reported; this
is not a raster OMR or a claim to reconstruct arbitrary engraving software.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import Any

import pdfplumber

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PAGE_OBJECTS = 60_000
MAX_TOTAL_GLYPHS = 250_000


class ScorePDFError(ValueError):
    pass


@dataclass
class NoteEvent:
    staff: int
    midi: int
    spelling: str
    onset: float
    duration: float | None
    x: float
    y: float
    confidence: str = "medium"
    tie_continuation: bool = False
    tie_to_next: bool = False
    written_midi: int | None = None
    written_spelling: str | None = None
    octave_shift: int = 0


@dataclass
class PrintedChord:
    symbol: str
    onset: float
    x: float


@dataclass
class ScoreMeasure:
    index: int
    page: int
    system: int
    number: int
    time_signature: tuple[int, int]
    notes: list[NoteEvent] = field(default_factory=list)
    chords: list[PrintedChord] = field(default_factory=list)
    no_chord: bool = False
    repeat_markers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    staff_warnings: dict[int, list[str]] = field(default_factory=dict)
    rhythm_exact: bool = True
    key_signature: int | None = None


@dataclass
class ParsedScore:
    title: str = ""
    key_signature: int | None = None
    key: str | None = None
    time_signature: tuple[int, int] | None = None
    measures: list[ScoreMeasure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    unsupported_counts: dict[str, int] = field(default_factory=dict)
    supported: bool = False
    complete: bool = True
    resolved_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class _Glyph:
    text: str
    font: str
    x: float
    y: float
    width: float
    size: float
    standard: bool = False


@dataclass
class _Staff:
    top: float
    bottom: float
    left: float
    right: float
    spacing: float
    glyphs: list[_Glyph] = field(default_factory=list)


@dataclass
class _OctaveMark:
    x: float
    y: float
    width: float
    amount: int
    direction: int
    glyph_ids: set[int]


@dataclass
class _OctaveSpan:
    staff: _Staff
    start: float
    end: float
    shift: int
    mark: _OctaveMark


_NOTEHEADS = {"œ": 1.0, "˙": 2.0, "w": 4.0, "\ue0a4": 1.0, "\ue0a3": 2.0, "\ue0a2": 4.0}
_CLEFS = {"&": "treble", "?": "bass", "B": "alto", "\ue050": "treble", "\ue062": "bass", "\ue05c": "alto"}
_ACCIDENTALS = {"b": -1, "♭": -1, "\ue260": -1, "#": 1, "♯": 1, "\ue262": 1,
                "n": 0, "♮": 0, "\ue261": 0, "𝄪": 2, "\ue263": 2, "𝄫": -2, "\ue264": -2}
_RESTS = {"Œ": 1.0, "‰": .5, "≈": .25, "Ó": 2.0, "∑": None,
          "\ue4e1": None, "\ue4e2": 2.0, "\ue4e3": 1.0, "\ue4e4": .5, "\ue4e5": .25,
          "\ue4e6": .125, "\ue4e7": .0625, "\ue4e8": .03125}
_FLAGS = {"j": .5, "J": .5, "r": .25, "R": .25,
          "\ue240": .5, "\ue241": .5, "\ue242": .25, "\ue243": .25,
          "\ue244": .125, "\ue245": .125, "\ue246": .0625, "\ue247": .0625}
_REPEATS = {"%", "÷", "𝄆", "𝄇", "\ue500", "\ue501", "\ue502"}
_FONT = re.compile(r"Maestro|Bravura|Petaluma|Leland|Gonville|MuseJazz", re.I)
# SMuFL's explicit alta/bassa signs; bare 8/15 use the bracket's staff side.
# https://smufl.formats.music/latest/tables/octaves.html
_OCTAVE_GLYPHS = {"\ue510": (12, 0), "\ue511": (12, 1), "\ue512": (12, -1), "\ue513": (12, -1),
                  "\ue514": (24, 0), "\ue515": (24, 1), "\ue516": (24, -1), "\ue51c": (12, -1),
                  "\ue51d": (24, -1), "\ue517": (36, 0), "\ue518": (36, 1), "\ue519": (36, -1),
                  "\ue51e": (36, -1), "\ue51f": (0, -1),
                  "𝄶": (12, 1), "𝄷": (12, -1), "𝄸": (24, 1), "𝄹": (24, -1)}
_LETTERS = "CDEFGAB"
_PCS = (0, 2, 4, 5, 7, 9, 11)
_CHORD = re.compile(r"^[A-G](?:#|b)?(?:(?:maj|min|dim|aug|sus|add|omit|no|alt|m|M|Δ|ø|°|[0-9#+−-]|\([^)]*\)))*(?:/[A-G](?:#|b)?)?$")


def _music(g: _Glyph) -> bool:
    return bool(_FONT.search(g.font)) or g.standard or g.text in _OCTAVE_GLYPHS \
        or any(0xE000 <= ord(char) <= 0xEFFF for char in g.text)


def _clef(g: _Glyph, staff: _Staff) -> str:
    selected = _CLEFS[g.text]
    if selected == "alto" and round((g.y - staff.bottom) / staff.spacing) == 3:
        return "tenor"
    return selected


def _glyphs(chars: list[dict]) -> list[_Glyph]:
    result = []
    for char in chars:
        matrix = char.get("matrix")
        if not matrix or len(matrix) != 6:
            continue
        a, b, c, d, x, y = matrix
        if abs(b) + abs(c) > .05 * max(abs(a), abs(d), 1):
            continue
        text = char.get("text", "")
        standard = any(0xE000 <= ord(value) <= 0xEFFF for value in text)
        if len(text) == 1 and 0xE080 <= ord(text) <= 0xE089:
            text = str(ord(text) - 0xE080)
        result.append(_Glyph(text, char.get("fontname", ""), float(x), float(y),
                             abs(float(char.get("x1", x)) - float(char.get("x0", x))),
                             max(abs(float(a)), abs(float(d)), float(char.get("size", 0))), standard))
    return result


def _cluster(values: list[float], tolerance: float) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and abs(value - median(groups[-1])) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [median(group) for group in groups]


def _staffs(lines: list[dict], width: float) -> list[_Staff]:
    horizontal = [line for line in lines if abs(line["y1"] - line["y0"]) < .3
                  and abs(line["x1"] - line["x0"]) > max(35, width * .08)]
    rows: list[dict] = []
    for line in sorted(horizontal, key=lambda item: -item["y0"]):
        if rows and abs(rows[-1]["y"] - line["y0"]) < .35:
            rows[-1]["segments"].append((min(line["x0"], line["x1"]), max(line["x0"], line["x1"])))
        else:
            rows.append({"y": line["y0"], "segments": [(min(line["x0"], line["x1"]), max(line["x0"], line["x1"]))]})
    for row in rows:
        segments = sorted(row["segments"])
        merged = [list(segments[0])]
        for left, right in segments[1:]:
            if left - merged[-1][1] <= 2:
                merged[-1][1] = max(merged[-1][1], right)
            else:
                merged.append([left, right])
        row["left"], row["right"] = max(merged, key=lambda segment: segment[1] - segment[0])
    result = []
    index = 0
    while index + 4 < len(rows):
        group = rows[index:index + 5]
        gaps = [group[j]["y"] - group[j + 1]["y"] for j in range(4)]
        spacing = median(gaps)
        left, right = max(row["left"] for row in group), min(row["right"] for row in group)
        if 1.5 <= spacing <= 16 and max(abs(gap - spacing) for gap in gaps) <= max(.25, spacing * .12) \
                and right - left >= max(40, width * .16):
            result.append(_Staff(group[0]["y"], group[-1]["y"], left, right, spacing))
            index += 5
        else:
            index += 1
    return result


def _verticals(lines: list[dict]) -> list[dict]:
    return [line for line in lines if abs(line["x1"] - line["x0"]) < .3
            and abs(line["y1"] - line["y0"]) > 2]


def _systems(staffs: list[_Staff], verticals: list[dict]) -> list[list[_Staff]]:
    systems: list[list[_Staff]] = []
    for staff in staffs:
        if not systems:
            systems.append([staff])
            continue
        previous = systems[-1][-1]
        gap = previous.bottom - staff.top
        connected = any(min(line["y0"], line["y1"]) <= staff.bottom + staff.spacing * .3
                        and max(line["y0"], line["y1"]) >= previous.top - previous.spacing * .3
                        for line in verticals)
        if gap < 15 * max(previous.spacing, staff.spacing) and connected:
            systems[-1].append(staff)
        else:
            systems.append([staff])
    return systems


def _assign_glyphs(staffs: list[_Staff], glyphs: list[_Glyph]) -> None:
    for g in glyphs:
        if not _music(g):
            continue
        nearest = min(staffs, key=lambda staff: max(staff.bottom - g.y, g.y - staff.top, 0))
        if nearest.left - nearest.spacing * 2 <= g.x <= nearest.right + nearest.spacing * 2 \
                and nearest.bottom - nearest.spacing * 9 <= g.y <= nearest.top + nearest.spacing * 9:
            nearest.glyphs.append(g)


def _key_signature(staff: _Staff, start: float | None = None, end: float | None = None) -> tuple[int | None, set[int]]:
    start = staff.left if start is None else start
    end = staff.right if end is None else end
    heads = [g.x for g in staff.glyphs if g.text in _NOTEHEADS and start <= g.x < end]
    first = min(heads, default=staff.right)
    candidates = sorted((g for g in staff.glyphs if g.text in ("b", "#", "n", "♭", "♯", "♮", "\ue260", "\ue261", "\ue262")
                         and start <= g.x < min(first - staff.spacing * 1.5, start + staff.spacing * 13, end)
                         and staff.bottom - staff.spacing <= g.y <= staff.top + staff.spacing), key=lambda g: g.x)
    group = []
    for g in candidates:
        if group and g.x - group[-1].x > staff.spacing * 2:
            break
        group.append(g)
    if not group:
        return None, set()
    altered = [g for g in group if _ACCIDENTALS[g.text] != 0]
    signs = {_ACCIDENTALS[g.text] for g in altered}
    if len(signs) > 1 or len(altered) > 7 or len(group) > 14:
        return None, set()
    return (next(iter(signs)) * len(altered) if signs else 0), {id(g) for g in group}


def _meters(staff: _Staff) -> list[tuple[float, tuple[int, int]]]:
    candidates = [g for g in staff.glyphs if staff.bottom - staff.spacing * .4 <= g.y <= staff.top + staff.spacing * .4]
    result = [(g.x, (4, 4)) for g in candidates if g.text in ("c", "C", "𝄴", "\ue08a")]
    result += [(g.x, (2, 2)) for g in candidates if g.text in ("¢", "𝄵", "\ue08b")]
    digits = [g for g in candidates if g.text.isdigit()]
    groups: list[list[_Glyph]] = []
    for g in sorted(digits, key=lambda item: item.x):
        if groups and g.x - max(item.x + item.width for item in groups[-1]) < staff.spacing:
            groups[-1].append(g)
        else:
            groups.append([g])
    center = (staff.top + staff.bottom) / 2
    for group in groups:
        numerator = sorted((g for g in group if g.y > center + staff.spacing * .2), key=lambda g: g.x)
        denominator = sorted((g for g in group if g.y < center - staff.spacing * .2), key=lambda g: g.x)
        if numerator and denominator:
            top = int("".join(g.text for g in numerator))
            bottom = int("".join(g.text for g in denominator))
            if 1 <= top <= 32 and bottom in (1, 2, 4, 8, 16, 32):
                result.append((min(g.x for g in group), (top, bottom)))
    return sorted(result)


def _boundaries(system: list[_Staff], verticals: list[dict]) -> list[float]:
    spacing = median(staff.spacing for staff in system)
    left, right = max(staff.left for staff in system), min(staff.right for staff in system)
    values = []
    for line in verticals:
        x = line["x0"]
        if not left - spacing <= x <= right + spacing:
            continue
        crossed = sum(min(line["y0"], line["y1"]) <= staff.bottom + spacing * .3
                      and max(line["y0"], line["y1"]) >= staff.top - spacing * .3 for staff in system)
        if crossed:
            near_head = any(abs(g.x - x) < spacing * 1.7 for staff in system for g in staff.glyphs if g.text in _NOTEHEADS)
            if crossed >= 2 or not near_head:
                values.append(x)
    values = _cluster(values, spacing * .65)
    if not values or values[0] > left + spacing:
        values.insert(0, left)
    if values[-1] < right - spacing and any(g.x > values[-1] + spacing and g.text in (*_NOTEHEADS, *_RESTS)
                                          for staff in system for g in staff.glyphs):
        values.append(right)
    return values


def _boxed(g: _Glyph, rects: list[dict], spacing: float) -> bool:
    return any(rect["x0"] - 1 <= g.x <= rect["x1"] + 1 and rect["y0"] <= g.y <= rect["y1"]
               and rect["x1"] - rect["x0"] < spacing * 8 and rect["y1"] - rect["y0"] < spacing * 8
               for rect in rects)


def _chord_text(system: list[_Staff], glyphs: list[_Glyph], rects: list[dict]) -> list[tuple[float, str]]:
    staff = system[0]
    candidates = [g for g in glyphs if (not _music(g) or (g.text in _ACCIDENTALS and g.size < staff.spacing * 3.5))
                  and staff.top + staff.spacing * .5 <= g.y <= staff.top + staff.spacing * 6
                  and staff.left <= g.x <= staff.right and not _boxed(g, rects, staff.spacing)]
    rows: list[list[_Glyph]] = []
    for g in sorted(candidates, key=lambda g: -g.y):
        if rows and abs(g.y - median(item.y for item in rows[-1])) < staff.spacing * 1.2:
            rows[-1].append(g)
        else:
            rows.append([g])
    result = []
    for row in rows:
        groups: list[list[_Glyph]] = []
        for g in sorted(row, key=lambda g: g.x):
            if groups and g.x - max(item.x + item.width for item in groups[-1]) <= staff.spacing * 1.15:
                groups[-1].append(g)
            else:
                groups.append([g])
        for group in groups:
            text = "".join(g.text for g in group).replace(" ", "").replace("♯", "#").replace("♭", "b")
            text = text.replace("−", "-")
            if re.fullmatch(r"\(?N\.?C\.?\)?", text, re.I):
                result.append((min(g.x for g in group), "N.C."))
            elif _CHORD.fullmatch(text):
                result.append((min(g.x for g in group), text))
    return sorted(result)


def _pitch(y: float, staff: _Staff, clef: str, signature: int, accidental: int | None) -> tuple[int, str]:
    bottom = {"treble": 30, "bass": 18, "alto": 24, "tenor": 22}[clef]
    diatonic = bottom + round((y - staff.bottom) / (staff.spacing / 2))
    octave, letter = divmod(diatonic, 7)
    if accidental is None:
        altered = "FCGDAEB"[:max(signature, 0)] if signature >= 0 else "BEADGCF"[:abs(signature)]
        accidental = (1 if signature > 0 else -1) if _LETTERS[letter] in altered else 0
    midi = (octave + 1) * 12 + _PCS[letter] + accidental
    return midi, _LETTERS[letter] + ({-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}[accidental]) + str(octave)


def _duration(g: _Glyph, staff: _Staff, verticals: list[dict], shapes: list[dict]) -> float | None:
    base = _NOTEHEADS[g.text]
    if base == 1:
        stems = [line for line in verticals if g.x - staff.spacing * .3 <= line["x0"] <= g.x + staff.spacing * 1.8
                 and min(line["y0"], line["y1"]) - staff.spacing * .5 <= g.y <= max(line["y0"], line["y1"]) + staff.spacing * .5
                 and abs(line["y1"] - line["y0"]) >= staff.spacing * 1.8]
        stem = min(stems, key=lambda line: abs(line["x0"] - g.x), default=None)
        if stem is None:
            return None
        flags = [flag for flag in staff.glyphs if flag.text in _FLAGS and abs(flag.x - stem["x0"]) <= staff.spacing
                 and min(stem["y0"], stem["y1"]) - staff.spacing <= flag.y <= max(stem["y0"], stem["y1"]) + staff.spacing]
        if flags:
            base = min(_FLAGS[flag.text] for flag in flags)
        else:
            beam_levels = []
            for shape in shapes:
                if not shape.get("fill") or any(op[0] == "c" for op in shape.get("path", [])):
                    continue
                if shape["x1"] - shape["x0"] < staff.spacing * .65 or shape["y1"] - shape["y0"] > staff.spacing * 1.8:
                    continue
                if shape["x0"] - staff.spacing * .1 <= stem["x0"] <= shape["x1"] + staff.spacing * .1 \
                        and min(stem["y0"], stem["y1"]) - staff.spacing * .4 <= (shape["y0"] + shape["y1"]) / 2 <= max(stem["y0"], stem["y1"]) + staff.spacing * .4:
                    beam_levels.append((shape["y0"] + shape["y1"]) / 2)
            beams = len(_cluster(beam_levels, staff.spacing * .3))
            if beams > 4:
                return None
            base = 1 / (2 ** beams)
    dots = [dot for dot in staff.glyphs if dot.text in (".", "\ue1e7")
            and g.x + g.width <= dot.x <= g.x + g.width + staff.spacing * 2.5
            and abs(dot.y - g.y) <= staff.spacing * .8]
    if dots:
        count = min(2, len(_cluster([dot.x for dot in dots], staff.spacing * .3)))
        base *= 1.5 if count == 1 else 1.75
    return base


def _tie_links(staff: _Staff, shapes: list[dict], page_height: float) -> tuple[dict[int, int], set[int]]:
    """Resolve only adjacent equal-position notes with aligned curve endpoints.

    A slur spanning intermediate notes, different staff positions, a partial
    system-end curve, or ambiguous chord endpoints remains unsupported.
    """
    heads = [g for g in staff.glyphs if g.text in _NOTEHEADS]
    links: dict[int, int] = {}
    resolved: set[int] = set()
    for shape in shapes:
        path = shape.get("path", [])
        if not any(op[0] == "c" for op in path) or shape["x1"] - shape["x0"] < staff.spacing * 2:
            continue
        endpoints = [op[-1] for op in path if op[0] in ("m", "l", "c") and len(op) > 1]
        if not endpoints:
            continue
        first = min(endpoints, key=lambda point: point[0])
        last = max(endpoints, key=lambda point: point[0])
        first_y, last_y = page_height - first[1], page_height - last[1]
        if abs(first_y - last_y) > staff.spacing * .3:
            continue
        sources = [g for g in heads if 0 <= shape["x0"] - g.x <= staff.spacing * 3
                   and staff.spacing * .15 <= abs(first_y - g.y) <= staff.spacing * 1.5]
        targets = [g for g in heads if abs(shape["x1"] - g.x) <= staff.spacing * 1.5
                   and staff.spacing * .15 <= abs(last_y - g.y) <= staff.spacing * 1.5]
        pairs = []
        for source in sources:
            for target in targets:
                if source.x >= target.x or abs(source.y - target.y) > staff.spacing * .15:
                    continue
                if any(source.x < g.x < target.x and g.text in _CLEFS for g in staff.glyphs):
                    continue
                if any(source.x + staff.spacing * 1.8 < head.x < target.x - staff.spacing * 1.8 for head in heads):
                    continue
                score = abs(first_y - source.y) + abs(last_y - target.y) \
                    + abs(shape["x0"] - source.x - source.width) * .25 + abs(shape["x1"] - target.x) * .25
                pairs.append((score, source, target))
        pairs.sort(key=lambda item: item[0])
        if not pairs or (len(pairs) > 1 and pairs[1][0] - pairs[0][0] < staff.spacing * .25):
            continue
        _, source, target = pairs[0]
        if id(target) in links and links[id(target)] != id(source):
            continue
        links[id(target)] = id(source)
        resolved.add(id(shape))
    return links, resolved


def _octave_marks(glyphs: list[_Glyph], spacing: float) -> list[_OctaveMark]:
    marks = []
    for g in glyphs:
        if g.text in _OCTAVE_GLYPHS:
            amount, direction = _OCTAVE_GLYPHS[g.text]
            marks.append(_OctaveMark(g.x, g.y, g.width, amount, direction, {id(g)}))
        elif g.text == "√" and re.search("Maestro", g.font, re.I):
            marks.append(_OctaveMark(g.x, g.y, g.width, 12, 0, {id(g)}))
    rows: list[list[_Glyph]] = []
    for g in sorted((g for g in glyphs if not _music(g) and g.text.strip()), key=lambda g: -g.y):
        if rows and abs(g.y - median(item.y for item in rows[-1])) <= spacing * .8:
            rows[-1].append(g)
        else:
            rows.append([g])
    for row in rows:
        groups: list[list[_Glyph]] = []
        for g in sorted(row, key=lambda item: item.x):
            if groups and g.x - max(item.x + item.width for item in groups[-1]) <= spacing * .8:
                groups[-1].append(g)
            else:
                groups.append([g])
        for group in groups:
            text = "".join(g.text for g in group).replace(" ", "").strip("()").lower()
            if re.fullmatch(r"8(?:va|vb|ba)|15m[ab]|22m[ab]", text):
                amount = 12 if text.startswith("8") else (24 if text.startswith("15") else 36)
                direction = -1 if text.endswith(("vb", "ba", "mb")) else 0
                start = min(g.x for g in group)
                marks.append(_OctaveMark(start, median(g.y for g in group), max(g.x + g.width for g in group) - start,
                                         amount, direction, {id(g) for g in group}))
    unique: dict[tuple, _OctaveMark] = {}
    for mark in marks:
        key = (round(mark.x / (spacing * .2)), round(mark.y / (spacing * .2)), mark.amount, mark.direction)
        if key in unique:
            unique[key].glyph_ids.update(mark.glyph_ids)
        else:
            unique[key] = mark
    return list(unique.values())


def _octave_spans(staffs: list[_Staff], glyphs: list[_Glyph], lines: list[dict]) \
        -> tuple[list[_OctaveSpan], list[_OctaveMark], set[int]]:
    """Read only a single-system dashed bracket with a correctly directed hook."""
    spacing = median(staff.spacing for staff in staffs)
    marks = _octave_marks(glyphs, spacing)
    dashed = [line for line in lines if line.get("dash") and line["dash"][0]
              and any(length > 0 for length in line["dash"][0])
              and abs(line["y1"] - line["y0"]) <= spacing * .08
              and line["x1"] - line["x0"] >= spacing * 3]
    spans = []
    for mark in marks:
        if mark.amount not in (12, 24):
            continue
        candidates = []
        for line in dashed:
            start, end, y = line["x0"], line["x1"], (line["y0"] + line["y1"]) / 2
            if start < mark.x or not -spacing <= start - mark.x - mark.width <= spacing * 6 \
                    or abs(y - mark.y) > spacing * 2:
                continue
            owners = []
            for staff in staffs:
                if not staff.left - staff.spacing <= mark.x < end <= staff.right + staff.spacing:
                    continue
                if y > staff.top + staff.spacing * .4:
                    direction, gap = 1, y - staff.top
                elif y < staff.bottom - staff.spacing * .4:
                    direction, gap = -1, staff.bottom - y
                else:
                    continue
                if gap > staff.spacing * 10 or (mark.direction and mark.direction != direction):
                    continue
                owners.append((gap / staff.spacing, staff, direction))
            owners.sort(key=lambda item: item[0])
            if not owners or (len(owners) > 1 and owners[1][0] - owners[0][0] <= 1):
                continue
            _, staff, direction = owners[0]
            hooks = []
            for hook in lines:
                if hook.get("dash") and hook["dash"][0]:
                    continue
                low, high = min(hook["y0"], hook["y1"]), max(hook["y0"], hook["y1"])
                if abs(hook["x1"] - hook["x0"]) > staff.spacing * .08 \
                        or abs(hook["x0"] - end) > staff.spacing * .3 \
                        or not staff.spacing * .25 <= high - low <= staff.spacing * 3:
                    continue
                if direction > 0 and abs(high - y) <= staff.spacing * .2 and low < y - staff.spacing * .2:
                    hooks.append(hook)
                elif direction < 0 and abs(low - y) <= staff.spacing * .2 and high > y + staff.spacing * .2:
                    hooks.append(hook)
            if hooks:
                candidates.append(_OctaveSpan(staff, mark.x, end, mark.amount * direction, mark))
        unique = {(id(span.staff), round(span.start, 3), round(span.end, 3), span.shift): span for span in candidates}
        if len(unique) == 1:
            spans.append(next(iter(unique.values())))
    ambiguous = {id(first) for first in spans for second in spans if first is not second and first.staff is second.staff
                 and min(first.end, second.end) - max(first.start, second.start) > first.staff.spacing * .2}
    spans = [span for span in spans if id(span) not in ambiguous]
    resolved_ids = {identity for span in spans for identity in span.mark.glyph_ids}
    return spans, marks, resolved_ids


def _octave_shift(g: _Glyph, staff: _Staff, spans: list[_OctaveSpan]) -> int:
    return next((span.shift for span in spans if span.staff is staff
                 and span.start - staff.spacing * .1 <= g.x <= span.end + staff.spacing * .1), 0)


def _shift_spelling(spelling: str, shift: int) -> str:
    match = re.fullmatch(r"([A-G](?:#{1,2}|b{1,2})?)(-?\d+)", spelling)
    if match is None:
        return spelling
    return match[1] + str(int(match[2]) + shift // 12)


def _warning(measure: ScoreMeasure, staff: int, message: str) -> None:
    if message not in measure.warnings:
        measure.warnings.append(message)
    values = measure.staff_warnings.setdefault(staff, [])
    if message not in values:
        values.append(message)
    measure.rhythm_exact = False


def _parse_pages(pages: Any, *, max_measures: int = 512) -> ParsedScore:
    parsed = ParsedScore()
    clefs: dict[int, str] = {}
    keys: dict[int, int] = {}
    current_meter = (4, 4)
    meter_known = False
    total_glyphs = 0
    counts: Counter = Counter()
    resolved_counts: Counter = Counter()
    for page_number, page in enumerate(pages, 1):
        chars, lines = page.chars, page.lines
        total_glyphs += len(chars)
        if total_glyphs > MAX_TOTAL_GLYPHS or len(chars) + len(lines) > MAX_PAGE_OBJECTS:
            raise ScorePDFError("The vector score exceeds the bounded glyph/geometry limit.")
        glyphs = _glyphs(chars)
        note_objects: dict[int, NoteEvent] = {}
        rotated_music = []
        for char in chars:
            matrix = char.get("matrix")
            if matrix and len(matrix) == 6 and (char.get("text") in (*_NOTEHEADS, *_CLEFS)):
                a, b, c, d, _, _ = matrix
                if abs(b) + abs(c) > .05 * max(abs(a), abs(d), 1) or a <= 0 or d <= 0:
                    rotated_music.append(char)
        if rotated_music:
            counts["rotated_music_glyph"] += len(rotated_music)
            parsed.complete = False
        staffs = _staffs(lines, float(page.width))
        if not staffs:
            counts["pages_without_supported_staff_geometry"] += 1
            parsed.complete = False
            continue
        if not parsed.title:
            title_candidates = [g for g in glyphs if not _music(g) and g.y > staffs[0].top + staffs[0].spacing * 8 and g.text]
            if title_candidates:
                largest = max(g.size for g in title_candidates)
                chosen = sorted((g for g in title_candidates if g.size >= largest * .8), key=lambda g: g.x)
                parsed.title = "".join(g.text for g in chosen).strip()[:120]
        _assign_glyphs(staffs, glyphs)
        unknown_heads = [g for g in glyphs if not _music(g) and g.text in ("œ", "˙")
                         and any(staff.bottom - staff.spacing * 6 < g.y < staff.top + staff.spacing * 6 for staff in staffs)]
        unsupported_heads = [g for g in glyphs if any(0xE0A0 <= ord(c) <= 0xE0FF for c in g.text) and g.text not in _NOTEHEADS]
        unsupported_clefs = [g for g in glyphs if any(0xE050 <= ord(c) <= 0xE06F for c in g.text) and g.text not in _CLEFS]
        composite_notes = [g for g in glyphs if any(0xE1D0 <= ord(c) <= 0xE1E6 for c in g.text)]
        for name, items in (("unknown_legacy_music_font", unknown_heads), ("unsupported_notehead", unsupported_heads),
                            ("unsupported_clef", unsupported_clefs), ("unsupported_composite_note", composite_notes)):
            if items:
                counts[name] += len(items)
                parsed.complete = False
        verticals = _verticals(lines)
        shapes = list(getattr(page, "curves", [])) + list(getattr(page, "rects", []))
        if len(chars) + len(lines) + len(shapes) > MAX_PAGE_OBJECTS:
            raise ScorePDFError("The vector score exceeds the bounded glyph/geometry limit.")
        octave_spans, octave_marks, resolved_octave_ids = _octave_spans(staffs, glyphs, lines)
        unresolved_octaves = [mark for mark in octave_marks if not mark.glyph_ids <= resolved_octave_ids]
        resolved_counts["ottava_spans"] += len(octave_spans)
        counts["ottava"] += len(unresolved_octaves)
        tie_links: dict[int, int] = {}
        resolved_tie_shapes: set[int] = set()
        for staff in staffs:
            links, resolved = _tie_links(staff, shapes, float(page.height))
            tie_links.update(links)
            resolved_tie_shapes.update(resolved)
        for system_number, system in enumerate(_systems(staffs, verticals), 1):
            bounds = _boundaries(system, verticals)
            if len(bounds) < 2:
                counts["systems_without_measure_boundaries"] += 1
                parsed.complete = False
                continue
            meter_events = _meters(system[0])
            chords = _chord_text(system, glyphs, list(getattr(page, "rects", [])))
            signature_ids: set[int] = set()
            for staff_index, staff in enumerate(system):
                signature, ids = _key_signature(staff)
                if signature is None and staff_index not in keys and _meters(staff):
                    first_head = min((g.x for g in staff.glyphs if g.text in _NOTEHEADS), default=staff.right)
                    header = [g for g in staff.glyphs if g.x < first_head and staff.bottom - staff.spacing <= g.y <= staff.top + staff.spacing]
                    if any(g.text in _CLEFS for g in header) and not any(g.text in _ACCIDENTALS for g in header):
                        signature = 0
                signature_ids.update(ids)
                if signature is not None:
                    keys[staff_index] = signature
                    if parsed.key_signature is None:
                        parsed.key_signature = signature
            for bar_index, (left, right) in enumerate(zip(bounds, bounds[1:])):
                if len(parsed.measures) >= max_measures:
                    parsed.complete = False
                    counts["measure_limit"] += 1
                    break
                for x, meter in meter_events:
                    if x < right:
                        current_meter = meter
                        meter_known = True
                for staff_index, staff in enumerate(system):
                    signature, ids = _key_signature(staff, left, right)
                    if signature is not None:
                        keys[staff_index] = signature
                        signature_ids.update(ids)
                if parsed.time_signature is None and meter_known:
                    parsed.time_signature = current_meter
                measure = ScoreMeasure(len(parsed.measures), page_number, system_number, len(parsed.measures) + 1,
                                       current_meter, key_signature=keys.get(0))
                beats = current_meter[0] * 4 / current_meter[1]
                if not meter_known:
                    measure.warnings.append("No readable time signature; 4/4 timing is provisional.")
                    measure.rhythm_exact = False
                    counts["missing_meter"] += 1
                all_atoms: list[tuple[float, float]] = []
                for staff_index, staff in enumerate(system):
                    records = sorted((g for g in staff.glyphs if left - staff.spacing * .2 <= g.x < right - staff.spacing * .2), key=lambda g: g.x)
                    initial_clef = clefs.get(staff_index)
                    if initial_clef is None:
                        initial_clef = "treble"
                    clef_events = [(g.x, _clef(g, staff), g) for g in staff.glyphs if g.text in _CLEFS and g.x < right]
                    clef = initial_clef
                    for x, selected, _ in sorted(clef_events):
                        if x <= left:
                            clef = selected
                    if staff_index not in clefs and not clef_events:
                        _warning(measure, staff_index, "No supported clef was present; treble position is provisional.")
                        counts["missing_clef"] += 1
                    accidentals: dict[int, int] = {}
                    note_records: list[tuple[_Glyph, NoteEvent]] = []
                    rests = []
                    for g in records:
                        if g.text in _CLEFS:
                            clef = _clef(g, staff)
                        elif g.text in _ACCIDENTALS and id(g) not in signature_ids:
                            step = round((g.y - staff.bottom) / (staff.spacing / 2))
                            accidentals[step] = _ACCIDENTALS[g.text]
                        elif g.text in _NOTEHEADS:
                            step_float = (g.y - staff.bottom) / (staff.spacing / 2)
                            if abs(step_float - round(step_float)) > .22:
                                _warning(measure, staff_index, "A notehead does not align reliably to a staff line or space.")
                                counts["unaligned_notehead"] += 1
                            written_midi, written_spelling = _pitch(g.y, staff, clef, keys.get(staff_index, 0), accidentals.get(round(step_float)))
                            shift = _octave_shift(g, staff, octave_spans)
                            tied_source = note_objects.get(tie_links.get(id(g), -1))
                            if tied_source is not None:
                                source_written_midi = tied_source.written_midi if tied_source.written_midi is not None else tied_source.midi
                                source_written_spelling = tied_source.written_spelling or tied_source.spelling
                                if round(step_float) in accidentals and written_midi != source_written_midi:
                                    _warning(measure, staff_index, "A possible tie conflicts with a written accidental; its pitch needs review.")
                                    counts["tie_accidental_conflict"] += 1
                                    tied_source = None
                                elif source_written_midi + shift != tied_source.midi:
                                    _warning(measure, staff_index, "A possible tie crosses an octave-span boundary; sounding-pitch continuity needs review.")
                                    counts["tie_octave_conflict"] += 1
                                    tied_source = None
                                else:
                                    written_midi, written_spelling = source_written_midi, source_written_spelling
                            midi, spelling = written_midi + shift, _shift_spelling(written_spelling, shift)
                            if not 0 <= midi <= 127:
                                counts["out_of_range_pitch"] += 1
                                parsed.complete = False
                                continue
                            duration = _duration(g, staff, verticals, shapes)
                            note = NoteEvent(staff_index, midi, spelling, 0, duration, g.x, g.y)
                            if shift:
                                note.written_midi, note.written_spelling, note.octave_shift = written_midi, written_spelling, shift
                                resolved_counts["octave_shifted_notes"] += 1
                            if tied_source is not None:
                                note.tie_continuation = True
                                tied_source.tie_to_next = True
                            note_objects[id(g)] = note
                            if duration is None:
                                _warning(measure, staff_index, "A note duration could not be resolved from its stem, beams or flags.")
                                counts["unknown_duration"] += 1
                            note_records.append((g, note))
                        elif g.text in _RESTS:
                            rests.append((g.x, _RESTS[g.text] if _RESTS[g.text] is not None else beats))
                        elif g.text in _REPEATS:
                            measure.repeat_markers.append(g.text)
                            counts["unexpanded_repeat"] += 1
                    clefs[staff_index] = clef
                    groups: list[list[tuple[_Glyph, NoteEvent]]] = []
                    for record in note_records:
                        if groups and record[0].x - groups[-1][0][0].x <= staff.spacing * 1.4:
                            groups[-1].append(record)
                        else:
                            groups.append([record])
                    atoms = [(group[0][0].x, min((note.duration for _, note in group if note.duration is not None), default=None), group) for group in groups]
                    atoms.extend((x, duration, []) for x, duration in rests)
                    atoms.sort(key=lambda item: item[0])
                    total = sum(duration or 0 for _, duration, _ in atoms)
                    sequential = all(duration is not None for _, duration, _ in atoms) and abs(total - beats) <= .06
                    if atoms and not sequential:
                        _warning(measure, staff_index, "Rhythm/voices do not sum to the written meter; onsets use provisional horizontal alignment.")
                        counts["rhythm_alignment"] += 1
                    cursor = 0.0
                    first_x = atoms[0][0] if atoms else left
                    last_x = atoms[-1][0] if atoms else right
                    for x, duration, group in atoms:
                        onset = cursor if sequential else max(0, min(beats, (x - first_x) / max(last_x - first_x + staff.spacing * 4, 1) * beats))
                        for _, note in group:
                            note.onset = round(onset, 6)
                            note.confidence = "high" if sequential and measure.rhythm_exact else "medium"
                            measure.notes.append(note)
                        all_atoms.append((x, onset))
                        cursor += duration or 0
                    for shape in shapes:
                        if shape["x1"] < left or shape["x0"] > right:
                            continue
                        is_curve = id(shape) not in resolved_tie_shapes and any(op[0] == "c" for op in shape.get("path", []))
                        if is_curve and shape["x1"] - shape["x0"] > staff.spacing * 2 \
                                and 0 < shape["y1"] - shape["y0"] < staff.spacing * 4 \
                                and staff.bottom - staff.spacing * 7 < shape["y1"] < staff.top + staff.spacing * 7:
                            _warning(measure, staff_index, "Tie/slur geometry is present; tied duration and voice continuity require review.")
                            counts["tie_or_slur"] += 1
                    for g in records:
                        if g.text in ("3", "5", "6", "7", "9") and g.y > staff.top + staff.spacing * .5:
                            _warning(measure, staff_index, "A possible tuplet needs review; tuplet timing has not been applied.")
                            counts["possible_tuplet"] += 1
                for x, symbol in chords:
                    if left - system[0].spacing * .2 <= x < right - system[0].spacing * .2:
                        if symbol == "N.C.":
                            measure.no_chord = True
                        else:
                            onset = min(all_atoms, key=lambda atom: abs(atom[0] - x))[1] if all_atoms else 0.0
                            measure.chords.append(PrintedChord(symbol, round(onset, 6), x))
                text = "".join(g.text for g in sorted(glyphs, key=lambda g: g.x)
                               if not _music(g) and id(g) not in resolved_octave_ids and left <= g.x < right
                               and system[-1].bottom - system[-1].spacing * 10 < g.y < system[0].top + system[0].spacing * 12)
                unresolved_here = [mark for mark in unresolved_octaves if left <= mark.x < right
                                   and min(staffs, key=lambda staff: max(staff.bottom - mark.y, mark.y - staff.top, 0)) in system]
                if unresolved_here:
                    measure.warnings.append("An octave indication has no unambiguous bounded bracket; its pitches remain written until the span is reviewed.")
                    measure.rhythm_exact = False
                elif re.search(r"(?:8v[ab]|8ba|15m[ab]|22m[ab]|ottava)", text, re.I):
                    measure.warnings.append("Octave text is present but its bounded span is unresolved; pitches remain written.")
                    measure.rhythm_exact = False
                    counts["ottava"] += 1
                if not measure.rhythm_exact:
                    for note in measure.notes:
                        note.confidence = "medium"
                measure.notes.sort(key=lambda note: (note.onset, note.staff, note.midi))
                parsed.measures.append(measure)
            for _, meter in meter_events:
                current_meter = meter
        if len(parsed.measures) >= max_measures and page_number < len(pages):
            parsed.complete = False
            counts["measure_limit"] += 1
            break
    parsed.supported = any(measure.notes or measure.chords or measure.no_chord for measure in parsed.measures)
    if not parsed.supported:
        parsed.complete = False
        parsed.warnings.append("No supported vector noteheads or printed chord labels could be extracted.")
    if counts:
        parsed.unsupported_counts = {name: count for name, count in counts.items() if count}
        parsed.unresolved = [f"{name}: {count}" for name, count in sorted(counts.items()) if count]
    parsed.resolved_counts = {name: count for name, count in resolved_counts.items() if count}
    if resolved_counts["ottava_spans"]:
        parsed.warnings.append(f"Applied {resolved_counts['ottava_spans']} bounded octave spans; original written pitches are retained alongside sounding pitches.")
    if any(not measure.rhythm_exact for measure in parsed.measures):
        parsed.warnings.append("Some durations or onsets are provisional; review the per-measure notation warnings.")
    if parsed.key_signature is not None:
        parsed.warnings.append("Key signature is extracted independently of tonal-center analysis; relative major/minor is not assumed.")
    return parsed


def parse_vector_score(data: bytes, *, max_pages: int = 50, max_measures: int = 512) -> ParsedScore:
    if not isinstance(data, bytes) or not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        raise ScorePDFError("Choose a nonempty PDF up to 8 MiB for local vector analysis.")
    if not 1 <= max_pages <= 50 or not 1 <= max_measures <= 512:
        raise ScorePDFError("Local vector analysis supports 1..50 pages and 1..512 measures.")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if not 1 <= len(pdf.pages) <= max_pages:
                raise ScorePDFError(f"The PDF exceeds the local limit of {max_pages} pages.")
            return _parse_pages(pdf.pages, max_measures=max_measures)
    except ScorePDFError:
        raise
    except Exception as exc:
        raise ScorePDFError("The PDF could not be decoded into supported vector geometry.") from exc
