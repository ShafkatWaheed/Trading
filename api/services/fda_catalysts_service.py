"""FDA Catalysts service — orchestrates openFDA + analysis mapper.

Returns a dict consumable directly by the /stocks/{t}/fda-catalysts route.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.analysis.sector_signals.fda import fda_applications_to_information
from src.data.entity_aliases import get_sec_display_name, resolve_ticker_with_audit
from src.data.fda_openfda import fetch_fda_applications_for_sponsor
from src.utils.db import get_connection, init_db


def _get_legal_aliases(ticker: str) -> list[str]:
    """Look up the legal-name aliases for a ticker from entity_aliases.

    openFDA's sponsor_name field aligns with corporate legal names, so we
    use the `legal` alias_type as the candidate-sponsor pool.
    """
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT alias_name FROM entity_aliases "
        "WHERE ticker = ? AND alias_type = 'legal'",
        (ticker,),
    ).fetchall()
    conn.close()
    return [r["alias_name"] for r in rows]


def get_fda_catalysts_for_ticker(ticker: str) -> dict:
    """Build FDA Catalysts card payload for `ticker`.

    Strategy:
      1. Look up `legal` aliases for the ticker (these are openFDA sponsor candidates)
      2. Query openFDA for each candidate sponsor name, dedupe by application_number
      3. Map raw applications -> StockInformation
    """
    from src.data.entity_aliases import ensure_alias_for_ticker
    ensure_alias_for_ticker(ticker)
    sponsor_names = _get_legal_aliases(ticker)
    if not sponsor_names:
        # Prefer the raw SEC display name (unnormalized — what openFDA actually expects,
        # e.g. "Apple Inc." not "apple")
        display = get_sec_display_name(ticker)
        if display:
            sponsor_names = [display]
        else:
            # Last resort: normalized legal alias
            conn = get_connection()
            row = conn.execute(
                "SELECT alias_name FROM entity_aliases WHERE ticker = ? AND alias_type = 'legal' LIMIT 1",
                (ticker,),
            ).fetchone()
            conn.close()
            if row:
                sponsor_names = [row["alias_name"]]

    seen_ids: set[str] = set()
    merged: list[dict] = []
    for name in sponsor_names:
        # Log the resolution decision (input was the legal name we're querying)
        resolve_ticker_with_audit(name, source="fda", use_fuzzy=False)
        for app in fetch_fda_applications_for_sponsor(name):
            app_no = app.get("application_number", "")
            if not app_no or app_no in seen_ids:
                continue
            seen_ids.add(app_no)
            merged.append(app)

    as_of = datetime.now(tz=timezone.utc).isoformat()
    info = fda_applications_to_information(
        ticker=ticker, applications=merged, as_of=as_of
    )
    return asdict(info)
