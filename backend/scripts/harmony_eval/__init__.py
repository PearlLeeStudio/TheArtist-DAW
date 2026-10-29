"""Harmony evaluation: does Meta reasoning over read notes beat the local analyzer?

chords   symbol normalization and the editor's two-slot alignment
dataset  deterministic synthetic scores from the product's own progressions and voicings,
         and excerpts realized the same way from the owner's private real songs
engines  the local, meta, auto and openweight adapters over the same ScoreMeasure objects
metrics  slot scoring and aggregation
run      the runner (results-<engine>.json, results-real-songs-<engine>.json), report (summary.md)

Results live in experiments/harmony_eval; paths are kept repo-relative in every
committed file. Anything derived from the private real songs except the aggregate
results goes to PRIVATE_DIR, outside the repository.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS_DIR = REPO_ROOT / "experiments" / "harmony_eval"
DATASET_PATH = EXPERIMENTS_DIR / "dataset.jsonl"
# The author's git-ignored tooling folder beside the repository, never inside it
PRIVATE_DIR = REPO_ROOT.parent / ".tooling" / "score-inspection" / "harmony-eval"
REAL_SONGS_DATASET_NAME = "real-songs-dataset.jsonl"


class PrivateDataError(Exception):
    """A write would put data derived from the private real songs where it does not belong."""


def repo_relative(path: Path) -> str:
    """The path as written into committed files: relative to the repo; a path outside it keeps only its name."""
    resolved = path.resolve()
    if resolved.is_relative_to(REPO_ROOT):
        return resolved.relative_to(REPO_ROOT).as_posix()
    return resolved.name


def outside_repo(path: Path) -> Path:
    """The resolved path of a private file or folder; PrivateDataError when it lies inside the repository."""
    resolved = path.resolve()
    if resolved.is_relative_to(REPO_ROOT):
        raise PrivateDataError(f"{repo_relative(resolved)} is inside the repository; the private real songs "
                               "and everything derived from them except the aggregate results stay outside it")
    return resolved
