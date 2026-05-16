"""Executive Changes service — orchestrates SEC 8-K fetch + analysis mapper.

Returns a dict consumable directly by the /stocks/{t}/exec-changes route.

Lookup pattern: read the CIK column from the seeded `legal` aliases for
the ticker in `entity_aliases`, fetch recent 8-K filings via
`fetch_recent_8ks`, and map the result via `exec_changes_to_information`.

If no CIK is on file we return an empty StockInformation payload so the
card can still render a low-signal state.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.analysis.sector_signals.exec_turnover import (
    exec_changes_to_information,
)
from src.data.sec_edgar import fetch_recent_8ks
from src.utils.db import get_connection, init_db


def _get_cik_for_ticker(ticker: str) -> str | None:
    """Pull the CIK from the seeded `legal` alias rows for `ticker`."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT cik FROM entity_aliases "
        "WHERE ticker = ? AND alias_type = 'legal' AND cik IS NOT NULL",
        (ticker,),
    ).fetchall()
    conn.close()
    for r in rows:
        cik = r["cik"]
        if cik:
            return cik
    return None


def get_exec_changes_for_ticker(ticker: str) -> dict:
    """Build Executive Changes card payload for `ticker`.

    Strategy:
      1. Look up CIK via `legal` alias for the ticker
      2. If no CIK, return an empty info payload (low severity)
      3. Otherwise fetch_recent_8ks(cik, days=180) and map
    """
    from src.data.entity_aliases import ensure_alias_for_ticker
    ensure_alias_for_ticker(ticker)
    as_of = datetime.now(tz=timezone.utc).isoformat()
    cik = _get_cik_for_ticker(ticker)
    if not cik:
        info = exec_changes_to_information(
            ticker=ticker, filings_8k=[], as_of=as_of
        )
        return asdict(info)

    filings = fetch_recent_8ks(cik, days=180)
    info = exec_changes_to_information(
        ticker=ticker, filings_8k=filings, as_of=as_of
    )
    return asdict(info)
