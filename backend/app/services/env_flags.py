"""Boolean environment flags, parsed the same way everywhere.

A flag is on for 1 / true / yes / on and off for 0 / false / no / off (case and
surrounding whitespace ignored). An unset or empty variable gives the default;
any other text raises, so a typo cannot silently flip a feature.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def env_bool(name: str, default: bool, env: Mapping[str, str] | None = None) -> bool:
    """The boolean value of the environment variable ``name``, or ``default`` when it is unset."""
    raw = (os.environ if env is None else env).get(name, "")
    text = raw.strip().lower()
    if not text:
        return default
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"{name} must be one of 1/true/yes/on or 0/false/no/off, got {raw!r}")


# The Meta Model API is a hackathon feature: off here means every Meta-backed path
# reports itself as disabled instead of calling the API or pretending to succeed.
META_ENABLED_VAR = "THEARTIST_META_ENABLED"


def meta_enabled(env: Mapping[str, str] | None = None) -> bool:
    return env_bool(META_ENABLED_VAR, True, env)
