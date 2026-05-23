"""Geopolitical events: tariffs, war, natural disaster, supply chain.

Fallback chain per topical query:
    Tavily → Exa → GDELT DOC 2.0 → Google News RSS

Tavily/Exa are paid, quota-bound. Once a 402/403/429 is observed,
`quota_tracker` marks the source exhausted for 4 hours; subsequent calls
skip it. GDELT and Google News are no-key / no-quota and act as durable
fallbacks so the geopolitical view never goes dark just because the paid
APIs are out of credits.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from src.data.gdelt_doc import get_gdelt_articles
from src.data.google_news_rss import get_google_news
from src.data.quota_tracker import is_exhausted, mark_exhausted
from src.utils.db import cache_get, cache_set

logger = logging.getLogger(__name__)


# Sector impact mapping per event category.
IMPACT = {
    "tariff": {
        "icon": "🏷",
        "negative": ["Technology", "Consumer Discretionary", "Industrials", "Materials"],
        "positive": ["Domestic Manufacturing", "Utilities", "Healthcare (domestic)"],
        "explanation": "Tariffs raise input costs for importers and manufacturers. Tech and consumer goods face higher component costs. Domestic producers may benefit.",
    },
    "war": {
        "icon": "⚔",
        "negative": ["Airlines", "Tourism", "Consumer Discretionary", "Global Banks"],
        "positive": ["Defense & Aerospace", "Energy (oil/gas)", "Cybersecurity", "Gold miners"],
        "explanation": "Conflicts drive defense spending, spike oil prices, create risk-off sentiment. Defense surges while travel and consumer spending pull back.",
    },
    "natural_disaster": {
        "icon": "🌊",
        "negative": ["Insurance", "Real Estate", "Agriculture", "Regional banks"],
        "positive": ["Construction", "Home improvement", "Infrastructure", "Utilities rebuild"],
        "explanation": "Disasters destroy assets but create rebuilding demand. Insurance faces claims; construction and materials companies see revenue spikes.",
    },
    "supply_chain": {
        "icon": "🚢",
        "negative": ["Automotive", "Electronics", "Retail", "Restaurants"],
        "positive": ["Shipping & Logistics", "Warehousing", "Domestic alternatives"],
        "explanation": "Disruptions cause shortages and cost inflation. Companies with domestic supply chains or inventory buffers outperform.",
    },
}

CATEGORIES = [
    {"type": "tariff", "query": "US tariffs trade war impact industries sectors", "severity": ["200%", "new tariff", "trade war escalat", "retaliat"]},
    {"type": "war", "query": "war conflict military impact US stock market", "severity": ["escalat", "invasion", "missile", "nuclear", "sanction"]},
    {"type": "natural_disaster", "query": "flood hurricane earthquake wildfire disaster US economic impact", "severity": ["billion damage", "emergency", "catastroph", "devastat"]},
    {"type": "supply_chain", "query": "supply chain disruption shortage US industry impact", "severity": ["shortage", "disruption", "backlog", "shut down"]},
]


# ── Per-source fetchers ──────────────────────────────────────────────

def _search_tavily(query: str) -> tuple[list[dict], bool]:
    """Returns (results, upstream_ok). Marks Tavily exhausted on 402/403/429."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return [], False
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"query": query, "api_key": api_key, "max_results": 3, "search_depth": "basic"},
            timeout=12,
        )
        # 432 is Tavily's custom "plan usage exceeded" code (not a standard HTTP code).
        if r.status_code in (402, 403, 429, 432):
            mark_exhausted("tavily")
            logger.warning("Tavily quota exhausted (HTTP %s); cooldown applied", r.status_code)
            return [], False
        if r.status_code != 200:
            logger.warning("Tavily search failed: HTTP %s body=%s", r.status_code, r.text[:200])
            return [], False
        return r.json().get("results", []) or [], True
    except Exception as e:
        logger.warning("Tavily search exception: %r", e)
        return [], False


