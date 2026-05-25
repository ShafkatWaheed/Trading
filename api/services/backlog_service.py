"""Backlog service — orchestrates USAspending + analysis mapper.

Returns a dict consumable directly by the /stocks/{t}/backlog route.

Lookup is by UEI: we read the seeded `sam_business_name` aliases for the
ticker, pull their `uei`, and query USAspending per UEI. UEI lookups are
authoritative (no fuzzy resolver round-trip needed).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from src.analysis.sector_signals.govcon import contracts_to_information
from src.data.usaspending import fetch_contracts_for_uei
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


def get_backlog_for_ticker(ticker: str, *, lookback_days: int = 730) -> dict:
    """Build Backlog card payload for `ticker`.

    Strategy:
      1. Look up sam_business_name aliases → UEIs for the ticker
      2. Query USAspending for each UEI (authoritative ID, no fuzzy)
      3. Dedupe awards by award_id
      4. Map raw awards → StockInformation

    Lazy bootstrap order:
      - `ensure_alias_for_ticker` seeds `legal` aliases (CIK + name from
        SEC) so the ticker is at least known.
      - `ensure_uei_for_ticker` seeds the curated SAM.gov UEI for the
        ~30 major federal contractors we hand-mapped. After this, the
        UEI lookup below picks the row up automatically on first call.
    """
    from src.data.entity_aliases import ensure_alias_for_ticker
    from src.data.sam_contractor_seed import ensure_uei_for_ticker
    ensure_alias_for_ticker(ticker)
    ensure_uei_for_ticker(ticker)
    ueis = _get_ueis_for_ticker(ticker)
    since = (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).date().isoformat()

    seen_ids: set[str] = set()
    merged: list[dict] = []
    for uei in ueis:
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
