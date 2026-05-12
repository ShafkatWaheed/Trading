"""Claude-written upside narrative — parallel to risk_narrative_service.

Reads the stock's deep-dive payload and asks Claude for a structured bull case
with growth drivers, competitive moats, multiple-expansion path, catalysts,
and a realistic best-case scenario. Cached 24h.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

from src.utils.db import cache_get, cache_set
from api.services import deep_dive_service

_TIMEOUT_SECONDS = 60
_CACHE_TTL_MINUTES = 24 * 60


def _ask_claude(prompt: str) -> str | None:
    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
            capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, env=env,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def get_bull_narrative(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"bull_narrative:v1:{symbol}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    dd = deep_dive_service.get_deep_dive(symbol, period="3M")
    if not dd:
        return {"symbol": symbol, "error": "No deep-dive context available."}

    sector = dd.get("sector") or "Unknown"
    industry = dd.get("industry") or "Unknown"
    verdict = dd.get("verdict") or "Hold"
    price = dd.get("price")
    bullish_signals = [
        str(s.get("title") or s.get("name") or s.get("category") or "").strip()
        for s in (dd.get("signals") or [])
        if s.get("direction") == "bullish"
    ]
    bullish_signals = [b for b in bullish_signals if b][:8]
    summary = dd.get("summary") or ""
    bullish_count = (dd.get("signal_counts") or {}).get("bullish", 0)
    bearish_count = (dd.get("signal_counts") or {}).get("bearish", 0)

    bullish_block = "\n  - " + "\n  - ".join(bullish_signals) if bullish_signals else "  (none flagged)"

    prompt = (
        f"You are a growth-focused equity analyst writing the BULL CASE for {symbol}.\n"
        f"Stock context:\n"
        f"  Sector: {sector}\n"
        f"  Industry: {industry}\n"
        f"  Current verdict: {verdict}\n"
        f"  Price: {('$' + format(price, '.2f')) if price else 'n/a'}\n"
        f"  Signal tally: {bullish_count} bullish vs {bearish_count} bearish\n"
        f"  Bullish signals flagged:{bullish_block}\n"
        f"  Summary:\n  {summary[:600]}\n"
        f"\n"
        f"Write a JSON object with EXACTLY these keys (each value a single tight paragraph,\n"
        f"2-4 sentences, concrete and specific to this company — no generic boilerplate):\n"
        f"  growth_drivers     : top revenue/profit accelerants (named products, geographies, segments)\n"
        f"  competitive_moat   : specific durable advantages (network effects, switching costs, IP, scale)\n"
        f"  multiple_expansion : path to higher P/E or P/S (margin expansion, mix shift, narrative shift)\n"
        f"  catalysts          : near-term events that could re-rate (product launches, regulatory, capacity)\n"
        f"  best_case          : realistic best-case scenario over 6-12 months with rough upside %\n"
        f"  invalidates_if     : ONE concrete condition that would break this bull thesis\n"
        f"\n"
        f"Reply with JSON ONLY — no markdown fences, no commentary.\n"
    )

    raw = _ask_claude(prompt)
    parsed = _extract_json(raw) if raw else None
    if not parsed:
        return {
            "symbol": symbol,
            "error": "Could not parse Claude response.",
            "raw": (raw or "")[:500],
            "from_cache": False,
        }

    payload = {
        "symbol": symbol,
        "growth_drivers":     str(parsed.get("growth_drivers") or "").strip(),
        "competitive_moat":   str(parsed.get("competitive_moat") or "").strip(),
        "multiple_expansion": str(parsed.get("multiple_expansion") or "").strip(),
        "catalysts":          str(parsed.get("catalysts") or "").strip(),
        "best_case":          str(parsed.get("best_case") or "").strip(),
        "invalidates_if":     str(parsed.get("invalidates_if") or "").strip(),
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
