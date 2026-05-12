"""Claude-written downside narrative for a stock.

Reads the stock's deep-dive payload (verdict, sector, signals, trade plan,
existing risks) and asks Claude to write a structured worst-case write-up
with industry threats, competitive risks, balance-sheet vulnerabilities,
macro exposure, and a realistic worst-case scenario.

Cached for 24h alongside other deep-dive artifacts.
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


def get_risk_narrative(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"risk_narrative:v1:{symbol}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    # Reuse the deep-dive payload (cached) for context — sector, verdict, signals.
    dd = deep_dive_service.get_deep_dive(symbol, period="3M")
    if not dd:
        return {"symbol": symbol, "error": "No deep-dive context available."}

    sector = dd.get("sector") or "Unknown"
    industry = dd.get("industry") or "Unknown"
    verdict = dd.get("verdict") or "Hold"
    risk_label = dd.get("risk_label") or "Moderate"
    risk_rating = dd.get("risk_rating") or 3
    price = dd.get("price")
    bearish_count = (dd.get("signal_counts") or {}).get("bearish", 0)
    bullish_count = (dd.get("signal_counts") or {}).get("bullish", 0)
    bearish_signals = [
        str(s.get("title") or s.get("name") or s.get("category") or "").strip()
        for s in (dd.get("signals") or [])
        if s.get("direction") == "bearish"
    ]
    bearish_signals = [b for b in bearish_signals if b][:8]
    plan_risks = [
        str(r).strip()
        for r in ((dd.get("trade_plan") or {}).get("risks") or [])
        if r
    ]
    summary = dd.get("summary") or ""

    bearish_block = "\n  - " + "\n  - ".join(bearish_signals) if bearish_signals else "  (none flagged)"
    plan_risk_block = "\n  - " + "\n  - ".join(plan_risks) if plan_risks else "  (none in trade plan)"

    prompt = (
        f"You are a risk-focused equity analyst writing a downside brief on {symbol}.\n"
        f"Stock context:\n"
        f"  Sector: {sector}\n"
        f"  Industry: {industry}\n"
        f"  Current verdict: {verdict} (risk {risk_rating}/5 = {risk_label})\n"
        f"  Price: {('$' + format(price, '.2f')) if price else 'n/a'}\n"
        f"  Signal tally: {bullish_count} bullish vs {bearish_count} bearish\n"
        f"  Bearish signals flagged:{bearish_block}\n"
        f"  Existing trade-plan risks:{plan_risk_block}\n"
        f"  Summary:\n  {summary[:600]}\n"
        f"\n"
        f"Write a JSON object with EXACTLY these keys (each value a single tight paragraph,\n"
        f"2-4 sentences, concrete and specific to this company — no generic boilerplate):\n"
        f"  industry_threats     : structural headwinds facing this industry\n"
        f"  competitive_risks    : specific named competitors / market-share threats\n"
        f"  balance_sheet        : leverage, liquidity, dilution risk concerns (n/a if obviously not relevant)\n"
        f"  macro_exposure       : how rates / FX / commodities / cycle could hurt this name\n"
        f"  worst_case           : a realistic worst-case scenario over 6-12 months and rough downside %\n"
        f"  invalidates_if       : ONE concrete condition that would BREAK the bear thesis\n"
        f"                         (i.e. that would force a more constructive view — be specific)\n"
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
        "industry_threats": str(parsed.get("industry_threats") or "").strip(),
        "competitive_risks": str(parsed.get("competitive_risks") or "").strip(),
        "balance_sheet": str(parsed.get("balance_sheet") or "").strip(),
        "macro_exposure": str(parsed.get("macro_exposure") or "").strip(),
        "worst_case": str(parsed.get("worst_case") or "").strip(),
        "invalidates_if": str(parsed.get("invalidates_if") or "").strip(),
        "risk_rating": risk_rating,
        "risk_label": risk_label,
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass

    return payload
