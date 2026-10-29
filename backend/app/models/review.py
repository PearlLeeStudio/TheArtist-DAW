"""Request and response models of the second-ear review (POST /api/review/candidates).

Strict like the planner's models: unknown fields are rejected and the shape is checked
here (HTTP 422) before any fact is computed or any model is called.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.plan import _KEY
from app.models.sections import CHORDS_PER_BAR, MAX_SECTION_BARS, SectionType
from app.services.genre_tables import GENRE_DEFAULTS

MIN_CANDIDATES = 2
MAX_CANDIDATES = 3
MAX_REASONS = 2
MAX_CLAIM_CHARS = 120
# The facts a reason may cite; rulesSlots is context (the same slots for every candidate), not a reason
FACT_NAMES = ("outOfKeyRatio", "changedSlots", "repetitionVsPrevious", "r1Roughness")
FactName = Literal["outOfKeyRatio", "changedSlots", "repetitionVsPrevious", "r1Roughness"]

# Chord symbols as the editor writes them, bounded like the planner's sketch
_Symbol = Annotated[str, Field(max_length=32)]
_Measure = Annotated[list[_Symbol | None], Field(min_length=CHORDS_PER_BAR, max_length=CHORDS_PER_BAR)]
_Bars = Annotated[list[_Measure], Field(min_length=1, max_length=MAX_SECTION_BARS)]


class ReviewCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$",
                       description="The candidate's name in the choice, e.g. A")
    chords: _Bars = Field(description="Per measure, the two slots as Apply would write them; null = empty")


class ReviewRequest(BaseModel):
    """The A/B/C candidates of one Generate over the same bars, the bars' original chords and,
    when the bars sit in a section, the section before it."""
    model_config = ConfigDict(extra="forbid")
    key: str = Field(..., examples=["C major", "A minor"])
    genre: str | None = Field(default=None, description="One of the 13 genres; null when the song has none")
    sectionType: SectionType | None = Field(default=None, description="The section Generate used; null = no "
                                                                      "song-form rules")
    original: _Bars = Field(description="The bars' chords before the generation, two slots per measure")
    candidates: list[ReviewCandidate] = Field(min_length=MIN_CANDIDATES, max_length=MAX_CANDIDATES)
    previousSection: _Bars | None = Field(default=None, description="The section before the bars' section; "
                                                                    "null when there is none")

    @field_validator("key")
    @classmethod
    def _key_format(cls, v: str) -> str:
        parts = v.strip().split()
        key = f"{parts[0][:1].upper()}{parts[0][1:]} {parts[1].lower()}" if len(parts) == 2 else v
        if not _KEY.fullmatch(key):
            raise ValueError("expected key format: 'C major' or 'A minor'")
        return key

    @field_validator("genre")
    @classmethod
    def _known_genre(cls, v: str | None) -> str | None:
        if v is not None and v not in GENRE_DEFAULTS:
            raise ValueError(f"unknown genre {v!r}; expected one of: {', '.join(GENRE_DEFAULTS)}")
        return v

    @model_validator(mode="after")
    def _aligned_candidates(self) -> "ReviewRequest":
        labels = [candidate.label for candidate in self.candidates]
        if len(set(labels)) != len(labels):
            raise ValueError("candidate labels must be unique")
        if any(len(candidate.chords) != len(self.original) for candidate in self.candidates):
            raise ValueError("every candidate must cover the same measures as original")
        return self


class CandidateFacts(BaseModel):
    """What code computed about one candidate, over all of its slots as Apply would write them."""
    label: str
    outOfKeyRatio: float | None         # share of its chords with a tone outside the key; null without chords
    changedSlots: int                   # slots whose chord differs from original
    repetitionVsPrevious: float | None  # share of its chords equal to the previous section's at that slot
    r1Roughness: float | None           # mean Sethares roughness per chord; null without the physics code
    rulesSlots: list[int]               # slots the song-form rules write for sectionType (0-based)


class ReviewReason(BaseModel):
    fact: str                            # "<factName>=<value>" as the judge stated it
    factName: FactName
    value: float | None                  # the judge's value; null when it was not a finite number
    claim: str
    confirmed: bool                      # the value matches the analyzer's table for the chosen candidate
    analyzerValue: float | None          # the table's value for the chosen candidate


class ReviewResponse(BaseModel):
    choice: str
    reasons: list[ReviewReason]
    facts: list[CandidateFacts]
    provider: str
    model: str
    requestId: str | None
    costUsd: float
    latencyMs: int
    source: Literal["judge"] = "judge"


class ReviewError(BaseModel):
    """kind: disabled (Meta switched off) | config | budget | timeout | llm, as the planner's PlanError."""
    kind: Literal["disabled", "config", "budget", "timeout", "llm"]
    message: str
    requestId: str | None = None


class ReviewErrorResponse(BaseModel):
    """The body under a failure status: no choice, never a fallback order."""
    detail: str
    error: ReviewError
    provider: str | None
    model: str | None
    costUsd: float                       # settled cost of the failed call (a timeout settles its reservation)
    latencyMs: int
