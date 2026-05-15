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


from dataclasses import dataclass

from src.utils.db import get_connection, init_db


# Single source of truth — must match the CHECK constraint on
# entity_aliases.alias_type defined in src/utils/db.py::init_db().
VALID_ALIAS_TYPES: frozenset[str] = frozenset({
    "legal", "common", "subsidiary",
    "uspto_canonical", "sam_business_name",
    "brand", "override",
})


@dataclass(frozen=True)
class ResolvedEntity:
    ticker: str
    matched_alias: str
    confidence: float
    alias_type: str


def insert_alias(
    *,
    ticker: str,
    cik: str | None,
    uei: str | None,
    alias_type: str,
    alias_name: str,
    alias_source: str,
    confidence: float,
    created_at: str,
) -> None:
    """Insert (or replace) one alias row. Normalizes alias_name on insert.

    Raises ValueError if alias_type is not in VALID_ALIAS_TYPES.
    """
    if alias_type not in VALID_ALIAS_TYPES:
        raise ValueError(
            f"alias_type {alias_type!r} not in VALID_ALIAS_TYPES "
            f"(allowed: {sorted(VALID_ALIAS_TYPES)})"
        )
    init_db()
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO entity_aliases
          (ticker, cik, uei, alias_type, alias_name, alias_source, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker.upper(),
            cik,
            uei,
            alias_type,
            normalize_name(alias_name),
            alias_source,
            float(confidence),
            created_at,
        ),
    )
    conn.commit()
    conn.close()


def resolve_by_cik(cik: str) -> ResolvedEntity | None:
    """Authoritative ID lookup. confidence=1.0 always."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE cik = ? LIMIT 1",
        (cik,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return ResolvedEntity(
        ticker=row["ticker"],
        matched_alias=row["alias_name"],
        confidence=1.0,
        alias_type=row["alias_type"],
    )


def resolve_by_uei(uei: str) -> ResolvedEntity | None:
    """Authoritative ID lookup. confidence=1.0 always."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE uei = ? LIMIT 1",
        (uei,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return ResolvedEntity(
        ticker=row["ticker"],
        matched_alias=row["alias_name"],
        confidence=1.0,
        alias_type=row["alias_type"],
    )


def resolve_ticker(
    name: str,
    *,
    min_confidence: float = 0.9,
    use_fuzzy: bool = False,
) -> ResolvedEntity | None:
    """Resolve a free-text company name to a ticker.

    Lookup order:
      1. Exact match on normalized alias_name (confidence=1.0)
      2. Fuzzy match — but ONLY when use_fuzzy=True (see Task C3)

    Returns None when no match passes `min_confidence`.
    """
    if not name or not name.strip():
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None

    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE alias_name = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    conn.close()
    if row is not None:
        return ResolvedEntity(
            ticker=row["ticker"],
            matched_alias=row["alias_name"],
            confidence=1.0,
            alias_type=row["alias_type"],
        )

    # Fuzzy path is implemented in Task C3.
    return None
