"""Top market-level news headlines with sentiment tags.

Same rule-based sentiment scoring as news_feed_service but for broad market
queries (Fed, inflation, jobs, geopolitical, tech sector).

Fallback chain per query: Tavily → Exa → GDELT → Google News RSS.
Tavily/Exa are quota-bound (cooldown-tracked by quota_tracker); GDELT and
Google News are no-key / no-quota so the card never goes dark when paid
APIs are exhausted.

Cached 30 min on success / 5 min when all providers fail so we retry
sooner once cooldowns expire.
"""
from __future__ import annotations

from datetime import datetime

from src.data.gdelt_doc import get_gdelt_articles
from src.data.google_news_rss import get_google_news
from src.data.news import NewsProvider
from src.data.quota_tracker import is_exhausted
from src.utils.db import cache_get, cache_set
from api.services.news_feed_service import _score_sentiment

_CACHE_TTL_OK = 30
_CACHE_TTL_FAIL = 5
_MAX_ITEMS = 8

_MARKET_QUERIES = [
    "stock market today Fed Reserve interest rates",
    "S&P 500 Nasdaq market outlook",
    "inflation jobs report economic data",
]


# ── Normalizers (free-source rows → service's {title, url, content_snippet, source, published} shape) ──

def _normalize_gdelt(rows: list[dict]) -> list[dict]:
    """GDELT rows: {title, url, seendate, domain, ...}. No body, so reuse title."""
    out: list[dict] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "url": (r.get("url") or "").strip(),
            "content_snippet": title,
            "source": (r.get("domain") or "").strip(),
            "published": (r.get("seendate") or "").strip(),
        })
    return out


def _normalize_google(rows: list[dict]) -> list[dict]:
    """Google News rows: {title, url, pub_date, source, description}."""
    out: list[dict] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "url": (r.get("url") or "").strip(),
            "content_snippet": (r.get("description") or title).strip(),
            "source": (r.get("source") or "").strip(),
            "published": (r.get("pub_date") or "").strip(),
        })
    return out


# ── Per-query fallback chain ─────────────────────────────────────────

def _fetch_for_query(query: str, prov: NewsProvider | None) -> tuple[list[dict], str | None]:
    """Try Tavily → Exa → GDELT → Google News for ONE query.

    Returns (rows, provider_used_or_None). Stops at the first source that
    returns non-empty rows. Per-query so one bad query can't kill the rest.
    """
    if prov is not None and not is_exhausted("tavily"):
        try:
            rows = prov.search_news(query, max_results=4) or []
            if rows:
                return rows, "tavily"
        except Exception:
            pass

    if prov is not None and not is_exhausted("exa"):
        try:
            rows = prov.search_research(query) or []
            if rows:
                return rows[:4], "exa"
        except Exception:
            pass

    gdelt = get_gdelt_articles(query, limit=5)
    if gdelt:
        return _normalize_gdelt(gdelt[:3]), "gdelt"

    google = get_google_news(query, limit=5)
    if google:
        return _normalize_google(google[:3]), "google_news"

    return [], None


# ── Public entry point ──────────────────────────────────────────────

def get_market_news(force: bool = False) -> dict:
    cache_key = "market_news:v2"  # bumped after schema/provider chain change
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    raw: list[dict] = []
    seen_urls: set[str] = set()
    providers_used: set[str] = set()

    try:
        prov = NewsProvider()
    except Exception:
        prov = None

    for q in _MARKET_QUERIES:
        rows, provider = _fetch_for_query(q, prov)
        if provider:
            providers_used.add(provider)
        for r in rows:
            url = r.get("url") or ""
            if url and url in seen_urls:
                continue
            seen_urls.add(url)
            raw.append(r)

    # Pick representative provider + warning message based on what filled the list.
    if not providers_used:
        provider_used: str | None = None
        source_warning: str | None = "All news providers returned no results."
    elif "google_news" in providers_used and not (providers_used & {"tavily", "exa"}):
        provider_used = "google_news"
        source_warning = "Upstream news providers exhausted — using Google News RSS (free)."
    elif "gdelt" in providers_used and not (providers_used & {"tavily", "exa"}):
        provider_used = "gdelt"
        source_warning = "Tavily + Exa exhausted — using GDELT (free)."
    elif "exa" in providers_used and "tavily" not in providers_used:
        provider_used = "exa"
        source_warning = "Tavily exhausted — using Exa as fallback."
    elif "tavily" in providers_used:
        # Tavily covered (alone or with others); no warning needed.
        provider_used = "tavily"
        source_warning = None
    else:
        # Catch-all (mixed gdelt+exa, etc.)
        provider_used = next(iter(providers_used))
        source_warning = None

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

    ttl = _CACHE_TTL_OK if items else _CACHE_TTL_FAIL
    try:
        cache_set(cache_key, payload, ttl_minutes=ttl)
    except Exception:
        pass
    return payload
