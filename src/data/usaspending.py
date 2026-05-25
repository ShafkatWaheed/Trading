"""USAspending fetcher (Wave 2, Phase E — Backlog card).

Free API: https://api.usaspending.gov/api/v2/search/spending_by_award/
(no key required; POST with JSON body)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from src.utils.db import log_api_call


_USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


def _search_awards(
    search_text: str,
    *,
    since_date: str,
    max_results: int,
) -> list[dict]:
    """Shared POST → normalized list helper.

    `search_text` is passed to USAspending's `recipient_search_text` filter,
    which accepts both UEIs and free-form recipient names (case-insensitive
    substring match). Returns the same normalized shape regardless of which.

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    end_date = datetime.now(tz=timezone.utc).date().isoformat()
    body = {
        "filters": {
            "recipient_search_text": [search_text],
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": since_date, "end_date": end_date}],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Award Type",
            "Action Date",
            "Awarding Agency",
        ],
        "limit": int(max_results),
        "page": 1,
    }
    try:
        resp = httpx.post(_USASPENDING_URL, json=body, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("usaspending", _USASPENDING_URL, "error", error=str(exc))
        return []

    results = data.get("results", []) or []
    out: list[dict] = []
    for r in results:
        out.append({
            "award_id": r.get("Award ID", "") or "",
            "recipient_name": r.get("Recipient Name", "") or "",
            "award_amount": r.get("Award Amount", 0) or 0,
            "award_type": r.get("Award Type", "") or "",
            "action_date": r.get("Action Date", "") or "",
            "awarding_agency": r.get("Awarding Agency", "") or "",
        })
    log_api_call("usaspending", _USASPENDING_URL, "ok")
    return out


def fetch_contracts_for_uei(
    uei: str,
    *,
    since_date: str,
    max_results: int = 100,
) -> list[dict]:
    """Query USAspending for awards to recipient `uei` since `since_date`.

    Returns a list of normalized award dicts:
        {award_id, recipient_name, award_amount, award_type,
         action_date, awarding_agency}

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    return _search_awards(uei, since_date=since_date, max_results=max_results)


def fetch_contracts_for_recipient(
    recipient_name: str,
    *,
    since_date: str,
    max_results: int = 100,
) -> list[dict]:
    """Query USAspending by recipient NAME (not UEI).

    USAspending's recipient_search_text accepts any name string and
    matches case-insensitively against recipient names. This is more
    robust than UEI matching when UEI data quality is uncertain.

    Returns the same normalized shape as fetch_contracts_for_uei:
      [{award_id, recipient_name, award_amount, award_type,
        action_date, awarding_agency}, ...]

    Empty list on error/no-results. Failures logged via log_api_call.
    """
    if not recipient_name or not recipient_name.strip():
        return []
    return _search_awards(
        recipient_name.strip(),
        since_date=since_date,
        max_results=max_results,
    )
