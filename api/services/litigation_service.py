"""Litigation service — orchestrates ITC EDIS + analysis mapper.

Returns a dict consumable directly by the /stocks/{t}/litigation route.

Lookup pattern: pull legal/common/override aliases for the ticker from
`entity_aliases`, audit-log each resolution via `resolve_ticker_with_audit`
(use_fuzzy=False — we already have the canonical name), then query EDIS
per name and dedupe by investigation_number before mapping.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.analysis.sector_signals.itc import itc_investigations_to_information
from src.data.entity_aliases import get_sec_display_name, resolve_ticker_with_audit
from src.data.itc_edis import fetch_337_investigations_for_party
from src.utils.db import get_connection, init_db


def _get_party_names(ticker: str) -> list[str]:
    """Look up the legal/common/override name variations for a ticker.

    EDIS matches on free-text party names, so we query each known
    variation independently and dedupe results downstream by
    investigation_number.
    """
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT alias_name FROM entity_aliases "
        "WHERE ticker = ? AND alias_type IN ('legal', 'common', 'override')",
        (ticker,),
    ).fetchall()
    conn.close()
    return [r["alias_name"] for r in rows if r["alias_name"]]


def get_litigation_for_ticker(ticker: str) -> dict:
    """Build Litigation card payload for `ticker`.

    Strategy:
      1. Look up legal/common/override aliases for the ticker
      2. Audit-log the resolution decision per name (use_fuzzy=False)
      3. Query EDIS per name; dedupe rows by investigation_number
      4. Map raw rows → StockInformation
    """
    from src.data.entity_aliases import ensure_alias_for_ticker
    ensure_alias_for_ticker(ticker)
    party_names = _get_party_names(ticker)
    if not party_names:
        # Prefer the raw SEC display name (unnormalized — what ITC EDIS actually expects,
        # e.g. "Apple Inc." not "apple")
        display = get_sec_display_name(ticker)
        if display:
            party_names = [display]
        else:
            # Last resort: normalized legal alias
            conn = get_connection()
            row = conn.execute(
                "SELECT alias_name FROM entity_aliases WHERE ticker = ? AND alias_type = 'legal' LIMIT 1",
                (ticker,),
            ).fetchone()
            conn.close()
            if row:
                party_names = [row["alias_name"]]

    seen_ids: set[str] = set()
    merged: list[dict] = []
    for name in party_names:
        resolve_ticker_with_audit(name, source="itc", use_fuzzy=False)
        for row in fetch_337_investigations_for_party(name):
            inv_no = row.get("investigation_number", "")
            if not inv_no or inv_no in seen_ids:
                continue
            seen_ids.add(inv_no)
            merged.append(row)

    as_of = datetime.now(tz=timezone.utc).isoformat()
    info = itc_investigations_to_information(
        ticker=ticker, investigations=merged, as_of=as_of
    )
    return asdict(info)
