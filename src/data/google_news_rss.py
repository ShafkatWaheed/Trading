"""Google News RSS search (no key, no quota).

Endpoint: https://news.google.com/rss/search?q=<QUERY>&hl=en-US&gl=US&ceid=US:en
Returns RSS XML; each <item> has title, link, pubDate, source, description.

Used as a broad-aggregator primary source — closest free replacement for Tavily's
general-web search.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_BASE_URL = "https://news.google.com/rss/search"
_CACHE_TTL_MINUTES = 30


def get_google_news(query: str, *, limit: int = 25) -> list[dict] | None:
    """Fetch Google News RSS for `query`. Returns raw rows or None on failure.

    Each row: {title, url, pub_date, source, description}.
    """
    key = f"google_news_rss:{query}:{limit}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")

    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        resp = httpx.get(_BASE_URL, params=params, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "TradingApp/1.0"})
        resp.raise_for_status()
        log_api_call("google_news_rss", f"search/{query[:50]}", "success")
    except Exception as e:
        log_api_call("google_news_rss", f"search/{query[:50]}", "error", str(e))
        return None

    rows: list[dict] = []
    try:
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item")[:limit]:
            rows.append({
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
                "pub_date": (item.findtext("pubDate") or "").strip(),
                "source": (item.findtext("source") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
            })
    except ET.ParseError as e:
        log_api_call("google_news_rss", f"search/{query[:50]}", "parse_error", str(e))
        return None

    cache_set(key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MINUTES)
    return rows
