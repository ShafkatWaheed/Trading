"""openFDA fetcher (Wave 2, Phase D — FDA Catalysts card).

Free API: https://api.fda.gov/drug/drugsfda.json  (no key required)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from src.utils.db import log_api_call


_OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"

# Corporate suffixes / fillers that break openFDA's exact-phrase index.
# openFDA stores sponsors like "PFIZER" / "ELI LILLY AND COMPANY" — punctuation
# and (often) "Inc."/"Corp." trailers are absent or inconsistent, so the literal
# user-supplied "Pfizer Inc." 404s. We normalize before querying.
_SUFFIX_RE = re.compile(
    r"\b("
    r"INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|"
    r"LTD|LIMITED|LLC|PLC|HOLDINGS|HOLDING|GROUP|"
    r"SA|AG|NV|"
    r"PHARMACEUTICALS|PHARMACEUTICAL|PHARMA|"
    r"THERAPEUTICS|BIOSCIENCES|LABS|LABORATORIES"
    r")\b",
    re.IGNORECASE,
)


def _normalize_sponsor(name: str) -> str:
    """Uppercase, strip punctuation, and drop common corporate suffixes."""
    s = (name or "").upper()
    # openFDA's Lucene parser treats these as syntax — strip them.
    s = re.sub(r"[.,&]", " ", s)
    s = _SUFFIX_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_application(r: dict) -> list[dict]:
    """Flatten one openFDA application into one dict per submission."""
    app_no = r.get("application_number", "")
    sponsor = r.get("sponsor_name", "")
    submissions = r.get("submissions", []) or []
    if not submissions:
        return [{
            "application_number": app_no,
            "sponsor_name": sponsor,
            "submission_type": "",
            "submission_status": "",
            "action_date": "",
        }]
    rows = []
    for s in submissions:
        rows.append({
            "application_number": app_no,
            "sponsor_name": sponsor,
            "submission_type": s.get("submission_type", "") or "",
            "submission_status": s.get("submission_status", "") or "",
            "action_date": s.get("submission_status_date", "") or "",
        })
    return rows


def _fetch(url: str) -> list[dict] | None:
    """Run one openFDA GET. Returns results list on success, None on error."""
    try:
        resp = httpx.get(url, timeout=30.0)
    except Exception as exc:
        log_api_call("openfda", url, "error", error=str(exc))
        return None
    # openFDA returns 404 for "no results found" (not a transport error) — that
    # is a legitimate empty result, not a failure.
    if resp.status_code == 404:
        log_api_call("openfda", url, "ok")
        return []
    if resp.status_code >= 400:
        log_api_call("openfda", url, "error", error=f"HTTP {resp.status_code}")
        return None
    try:
        data = resp.json()
    except Exception as exc:
        log_api_call("openfda", url, "error", error=f"json: {exc}")
        return None
    log_api_call("openfda", url, "ok")
    return data.get("results", []) or []


def fetch_fda_applications_for_sponsor(
    sponsor_name: str,
    *,
    limit: int = 100,
) -> list[dict]:
    """Query openFDA Drugs@FDA for applications by `sponsor_name`.

    Returns a list of normalized application dicts (one per submission row):
        {application_number, sponsor_name, submission_type,
         submission_status, action_date}

    Strategy: openFDA exposes two relevant indices with different tokenization:
      * `openfda.manufacturer_name` — phrase-indexed, accepts multi-word
        quoted phrases (e.g. `"ELI LILLY AND COMPANY"`).
      * `sponsor_name` — single-token index; only the first token of the
        legal name matches (e.g. `PFIZER`, `LILLY`, `BRISTOL`).
    We query both and merge by application_number for maximum coverage,
    since each index catches a different subset of filings.

    Empty list on no-results or network error (failures logged via
    log_api_call, never silently swallowed).
    """
    normalized = _normalize_sponsor(sponsor_name)
    if not normalized:
        return []

    merged: dict[str, dict] = {}  # app_no -> raw application dict

    # Attempt 1: phrase match against openfda.manufacturer_name
    phrase = f'"{normalized}"'
    url1 = (
        f"{_OPENFDA_URL}?search=openfda.manufacturer_name:{quote(phrase)}"
        f"&limit={int(limit)}"
    )
    r1 = _fetch(url1)
    if r1:
        for r in r1:
            ano = r.get("application_number", "")
            if ano and ano not in merged:
                merged[ano] = r

    # Attempt 2: single-token match against sponsor_name (catches different rows)
    token = normalized.split()[0] if normalized else ""
    # Skip reserved Lucene-like keywords and pathologically short tokens that
    # would match too broadly.
    if token and token not in {"AND", "OR", "NOT"} and len(token) >= 3:
        url2 = (
            f"{_OPENFDA_URL}?search=sponsor_name:{quote(token)}"
            f"&limit={int(limit)}"
        )
        r2 = _fetch(url2)
        if r2:
            for r in r2:
                ano = r.get("application_number", "")
                if ano and ano not in merged:
                    merged[ano] = r

    out: list[dict] = []
    for raw in merged.values():
        out.extend(_normalize_application(raw))
    return out
