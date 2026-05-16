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
    end_date = datetime.now(tz=timezone.utc).date().isoformat()
    body = {
        "filters": {
            "recipient_search_text": [uei],
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
