"""Disruption themes — AI, biotech, EV, quantum, etc.

Pulls news via Tavily/Exa, asks Claude to extract themes. Cached 1h.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from src.utils.db import cache_get, cache_set


# A small built-in fallback so the section is never empty even if all APIs fail.
FALLBACK_THEMES = [
    {
        "name": "AI Infrastructure",
        "icon": "🤖",
        "intensity": "HIGH",
        "tickers_benefit": ["NVDA", "AVGO", "ANET", "GLW", "VRT"],
        "sectors_benefit": ["Semiconductors", "Networking", "Data Center"],
        "tickers_risk": ["INTC", "ORCL"],
        "sectors_risk": ["Legacy Software"],
        "headline": "Hyperscalers pour record capex into GPU + cooling buildouts.",
    },
    {
        "name": "GLP-1 Obesity Drugs",
        "icon": "💊",
        "intensity": "HIGH",
        "tickers_benefit": ["LLY", "NVO"],
        "sectors_benefit": ["Pharma"],
        "tickers_risk": ["MDT"],
        "sectors_risk": ["Bariatric devices", "Snack food"],
        "headline": "Demand outpacing manufacturing capacity through 2027.",
    },
    {
        "name": "Electric Vehicles",
        "icon": "🔋",
        "intensity": "MEDIUM",
        "tickers_benefit": ["TSLA", "RIVN", "ENPH"],
        "sectors_benefit": ["EV", "Battery", "Solar"],
        "tickers_risk": ["XOM", "CVX"],
        "sectors_risk": ["Oil & Gas"],
        "headline": "China BEV competition pressuring legacy OEMs.",
    },
    {
        "name": "Quantum Computing",
        "icon": "⚛",
        "intensity": "EMERGING",
        "tickers_benefit": ["IONQ", "RGTI"],
        "sectors_benefit": ["Quantum hardware"],
        "tickers_risk": [],
        "sectors_risk": ["Cybersecurity (long-term encryption risk)"],
        "headline": "Government and enterprise pilot programs expanding.",
    },
]


def _search_tavily(query: str) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []
    try:
        import httpx
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"query": query, "api_key": api_key, "max_results": 5, "search_depth": "basic"},
            timeout=12,
        )
        results = r.json().get("results", []) or []
        return [
            {
                "title": (x.get("title") or "")[:120],
                "content": (x.get("content") or "")[:200],
                "url": x.get("url") or "",
            }
            for x in results
        ]
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
            json={"query": query, "type": "auto", "num_results": 5,
                  "contents": {"highlights": {"max_characters": 200}}},
            timeout=12,
        )
        results = r.json().get("results", []) or []
        return [
            {"title": (x.get("title") or "")[:120],
             "content": " ".join(x.get("highlights", []))[:200],
             "url": x.get("url") or ""}
            for x in results
        ]
    except Exception:
        return []


def _domain(url: str) -> str:
    """Extract a short domain label (e.g. 'reuters.com') from a URL for display."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _gather_articles() -> list[dict]:
    # Spread queries across intensity tiers so Claude doesn't see an all-AI diet.
    # Without these probes, trending coverage drowns out under-reported emerging
    # tech like quantum, fusion, robotics, and gene editing.
    queries = [
        # Mature / high-intensity (already dominating headlines)
        "AI infrastructure semiconductor stocks impact",
        "GLP-1 obesity drugs pharma disruption",
        # Medium-intensity
        "electric vehicle battery technology stocks competition",
        "cybersecurity zero trust enterprise stocks",
        # Emerging — explicit probes so search engines surface them
        "quantum computing stocks IONQ RGTI commercial milestones",
        "nuclear fusion energy startups stocks investment 2026",
        "humanoid robotics warehouse automation stocks Tesla Figure",
        "CRISPR gene editing therapy approval stocks",
        "autonomous vehicles robotaxi commercialization stocks Waymo Tesla",
        "space economy SpaceX satellite stocks investment",
    ]
    articles: list[dict] = []
    seen_titles: set[str] = set()
    for q in queries:
        # Per-query fallback: if Tavily returns nothing for THIS query (rate-limited
        # or no match), try Exa for the same query. Without this, one successful
        # Tavily call blocked Exa for every subsequent query.
        results = _search_tavily(q)
        if not results:
            results = _search_exa(q)
        for r in results[:3]:
            title = (r.get("title") or "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                articles.append(r)
        if len(articles) >= 24:
            break
    return [
        {
            "title": (a.get("title") or "")[:120],
            "content": (a.get("content") or "")[:200],
            "url": a.get("url") or "",
            "source": _domain(a.get("url") or ""),
        }
        for a in articles[:24]
    ]


def _ask_claude_for_themes(articles: list[dict]) -> list[dict] | None:
    if not articles:
        return None
    # Number articles 1..N so Claude can cite the supporting indices per theme.
    articles_text = "\n".join(
        f"[{i+1}] {a['title']}: {a['content'][:80]}"
        for i, a in enumerate(articles)
    )
    prompt = (
        "Identify the top 6 technology disruption themes impacting US stocks based on these articles.\n\n"
        f"{articles_text}\n\n"
        "REQUIRED MIX — your 6 themes MUST span maturity tiers:\n"
        "  - 2-3 HIGH intensity (already moving stocks now — e.g. AI infra, GLP-1)\n"
        "  - 1-2 MEDIUM intensity (mid-adoption — e.g. EVs, cybersecurity, cloud transitions)\n"
        "  - 2 EMERGING intensity (early-stage but accelerating — e.g. quantum computing, "
        "fusion energy, humanoid robotics, gene editing, autonomous vehicles, space economy)\n"
        "Do NOT return 6 AI variants. Spread across distinct technology domains.\n\n"
        "Respond with ONLY a JSON array of 6 items. Each item must have: "
        "name (string), icon (single emoji), intensity (HIGH/MEDIUM/EMERGING), "
        "tickers_benefit (array of 3-5 tickers), sectors_benefit (array of 1-3), "
        "tickers_risk (array of 0-3), sectors_risk (array of 0-3), "
        "headline (one short sentence), "
        "sources (array of 1-3 article indices from above that support this theme — "
        "use the numbers in brackets like [1], [4]; only cite articles that actually mention "
        "this theme)."
    )
    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
            capture_output=True, text=True, timeout=90, env=env,
        )
        if proc.returncode != 0:
            return None
        text = (proc.stdout or "").strip()
        # Find JSON array in the output
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end <= start:
            return None
        return json.loads(text[start:end])
    except Exception:
        return None


