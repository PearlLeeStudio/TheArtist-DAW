"""Sparse substitution proposals. Every address is zero-based; the score is input only."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Family = Literal["common_tones", "modal", "dominant"]
Mode = Literal["auto", "ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian"]


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    measureIndex: int = Field(ge=0, le=255)
    slotIndex: Literal[0, 1]


class ReharmBar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    measure: int = Field(ge=0, le=255)
    chords: list[str | None] = Field(min_length=2, max_length=2)


class ReharmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-G][#b]? (major|minor)$")
    timeSignature: tuple[int, int] = (4, 4)
    context: list[ReharmBar] = Field(min_length=1, max_length=256)
    selectedSlots: list[Slot] = Field(min_length=1, max_length=16)
    maxChanges: Literal[1, 2] = 1
    mode: Mode = "auto"
    modelKey: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def valid_passage(self):
        bars = {bar.measure: bar.chords for bar in self.context}
        if len(bars) != len(self.context) or sorted(bars) != list(range(len(bars))):
            raise ValueError("Context must contain consecutive unique measures starting at zero.")
        addresses = {(s.measureIndex, s.slotIndex) for s in self.selectedSlots}
        if len(addresses) != len(self.selectedSlots):
            raise ValueError("Selected slots must be unique.")
        if max(m for m, _ in addresses) - min(m for m, _ in addresses) >= 8:
            raise ValueError("Select a passage spanning at most eight measures.")
        if any(not bars.get(m, [None, None])[s] for m, s in addresses):
            raise ValueError("Select existing chords for reharmonization; empty slots are not filled.")
        if any(symbol is not None and (not symbol.strip() or len(symbol) > 40)
               for chords in bars.values() for symbol in chords):
            raise ValueError("Chord symbols must be nonempty and at most 40 characters.")
        if self.timeSignature not in ((4, 4), (3, 4), (6, 8), (2, 4), (5, 4)):
            raise ValueError("This meter is outside the Music Transformer vocabulary.")
        return self


class Change(BaseModel):
    address: Slot
    before: str
    after: str
    commonTones: int
    modes: list[str]
    conventions: list[str] = Field(default_factory=list)


class ReharmCandidate(BaseModel):
    id: str
    family: Family
    changes: list[Change]
    pitchDistance: float
    originalPitchDistance: float
    bassMotion: float
    originalBassMotion: float
    mathScore: float
    conventionScore: float = 0.0
    modelScore: float | None = None


class ReharmResponse(BaseModel):
    candidates: list[ReharmCandidate]
    modelUsed: str
    contextMeasures: list[int]
    metaModel: str
    requestIds: list[str]
    costUsd: float
    toolCalls: list[str]
