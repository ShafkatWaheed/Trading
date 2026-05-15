"""Entity alias resolution: ticker ↔ company-name mapping.

Single source of truth for the `entity_aliases` table. Two thresholds:
  - Scored signals require ≥0.9 fuzzy confidence (or authoritative ID)
  - Information sources accept ≥0.8 fuzzy confidence

Authoritative ID matches (CIK, UEI) ALWAYS return confidence=1.0 and
bypass fuzzy matching.

Per CLAUDE.md: this module belongs to the `data/` layer. It may call
external APIs (during seeding) and read/write `trading.db`. It must
NOT import from `src/analysis/` or `src/reports/`.
"""
from __future__ import annotations

import re

# Words stripped during normalization (lowercased, after punctuation removal).
# Order matters: longer phrases first to avoid leaving "holdings" when
# we meant to strip "holdings inc".
_SUFFIX_WORDS = (
    "incorporated", "corporation", "company", "limited",
    "holdings", "group", "trust",
    "inc", "corp", "co", "ltd", "llc", "lp", "plc", "nv", "sa", "ag",
)
_SUFFIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _SUFFIX_WORDS) + r")\b",
    flags=re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[.,/]")
# Standalone "&" left dangling after a suffix word is stripped
# (e.g. "JPMorgan Chase & Co." → "jpmorgan chase &" before cleanup).
# Only matches when surrounded by whitespace, so embedded "&" in
# "at&t" is preserved.
_LONE_AMP_RE = re.compile(r"\s+&(?:\s+|$)")


def normalize_name(raw: str) -> str:
    """Normalize a company name for matching.

    Steps: lowercase → drop period/comma/slash → strip corporate
    suffixes (Inc, Corp, LLC, ...) → drop dangling standalone "&" →
    collapse whitespace.

    Idempotent. Returns "" for empty input.
    """
    if not raw:
        return ""
    s = raw.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _SUFFIX_RE.sub("", s)
    s = _LONE_AMP_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
