"""USPTO PatentsView fetcher (Wave 2).

Free API: https://search.patentsview.org/api/v1/patent/  (no key required)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.
"""
from __future__ import annotations

import httpx

from src.utils.db import log_api_call


_PATENTSVIEW_URL = "https://search.patentsview.org/api/v1/patent/"


def fetch_patents_for_assignee(
    assignee_name: str,
    *,
    since_date: str,
    max_results: int = 100,
) -> list[dict]:
    """Query PatentsView for patents granted to `assignee_name` since `since_date`.

    Returns a list of normalized patent dicts:
        {patent_id, title, date, cpc_class, assignee}

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    body = {
        "q": {
            "_and": [
                {"assignees.assignee_organization": assignee_name},
                {"_gte": {"patent_date": since_date}},
            ]
        },
        "f": ["patent_id", "patent_title", "patent_date",
              "assignees.assignee_organization", "cpc_at_issue.cpc_subclass_id"],
        "o": {"size": max_results},
    }
    try:
        resp = httpx.post(_PATENTSVIEW_URL, json=body, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("uspto_patentsview", _PATENTSVIEW_URL, "error", error=str(exc))
        return []

    patents = data.get("patents", []) or []
    out: list[dict] = []
    for p in patents:
        cpc_list = p.get("cpc_at_issue", []) or []
        cpc_class = cpc_list[0].get("cpc_subclass_id", "") if cpc_list else ""
        assignees = p.get("assignees", []) or []
        assignee = assignees[0].get("assignee_organization", "") if assignees else ""
        out.append({
            "patent_id": p.get("patent_id", ""),
            "title": p.get("patent_title", ""),
            "date": p.get("patent_date", ""),
            "cpc_class": cpc_class,
            "assignee": assignee,
        })
    log_api_call("uspto_patentsview", _PATENTSVIEW_URL, "ok")
    return out
