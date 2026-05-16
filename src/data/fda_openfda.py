"""openFDA fetcher (Wave 2, Phase D — FDA Catalysts card).

Free API: https://api.fda.gov/drug/drugsfda.json  (no key required)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from src.utils.db import log_api_call


_OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"


def fetch_fda_applications_for_sponsor(
    sponsor_name: str,
    *,
    limit: int = 100,
) -> list[dict]:
    """Query openFDA Drugs@FDA for applications by `sponsor_name`.

    Returns a list of normalized application dicts (one per submission row):
        {application_number, sponsor_name, submission_type,
         submission_status, action_date}

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    # openFDA's search syntax requires the value to be URL-encoded and wrapped
    # in double-quotes to match the full phrase (otherwise it tokenizes).
    search = f'sponsor_name:"{sponsor_name}"'
    url = f"{_OPENFDA_URL}?search={quote(search)}&limit={int(limit)}"

    try:
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("openfda", url, "error", error=str(exc))
        return []

    results = data.get("results", []) or []
    out: list[dict] = []
    for r in results:
        app_no = r.get("application_number", "")
        sponsor = r.get("sponsor_name", "")
        submissions = r.get("submissions", []) or []
        if not submissions:
            # Application with no submissions — still surface a row with blanks
            out.append({
                "application_number": app_no,
                "sponsor_name": sponsor,
                "submission_type": "",
                "submission_status": "",
                "action_date": "",
            })
            continue
        for s in submissions:
            out.append({
                "application_number": app_no,
                "sponsor_name": sponsor,
                "submission_type": s.get("submission_type", "") or "",
                "submission_status": s.get("submission_status", "") or "",
                "action_date": s.get("submission_status_date", "") or "",
            })
    log_api_call("openfda", url, "ok")
    return out
