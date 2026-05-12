"""Top market-level news headlines with sentiment tags.

Same rule-based sentiment scoring as news_feed_service but for broad market
queries (Fed, inflation, jobs, geopolitical, tech sector). Cached 30 min.
"""
from __future__ import annotations

from datetime import datetime

from src.data.news import NewsProvider
from src.utils.db import cache_get, cache_set
from api.services.news_feed_service import _score_sentiment

_CACHE_TTL_MINUTES = 30
_MAX_ITEMS = 8

_MARKET_QUERIES = [
    "stock market today Fed Reserve interest rates",
    "S&P 500 Nasdaq market outlook",
    "inflation jobs report economic data",
]


def get_market_news(force: bool = False) -> dict:
    cache_key = "market_news:v1"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    raw: list[dict] = []
    seen_urls: set[str] = set()
    provider_used: str | None = None
    source_warning: str | None = None
    try:
        prov = NewsProvider()
        # 1) Tavily first
        for q in _MARKET_QUERIES:
            try:
                results = prov.search_news(q, max_results=4) or []
                for r in results:
                    url = r.get("url") or ""
                    if url and url in seen_urls:
                        continue
                    seen_urls.add(url)
                    raw.append(r)
            except Exception:
                continue
        if raw:
            provider_used = "tavily"
        else:
            # 2) Fall back to Exa when Tavily is rate-limited / empty
            for q in _MARKET_QUERIES:
                try:
                    results = prov.search_research(q) or []
                    for r in results[:4]:
                        url = r.get("url") or ""
                        if url and url in seen_urls:
                            continue
                        seen_urls.add(url)
                        raw.append(r)
                except Exception:
                    continue
            if raw:
                provider_used = "exa"
                source_warning = "Tavily rate-limit hit — using Exa as fallback."
            else:
                source_warning = "Both Tavily and Exa returned no results — check API quotas."
    except Exception:
        pass

    items: list[dict] = []
    for r in raw[:_MAX_ITEMS]:
        title = (r.get("title") or "").strip()
        snippet = (r.get("content_snippet") or "").strip()
        sent = _score_sentiment(f"{title}. {snippet}")
        items.append({
            "title":           title,
            "snippet":         snippet[:240],
            "url":             r.get("url") or "",
            "source":          r.get("source") or "",
            "sentiment":       sent["label"],
            "sentiment_score": sent["score"],
            "published":       r.get("published") or r.get("published_date"),
        })

    bull = sum(1 for i in items if i["sentiment"] == "bullish")
    bear = sum(1 for i in items if i["sentiment"] == "bearish")
    neut = len(items) - bull - bear
    if items:
        net_score = sum(i["sentiment_score"] for i in items) / len(items)
        if net_score >= 0.2:    net_label = "bullish"
        elif net_score <= -0.2: net_label = "bearish"
        else:                   net_label = "mixed"
    else:
        net_score = 0.0
        net_label = "no coverage"

    payload = {
        "items":          items,
        "bull_count":     bull,
        "bear_count":     bear,
        "neutral_count":  neut,
        "net_sentiment":  net_label,
        "net_score":      round(net_score, 2),
        "provider":       provider_used,
        "source_warning": source_warning,
        "last_updated":   datetime.utcnow().isoformat() + "Z",
        "from_cache":     False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