def get_disruption_themes() -> dict:
    """Return current disruption themes. Cached 1 hour."""
    cached = cache_get("disruption_themes_v1")
    if cached:
        return cached

    articles = _gather_articles()
    claude_themes = _ask_claude_for_themes(articles)
    themes = claude_themes or FALLBACK_THEMES
    source = "claude" if claude_themes else "fallback"

    # Sanity: enforce shape. Validate cited indices against actual articles list.
    n_articles = len(articles)
    cleaned = []
    for t in themes[:6]:
        if not isinstance(t, dict):
            continue
        # Normalize sources: keep only valid 1..N indices, max 3 per theme.
        raw_sources = t.get("sources") or []
        sources: list[int] = []
        for s in raw_sources:
            try:
                idx = int(s)
                if 1 <= idx <= n_articles and idx not in sources:
                    sources.append(idx)
            except (TypeError, ValueError):
                continue
            if len(sources) >= 3:
                break
        cleaned.append({
            "name": str(t.get("name", "Theme"))[:60],
            "icon": str(t.get("icon", "💡"))[:4],
            "intensity": str(t.get("intensity", "MEDIUM")).upper()[:10],
            "tickers_benefit": [str(x).upper()[:6] for x in (t.get("tickers_benefit") or [])][:6],
            "sectors_benefit": [str(x)[:30] for x in (t.get("sectors_benefit") or [])][:4],
            "tickers_risk": [str(x).upper()[:6] for x in (t.get("tickers_risk") or [])][:6],
            "sectors_risk": [str(x)[:30] for x in (t.get("sectors_risk") or [])][:4],
            "headline": str(t.get("headline", ""))[:200],
            "sources": sources,
        })

    # Build the top-level articles list (1-indexed for parity with citations).
    article_index = [
        {
            "idx": i + 1,
            "title": (a.get("title") or "")[:120],
            "url": a.get("url") or "",
            "source": a.get("source") or _domain(a.get("url") or ""),
        }
        for i, a in enumerate(articles)
    ]

    payload = {
        "themes": cleaned,
        "source": source,
        "articles_used": len(articles),
        "articles": article_index,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
    try:
        cache_set("disruption_themes_v1", payload, ttl_minutes=60)
    except Exception:
        pass
    return payload
