"""Geopolitical events: tariffs, war, natural disaster, supply chain."""
from __future__ import annotations

import os
from datetime import datetime
from src.utils.db import cache_get, cache_set


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


def _search_tavily(query: str) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []
    try:
        import httpx
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"query": query, "api_key": api_key, "max_results": 3, "search_depth": "basic"},
            timeout=12,
        )
        return r.json().get("results", []) or []
    except Exception:
        return []


def _search_exa(query: str) -> list[dict]:
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        return []
    try:
        import httpx
        r = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key},
            json={"query": query, "type": "auto", "num_results": 3,
                  "contents": {"highlights": {"max_characters": 200}}},
            timeout=12,
        )
        results = r.json().get("results", []) or []
        return [
            {
                "title": x.get("title", ""),
                "content": " ".join(x.get("highlights", []))[:200],
                "url": x.get("url", ""),
            }
            for x in results
        ]
    except Exception:
        return []


def get_geopolitical_events() -> dict:
    """Fetch + categorize geopolitical events. Cached 1 hour."""
    cached = cache_get("geo_events_v1")
    if cached:
        return cached

    events = []
    for cat in CATEGORIES:
        results = _search_tavily(cat["query"]) or _search_exa(cat["query"])
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
    }
    try:
        cache_set("geo_events_v1", payload, ttl_minutes=60)
    except Exception:
        pass
    return payload
