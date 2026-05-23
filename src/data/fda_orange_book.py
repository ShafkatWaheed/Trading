"""FDA Orange Book patent fetcher (Patent Events card).

Free API: https://api.fda.gov/drug/orange.json  (no key required)

The Orange Book lists every approved drug + its patents + their expiration
dates. This is the canonical source for the "patent cliff" signal in
pharma/biotech.

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.

Implementation note (probed 2026-05-23):
    openFDA does not currently expose Orange Book patent data via JSON at
    `/drug/orange.json` (404). The `/drug/drugsfda.json` endpoint returns
    application/product metadata but no `patents` array. If/when openFDA
    publishes the Orange Book endpoint, this fetcher will work as-is given
    the expected shape below. Until then live calls return [] via the
    network-error path (logged), which is the contracted behavior.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from src.utils.db import log_api_call


_ORANGE_BOOK_URL = "https://api.fda.gov/drug/orange.json"


def _yn_to_bool(val) -> bool:
    """Orange Book flags are 'Y'/'N' strings; normalize to bool. None -> False."""
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().upper() == "Y"


def fetch_patents_for_sponsor(
    sponsor_name: str,
    *,
    limit: int = 100,
) -> list[dict]:
    """Query openFDA Orange Book for patents protecting drugs by `sponsor_name`.

    Returns a normalized list of dicts (one per product*patent row):
        {application_number, patent_number, patent_expire_date,
         drug_substance_flag, drug_product_flag, use_code,
         sponsor_name, trade_name}

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    # openFDA's search syntax requires the value to be URL-encoded and wrapped
    # in double-quotes to match the full phrase (otherwise it tokenizes).
    search = f'openfda.manufacturer_name:"{sponsor_name}"'
    url = f"{_ORANGE_BOOK_URL}?search={quote(search)}&limit={int(limit)}"

    try:
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("fda_orange_book", url, "error", error=str(exc))
        return []

    results = data.get("results", []) or []
    out: list[dict] = []
    for r in results:
        app_no = r.get("application_number", "") or ""
        sponsor = r.get("sponsor_name", "") or ""
        # Trade name: prefer openfda.brand_name list, fall back to products[].brand_name
        trade_name = ""
        openfda = r.get("openfda") or {}
        brand_names = openfda.get("brand_name") or []
        if brand_names:
            trade_name = brand_names[0] or ""
        if not trade_name:
            products = r.get("products") or []
            for p in products:
                bn = p.get("brand_name")
                if bn:
                    trade_name = bn
                    break

        patents = r.get("patents") or []
        for pat in patents:
            out.append({
                "application_number": app_no,
                "patent_number": pat.get("patent_number", "") or "",
                "patent_expire_date": pat.get("patent_expire_date", "") or "",
                "drug_substance_flag": _yn_to_bool(pat.get("drug_substance_flag")),
                "drug_product_flag": _yn_to_bool(pat.get("drug_product_flag")),
                "use_code": pat.get("patent_use_code", "") or "",
                "sponsor_name": sponsor,
                "trade_name": trade_name,
            })

    log_api_call("fda_orange_book", url, "ok")
    return out
