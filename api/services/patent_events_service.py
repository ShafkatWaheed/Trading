"""Patent Events service — orchestrates Orange Book + ITC §337 + 8-K
Item 1.01 + Item 8.01 into a single StockInformation card payload.

Pattern mirrors api/services/litigation_service.py and fda_catalysts_service.py.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.analysis.sector_signals.patent_events import patent_events_to_information
from src.data.entity_aliases import (
    ensure_alias_for_ticker,
    get_sec_display_name,
    resolve_ticker_with_audit,
)
from src.data.fda_orange_book import fetch_patents_for_sponsor
from src.data.itc_edis import fetch_337_investigations_for_party
from src.data.sec_edgar import fetch_recent_8ks
from src.utils.db import get_connection, init_db
from src.utils.sec_8k_parser import (
    parse_8k_item_101_license_deals,
    parse_8k_item_801_litigation_events,
)


def _get_legal_name(ticker: str) -> str | None:
    """Look up the company's name for fetcher queries. Prefer the raw SEC
    display name (e.g. 'Apple Inc.') over the normalized alias."""
    raw = get_sec_display_name(ticker)
    if raw:
        return raw
    # Fall back to the normalized legal alias
    conn = get_connection()
    row = conn.execute(
        "SELECT alias_name FROM entity_aliases WHERE ticker = ? AND alias_type = 'legal' LIMIT 1",
        (ticker,),
    ).fetchone()
    conn.close()
    return row["alias_name"] if row else None


def _get_cik(ticker: str) -> str | None:
    """Look up CIK from entity_aliases."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT cik FROM entity_aliases WHERE ticker = ? AND cik IS NOT NULL LIMIT 1",
        (ticker,),
    ).fetchone()
    conn.close()
    return row["cik"] if row else None


def get_patent_events_for_ticker(ticker: str) -> dict:
    """Build Patent Events card payload for `ticker`.

    Pulls all 4 streams (Orange Book, ITC §337, 8-K Item 1.01, 8-K Item 8.01),
    merges via patent_events_to_information mapper, returns as dict.
    """
    ticker_up = ticker.upper()
    ensure_alias_for_ticker(ticker_up)
    name = _get_legal_name(ticker_up)
    cik = _get_cik(ticker_up)

    # 1. Orange Book — match by sponsor name (substring on FDA's uppercased applicant)
    orange_book: list[dict] = []
    if name:
        resolve_ticker_with_audit(name, source="patent_events:orange_book", use_fuzzy=False)
        orange_book = fetch_patents_for_sponsor(name)

    # 2. ITC §337 — match by party name in investigation titles
    itc: list[dict] = []
    if name:
        resolve_ticker_with_audit(name, source="patent_events:itc", use_fuzzy=False)
        itc = fetch_337_investigations_for_party(name)

    # 3. + 4. 8-K filings — require CIK
    license_deals: list = []
    litigation_events: list = []
    if cik:
        filings = fetch_recent_8ks(cik, days=180)
        for f in filings:
            raw = f.get("raw_text", "") or ""
            license_deals.extend(parse_8k_item_101_license_deals(raw))
            litigation_events.extend(parse_8k_item_801_litigation_events(raw))

    as_of = datetime.now(tz=timezone.utc).isoformat()
    info = patent_events_to_information(
        ticker=ticker_up,
        as_of=as_of,
        orange_book_patents=orange_book,
        itc_investigations=itc,
        license_deals=license_deals,
        litigation_events=litigation_events,
    )
    return asdict(info)
