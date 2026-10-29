"""Complete, bounded musical synopsis shared by harmony and song-form analysis."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.models.score_import import (
    ChordBasis, Confidence, MAX_CHORDS_PER_MEASURE, MAX_SCORE_MEASURES, MAX_SCORE_SECTIONS,
    ScoreImportResponse, StrictModel,
)
from app.models.sections import SectionType

MAX_CONTEXT_BYTES = 40 * 1024
_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class ScoreContextError(ValueError):
    pass


def _meter(value: list[int] | None) -> list[int] | None:
    if value is not None and (len(value) != 2 or not 1 <= value[0] <= 32 or value[1] not in (1, 2, 4, 8, 16, 32)):
        raise ValueError("score context meter is invalid")
    return value


class ContextMeasure(StrictModel):
    index: int = Field(ge=0, lt=MAX_SCORE_MEASURES)
    chords: list[str] = Field(max_length=MAX_CHORDS_PER_MEASURE)
    chordBasis: ChordBasis
    confidence: Confidence
    analysisSource: Literal["local", "meta"]
    noChord: bool
    timeSignature: list[int] | None
    pitchClasses: list[int] = Field(max_length=12)

    _valid_meter = field_validator("timeSignature")(_meter)

    @field_validator("chords")
    @classmethod
    def musical_symbols(cls, value: list[str]) -> list[str]:
        from app.services.harmony_meta import _symbol
        return [_symbol(symbol) for symbol in value]

    @field_validator("pitchClasses")
    @classmethod
    def pitch_classes(cls, value: list[int]) -> list[int]:
        if any(not 0 <= pitch <= 11 for pitch in value) or value != sorted(set(value)):
            raise ValueError("pitch classes must be sorted unique integers 0..11")
        return value


class ContextSection(StrictModel):
    section: SectionType | None
    startMeasure: int = Field(ge=0, lt=MAX_SCORE_MEASURES)
    length: int = Field(ge=1, le=MAX_SCORE_MEASURES)
    basis: Literal["explicit", "inferred"]


class ScoreContext(StrictModel):
    key: str | None
    timeSignature: list[int] | None
    measures: list[ContextMeasure] = Field(min_length=1, max_length=MAX_SCORE_MEASURES)
    sections: list[ContextSection] = Field(max_length=MAX_SCORE_SECTIONS)

    _valid_meter = field_validator("timeSignature")(_meter)

    @field_validator("key")
    @classmethod
    def tonal_key(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[A-G](?:#|b)? (?:major|minor)", value) is None:
            raise ValueError("score context key must be a tonal key")
        return value

    @model_validator(mode="after")
    def complete_order(self) -> "ScoreContext":
        if [bar.index for bar in self.measures] != list(range(len(self.measures))):
            raise ValueError("score context must contain every bar in written order")
        occupied: set[int] = set()
        for section in self.sections:
            end = section.startMeasure + section.length
            if end > len(self.measures):
                raise ValueError("score context section extends beyond the score")
            indices = set(range(section.startMeasure, end))
            if occupied & indices:
                raise ValueError("score context sections overlap")
            occupied.update(indices)
        return self


def validate_score_context(raw: dict) -> dict:
    try:
        context = ScoreContext.model_validate(raw).model_dump()
    except ValueError:
        raise ScoreContextError("The complete score context contains unsupported musical data; review the score or use local analysis.") from None
    if len(json.dumps(context, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ScoreContextError("The complete score context exceeds the 40 KiB analysis limit; split the score into shorter files.")
    return context


def score_context(draft: ScoreImportResponse) -> dict:
    """All bars and known section ranges, without filenames, titles or free-text annotations."""
    def pitch_classes(names: list[str]) -> list[int]:
        found = set()
        for name in names:
            match = re.fullmatch(r"([A-G])([#b]*)(?:-?\d+)?", name.replace("♯", "#").replace("♭", "b"))
            if match:
                found.add((_NATURAL[match[1]] + match[2].count("#") - match[2].count("b")) % 12)
        return sorted(found)

    return validate_score_context({
        "key": draft.key, "timeSignature": draft.timeSignature,
        "measures": [{"index": index, "chords": list(bar.chords), "chordBasis": bar.chordBasis,
                      "confidence": bar.confidence, "analysisSource": bar.analysisSource or "local",
                      "noChord": bar.noChord, "timeSignature": bar.timeSignature,
                      "pitchClasses": pitch_classes(bar.notes)} for index, bar in enumerate(draft.measures)],
        "sections": [{"section": section.section, "startMeasure": section.startMeasure,
                      "length": section.length, "basis": section.basis} for section in draft.sections],
    })
