"""Backlog service — orchestrates USAspending + analysis mapper.

Returns a dict consumable directly by the /stocks/{t}/backlog route.

Primary lookup is by recipient NAME (USAspending's `recipient_search_text`
accepts arbitrary name strings, not just UEIs — and UEIs in our seed are
unreliable). UEI lookup is kept as a SECONDARY merge so contracts that
only match by UEI still surface; results are deduped by `award_id`.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from src.analysis.sector_signals.govcon import contracts_to_information
from src.data.usaspending import (
    fetch_contracts_for_recipient,
    fetch_contracts_for_uei,
)
from src.utils.db import get_connection, init_db


def _get_ueis_for_ticker(ticker: str) -> list[str]:
    """Pull the UEIs associated with a ticker via `sam_business_name` aliases."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT uei FROM entity_aliases "
        "WHERE ticker = ? AND alias_type = 'sam_business_name' AND uei IS NOT NULL",
        (ticker,),
    ).fetchall()
    conn.close()
    return [r["uei"] for r in rows if r["uei"]]


def _get_legal_alias_name(ticker: str) -> str | None:
    """Fallback name lookup: the stored `legal` alias_name (normalized)."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT alias_name FROM entity_aliases "
        "WHERE ticker = ? AND alias_type = 'legal' LIMIT 1",
        (ticker,),
    ).fetchone()
    conn.close()
    return row["alias_name"] if row else None


def get_backlog_for_ticker(ticker: str, *, lookback_days: int = 730) -> dict:
    """Build Backlog card payload for `ticker`.

    Strategy:
      1. Lazily bootstrap the SEC alias for the ticker (so legal name
         is populated) and the curated UEI (for the ~30 hand-mapped primes).
      2. Resolve a recipient NAME — prefer the raw SEC display name
         (e.g. "Lockheed Martin Corporation"); fall back to the stored
         normalized `legal` alias.
      3. PRIMARY query: USAspending by recipient name. Name search works
         reliably even when our UEI data is wrong/missing.
      4. SECONDARY merge: query each known UEI and merge contracts not
         already returned by the name path. Dedupe by `award_id`.
      5. Map raw awards → StockInformation.
    """
    from src.data.entity_aliases import (
        ensure_alias_for_ticker,
        get_sec_display_name,
    )
    from src.data.sam_contractor_seed import ensure_uei_for_ticker

    ensure_alias_for_ticker(ticker)
    ensure_uei_for_ticker(ticker)

    # Resolve a recipient name (prefer raw SEC display name).
    recipient_name = get_sec_display_name(ticker)
    if not recipient_name:
        recipient_name = _get_legal_alias_name(ticker)

    since = (
        datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    ).date().isoformat()

    seen_ids: set[str] = set()
    merged: list[dict] = []

    # PRIMARY: name-based query (works without accurate UEI).
    if recipient_name:
        for c in fetch_contracts_for_recipient(recipient_name, since_date=since):
            award_id = c.get("award_id", "")
            if not award_id or award_id in seen_ids:
                continue
            seen_ids.add(award_id)
            merged.append(c)

    # SECONDARY: UEI-based merge (catches contracts only matchable by UEI).
    for uei in _get_ueis_for_ticker(ticker):
        for c in fetch_contracts_for_uei(uei, since_date=since):
            award_id = c.get("award_id", "")
            if not award_id or award_id in seen_ids:
                continue
            seen_ids.add(award_id)
            merged.append(c)

    as_of = datetime.now(tz=timezone.utc).isoformat()
    info = contracts_to_information(
        ticker=ticker, contracts=merged, as_of=as_of
    )
    return asdict(info)
