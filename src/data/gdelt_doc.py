"""GDELT DOC 2.0 article search (no key, no quota).

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
Params: query=<str>&mode=ArtList&format=json&maxrecords=N&sort=DateDesc

Returns {"articles": [{url, title, seendate, domain, language, sourcecountry}, ...]}.
seendate format is GDELT's compact form: 'YYYYMMDDTHHMMSSZ'.
"""
from __future__ import annotations

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_CACHE_TTL_MINUTES = 30


def get_gdelt_articles(query: str, *, limit: int = 50) -> list[dict] | None:
    """Fetch GDELT DOC articles for `query`. Returns raw rows or None on failure.

    Returns [] if the query has no hits (distinguishable from None / error).
    """
    key = f"gdelt_doc:{query}:{limit}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(limit),
        "sort": "DateDesc",
    }
    try:
        resp = httpx.get(_BASE_URL, params=params, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "TradingApp/1.0"})
        resp.raise_for_status()
        data = resp.json()
        log_api_call("gdelt", f"doc/{query[:50]}", "success")
    except Exception as e:
        log_api_call("gdelt", f"doc/{query[:50]}", "error", str(e))
        return None

    if not isinstance(data, dict):
        return None
    rows = data.get("articles") or []
    if not isinstance(rows, list):
        return None
    cache_set(key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MINUTES)
    return rows
