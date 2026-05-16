"""ITC EDIS fetcher (Wave 2, Phase F — Litigation card).

Free API: https://edis.usitc.gov/data/section337/investigation  (no key required)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.

EDIS is the U.S. International Trade Commission's Electronic Document
Information System. Section 337 investigations cover unfair-import
practices (most often patent infringement) and can result in exclusion
orders banning imports of the accused products — a material risk for a
respondent. Being a complainant is offensive/protective and typically
benign.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from src.utils.db import log_api_call


_EDIS_URL = "https://edis.usitc.gov/data/section337/investigation"


def _classify_role(party_role_raw: str) -> str:
    """Normalize a free-text party role to one of: complainant, respondent, unknown."""
    if not party_role_raw:
        return "unknown"
    lo = party_role_raw.strip().lower()
    if "complainant" in lo:
        return "complainant"
    if "respondent" in lo:
        return "respondent"
    return "unknown"


def fetch_337_investigations_for_party(party_name: str) -> list[dict]:
    """Query EDIS for §337 investigations involving `party_name`.

    Returns a list of normalized investigation dicts (one per party row):
        {investigation_number, title, party_name, party_role,
         status, filing_date}

    `party_role` is one of: 'complainant', 'respondent', or 'unknown'.

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    url = f"{_EDIS_URL}?party={quote(party_name)}"

    try:
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("itc_edis", url, "error", error=str(exc))
        return []

    investigations = data.get("investigations", []) or []
    out: list[dict] = []
    for inv in investigations:
        inv_number = inv.get("investigation_number", "") or ""
        title = inv.get("title", "") or ""
        status = inv.get("status", "") or ""
        filing_date = inv.get("filing_date", "") or ""
        parties = inv.get("parties", []) or []

        if not parties:
            # Investigation with no party rows — emit a single row with
            # the queried name and unknown role so the caller can still
            # surface it.
            out.append({
                "investigation_number": inv_number,
                "title": title,
                "party_name": party_name,
                "party_role": "unknown",
                "status": status,
                "filing_date": filing_date,
            })
            continue

        for p in parties:
            out.append({
                "investigation_number": inv_number,
                "title": title,
                "party_name": p.get("name", "") or party_name,
                "party_role": _classify_role(p.get("role", "") or ""),
                "status": status,
                "filing_date": filing_date,
            })

    log_api_call("itc_edis", url, "ok")
    return out
