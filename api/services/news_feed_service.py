"""News feed for a stock — headlines with rule-based sentiment tags.

Uses Tavily/Exa via NewsProvider. Sentiment is scored locally to avoid
per-headline Claude calls. Returns last N headlines + aggregate net sentiment.
"""
from __future__ import annotations

from datetime import datetime

from src.data.news import NewsProvider
from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 30  # news moves fast; refresh sub-hourly
_MAX_ITEMS = 10

_BULL_WORDS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "upgrade", "upgraded",
    "outperform", "buy", "raises", "boost", "boosts", "record", "all-time", "high",
    "expansion", "growth", "growing", "rising", "jumps", "jumped", "soars", "soared",
    "breakout", "breaks out", "bullish", "strong", "stronger", "exceeded", "exceed",
    "guidance raised", "raised guidance", "tops", "topped", "blowout", "stellar",
    "approval", "approved", "wins", "won", "deal", "acquisition", "expansion",
    "milestone", "launches", "launched", "demand", "tailwind",
}
_BEAR_WORDS = {
    "miss", "misses", "drop", "drops", "fall", "falls", "fell", "downgrade", "downgraded",
    "underperform", "sell", "cuts", "cut", "lawsuit", "fraud", "investigation", "probe",
    "decline", "declines", "warning", "warned", "weak", "weaker", "shortfall",
    "guidance cut", "cut guidance", "guides lower", "tumbles", "tumbled",
    "plunges", "plunged", "loss", "losses", "fired", "ousted", "scandal",
    "recall", "delisted", "bankruptcy", "default", "headwind",
    "below estimates", "missed estimates", "disappointed", "disappointing",
}


def _score_sentiment(text: str) -> dict:
    """Rule-based: count bullish vs bearish keyword hits.

    Returns {label: bullish/bearish/neutral, score: -1..+1}.
    """
    if not text:
        return {"label": "neutral", "score": 0.0}
    t = text.lower()
    bull = sum(1 for w in _BULL_WORDS if w in t)
    bear = sum(1 for w in _BEAR_WORDS if w in t)
    total = bull + bear
    if total == 0:
        return {"label": "neutral", "score": 0.0}
    score = (bull - bear) / max(total, 1)
    if score >= 0.3:
        label = "bullish"
    elif score <= -0.3:
        label = "bearish"
    else:
        label = "neutral"
    return {"label": label, "score": round(score, 2)}


def get_news_feed(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"news_feed:v1:{symbol}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    items: list[dict] = []
    try:
        raw = NewsProvider().search_stock_news(symbol, days=14) or []
    except Exception:
        raw = []

    for r in raw[:_MAX_ITEMS]:
        title = (r.get("title") or "").strip()
        snippet = (r.get("content_snippet") or "").strip()
        url = r.get("url") or ""
        source = r.get("source") or ""
        sent = _score_sentiment(f"{title}. {snippet}")
        items.append({
            "title": title,
            "snippet": snippet[:240],
            "url": url,
            "source": source,
            "sentiment": sent["label"],
            "sentiment_score": sent["score"],
            "published": r.get("published") or r.get("published_date") or None,
        })

    # Aggregate
    bull_count = sum(1 for i in items if i["sentiment"] == "bullish")
    bear_count = sum(1 for i in items if i["sentiment"] == "bearish")
    neutral_count = len(items) - bull_count - bear_count
    if items:
        net_score = sum(i["sentiment_score"] for i in items) / len(items)
        if net_score >= 0.2:
            net_label = "bullish"
        elif net_score <= -0.2:
            net_label = "bearish"
        else:
            net_label = "mixed"
    else:
        net_score = 0.0
        net_label = "no coverage"

    payload = {
        "symbol": symbol,
        "items": items,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "neutral_count": neutral_count,
        "net_sentiment": net_label,
        "net_score": round(net_score, 2),
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