def _search_exa(query: str) -> tuple[list[dict], bool]:
    """Returns (results, upstream_ok). Marks Exa exhausted on 402/403/429."""
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        return [], False
    try:
        r = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key},
            json={"query": query, "type": "auto", "num_results": 3,
                  "contents": {"highlights": {"max_characters": 200}}},
            timeout=12,
        )
        if r.status_code in (402, 403, 429):
            mark_exhausted("exa")
            logger.warning("Exa quota exhausted (HTTP %s); cooldown applied", r.status_code)
            return [], False
        if r.status_code != 200:
            logger.warning("Exa search failed: HTTP %s body=%s", r.status_code, r.text[:200])
            return [], False
        results = r.json().get("results", []) or []
        return [
            {
                "title": x.get("title", ""),
                "content": " ".join(x.get("highlights", []))[:200],
                "url": x.get("url", ""),
            }
            for x in results
        ], True
    except Exception as e:
        logger.warning("Exa search exception: %r", e)
        return [], False


# ── Normalizers (GDELT / Google rows → {title, content, url}) ────────

def _normalize_gdelt(rows: list[dict]) -> list[dict]:
    """GDELT articles have no snippet; use the title as content."""
    out: list[dict] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "content": title,
            "url": (r.get("url") or "").strip(),
        })
    return out


def _normalize_google(rows: list[dict]) -> list[dict]:
    """Google News rows: use `description` as content, fall back to title."""
    out: list[dict] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "content": (r.get("description") or title).strip(),
            "url": (r.get("url") or "").strip(),
        })
    return out


# ── Fallback chain ───────────────────────────────────────────────────

def _fetch_category(query: str) -> tuple[list[dict], bool]:
    """Try sources in order until one succeeds. Returns (rows, upstream_ok).

    Order: Tavily (if not on cooldown) → Exa (if not on cooldown) → GDELT → Google News.
    upstream_ok=True if ANY source returned (even with zero rows).
    """
    if not is_exhausted("tavily"):
        rows, ok = _search_tavily(query)
        if ok:
            return rows, True

    if not is_exhausted("exa"):
        rows, ok = _search_exa(query)
        if ok:
            return rows, True

    # GDELT — no quota, no key. Returns None on transport failure, [] on no hits.
    gdelt_rows = get_gdelt_articles(query, limit=5)
    if gdelt_rows is not None:
        return _normalize_gdelt(gdelt_rows[:3]), True

    # Google News RSS — no quota, no key. Last resort.
    google_rows = get_google_news(query, limit=5)
    if google_rows is not None:
        return _normalize_google(google_rows[:3]), True

    return [], False


# ── Public entry point ──────────────────────────────────────────────

def get_geopolitical_events() -> dict:
    """Fetch + categorize geopolitical events. Cached 1 hour on success,
    5 min when every upstream failed so we retry as soon as cooldowns expire.
    """
    cached = cache_get("geo_events_v1")
    if cached:
        return cached

    events: list[dict] = []
    any_upstream_ok = False
    for cat in CATEGORIES:
        results, ok = _fetch_category(cat["query"])
        if ok:
            any_upstream_ok = True
        impact = IMPACT.get(cat["type"], {})
        for r in results[:2]:
            title = (r.get("title") or "")[:120]
            content = (r.get("content") or "")[:200]
            url = r.get("url") or ""
            combined = (title + " " + content).lower()
            severity = "high" if any(kw in combined for kw in cat["severity"]) else "moderate"
            events.append({
                "type": cat["type"],
                "icon": impact.get("icon", "⚠"),
                "title": title,
                "snippet": content,
                "url": url,
                "severity": severity,
                "negative_sectors": impact.get("negative", []),
                "positive_sectors": impact.get("positive", []),
                "explanation": impact.get("explanation", ""),
            })

    payload = {
        "events": events,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "data_available": any_upstream_ok,
    }
    try:
        ttl = 60 if any_upstream_ok else 5
        cache_set("geo_events_v1", payload, ttl_minutes=ttl)
    except Exception:
        pass
    return payload
