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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.data.sec_edgar import SEC_USER_AGENT
from src.utils.db import get_connection, init_db, log_api_call

# NOTE: `yaml` (in seed_from_overrides) and `rapidfuzz` (in resolve_ticker)
# are intentionally lazy-imported at their call sites to avoid making them
# mandatory dependencies at module-load time.

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
      2. Fuzzy match via rapidfuzz.token_set_ratio when use_fuzzy=True

    Returns None when no match passes `min_confidence`.

    Threshold convention:
      - Scored signals: min_confidence=0.9 (default)
      - Information sources: min_confidence=0.8
    """
    if not name or not name.strip():
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None

    init_db()
    conn = get_connection()
    try:
        # 1. Exact match (confidence=1.0)
        row = conn.execute(
            "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE alias_name = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row is not None:
            return ResolvedEntity(
                ticker=row["ticker"],
                matched_alias=row["alias_name"],
                confidence=1.0,
                alias_type=row["alias_type"],
            )

        if not use_fuzzy:
            return None

        # 2. Fuzzy match: score the candidate against EVERY alias
        from rapidfuzz import fuzz

        candidates = conn.execute(
            "SELECT ticker, alias_name, alias_type FROM entity_aliases"
        ).fetchall()
        if not candidates:
            return None

        best: tuple[float, str, str, str] | None = None  # (score, ticker, alias, alias_type)
        for c in candidates:
            score = fuzz.token_set_ratio(normalized, c["alias_name"]) / 100.0
            if score < min_confidence:
                continue
            # Highest score wins; ties broken by alpha ticker order
            if best is None or score > best[0] or (score == best[0] and c["ticker"] < best[1]):
                best = (score, c["ticker"], c["alias_name"], c["alias_type"])

        if best is None:
            return None
        return ResolvedEntity(
            ticker=best[1],
            matched_alias=best[2],
            confidence=best[0],
            alias_type=best[3],
        )
    finally:
        conn.close()


# ── Seeders ──────────────────────────────────────────────────────────

_DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent / "entity_overrides.yaml"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def seed_from_overrides(yaml_path: Path | None = None) -> int:
    """Load manual overrides from YAML and insert into entity_aliases.

    Returns the count of inserted alias rows. Missing file → 0 (silent).
    """
    # Lazy import: yaml is not a mandatory module-load-time dep (see top of file).
    import yaml

    path = yaml_path if yaml_path is not None else _DEFAULT_OVERRIDES_PATH
    if not path.exists():
        return 0

    with path.open("r") as f:
        data = yaml.safe_load(f) or {}

    overrides = data.get("overrides", []) or []
    now = _now_iso()
    inserted = 0

    for entry in overrides:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        cik = entry.get("cik")
        uei = entry.get("uei")

        for alias in entry.get("aliases", []) or []:
            insert_alias(
                ticker=ticker, cik=cik, uei=uei,
                alias_type="override", alias_name=alias,
                alias_source="override", confidence=1.0, created_at=now,
            )
            inserted += 1
        for sub in entry.get("subsidiaries", []) or []:
            insert_alias(
                ticker=ticker, cik=None, uei=None,
                alias_type="subsidiary", alias_name=sub,
                alias_source="override", confidence=1.0, created_at=now,
            )
            inserted += 1
        for brand in entry.get("brands", []) or []:
            insert_alias(
                ticker=ticker, cik=None, uei=None,
                alias_type="brand", alias_name=brand,
                alias_source="override", confidence=1.0, created_at=now,
            )
            inserted += 1

    return inserted


def seed_from_sec_mapping(
    mapping: dict[str, tuple[str, str]],
    *,
    alias_source: str = "sec",
) -> int:
    """Seed entity_aliases from a {ticker: (cik, legal_name)} mapping.

    Caller is responsible for producing the mapping — typically from
    SECEdgarProvider's existing CIK lookup (a one-time fetch of the
    SEC company_tickers.json file).

    Returns count of inserted rows. CIK is stored as the authoritative
    ID (confidence=1.0). Skips entries with blank ticker or blank CIK.
    """
    now = _now_iso()
    inserted = 0
    for ticker, (cik, legal_name) in mapping.items():
        if not ticker or not cik or not legal_name:
            continue
        insert_alias(
            ticker=ticker, cik=cik, uei=None,
            alias_type="legal", alias_name=legal_name,
            alias_source=alias_source, confidence=1.0, created_at=now,
        )
        inserted += 1
    return inserted


def load_sec_mapping_from_provider() -> dict[str, tuple[str, str]]:
    """Convenience: build the {ticker: (cik, name)} mapping from the
    existing SECEdgarProvider. Network call.

    Returns {} on failure (so seeders don't crash mid-pipeline).
    """
    try:
        # SEC publishes the full ticker→CIK list as a single JSON file.
        # This is the standard source SECEdgarProvider uses for CIK lookup.
        resp = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call(
            source="sec_edgar",
            endpoint="company_tickers.json",
            status="error",
            error=str(exc),
        )
        return {}

    mapping: dict[str, tuple[str, str]] = {}
    # company_tickers.json shape: {"0": {"cik_str": int, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    for entry in data.values():
        ticker = entry.get("ticker", "")
        cik_int = entry.get("cik_str")
        title = entry.get("title", "")
        if not ticker or cik_int is None or not title:
            continue
        cik_padded = str(cik_int).zfill(10)
        mapping[ticker.upper()] = (cik_padded, title)
    return mapping
