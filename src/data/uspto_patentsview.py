"""USPTO patent fetcher (Wave 2).

Originally built against PatentsView (`search.patentsview.org`), which was
shut down in late 2024. Migrated to the USPTO Open Data Portal:

    https://api.uspto.gov/api/v1/patent/applications/search

This is the Patent File Wrapper Search endpoint. Among all `/api/v1/patent/*`
paths exposed on the API gateway, this and `trials/decisions/search` are the
only ones that authenticate a key (other paths return "Missing Authentication
Token", meaning the route is not registered on the gateway).

A free API key is required — register at https://account.uspto.gov/ and set
the `USPTO_API_KEY` environment variable. Without a key the fetcher logs a
warning and returns []; the Innovation card hides silently in that case.

The exact request body schema is not publicly documented in a server-fetchable
form (the ODP docs page is a JavaScript SPA). The body below follows the
naming conventions USPTO uses elsewhere (`criteria`, `patentDateFrom`,
`limit`). If a future test against a real key reveals a different field
shape, only the `body` dict and the response-unpacking loop need adjustment;
the function signature and normalized return shape are preserved so the
mapper/service layer is unaffected.

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.
"""
from __future__ import annotations

import os

import httpx

from src.utils.db import log_api_call


# USPTO Open Data Portal — Patent File Wrapper Search
# Verified live (2026-05): returns 403 "Forbidden" with bogus key (auth gate),
# vs 403 "Missing Authentication Token" for unregistered routes.
_USPTO_URL = "https://api.uspto.gov/api/v1/patent/applications/search"


def fetch_patents_for_assignee(
    assignee_name: str,
    *,
    since_date: str,
    max_results: int = 100,
) -> list[dict]:
    """Query USPTO ODP for patents assigned to `assignee_name` since `since_date`.

    Returns a list of normalized patent dicts (shape preserved from the
    legacy PatentsView implementation so downstream mapper/service code does
    not change):

        {patent_id, title, date, cpc_class, assignee}

    Returns [] (and logs) on:
      - missing `USPTO_API_KEY` env var (warning, not an error)
      - HTTP/network failure
      - empty result set
    """
    api_key = os.environ.get("USPTO_API_KEY")
    if not api_key:
        log_api_call(
            "uspto",
            _USPTO_URL,
            "no_key",
            error="USPTO_API_KEY not set — register at account.uspto.gov",
        )
        return []

    body = {
        "criteria": {
            "assignee": assignee_name,
            "patentDateFrom": since_date,
        },
        "limit": max_results,
    }
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = httpx.post(_USPTO_URL, json=body, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("uspto", _USPTO_URL, "error", error=str(exc))
        return []

    # USPTO ODP response field names are not fully documented; accept the
    # legacy `patents` key (matches existing tests) and the likely ODP keys
    # (`patentBag`, `results`) so we degrade gracefully.
    patents = (
        data.get("patents")
        or data.get("patentBag")
        or data.get("results")
        or []
    )
    out: list[dict] = []
    for p in patents:
        # CPC class: legacy PatentsView shape uses `cpc_at_issue`; ODP likely
        # uses `cpcClassifications` or similar. Try both, fall back to "".
        cpc_class = ""
        cpc_list = p.get("cpc_at_issue") or p.get("cpcClassifications") or []
        if cpc_list and isinstance(cpc_list, list):
            first = cpc_list[0] or {}
            cpc_class = (
                first.get("cpc_subclass_id")
                or first.get("subclass")
                or first.get("symbol")
                or ""
            )

        # Assignee
        assignee = ""
        assignees = p.get("assignees") or p.get("assigneeBag") or []
        if assignees and isinstance(assignees, list):
            first = assignees[0] or {}
            assignee = (
                first.get("assignee_organization")
                or first.get("organizationName")
                or first.get("name")
                or ""
            )

        out.append({
            "patent_id": (
                p.get("patent_id")
                or p.get("patentNumber")
                or p.get("applicationNumber")
                or ""
            ),
            "title": (
                p.get("patent_title")
                or p.get("inventionTitle")
                or p.get("title")
                or ""
            ),
            "date": (
                p.get("patent_date")
                or p.get("patentDate")
                or p.get("grantDate")
                or ""
            ),
            "cpc_class": cpc_class,
            "assignee": assignee,
        })
    log_api_call("uspto", _USPTO_URL, "ok")
    return out
