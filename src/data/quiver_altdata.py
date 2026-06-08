"""Quiver Quantitative alternative-data signals for the deep dive.

Four per-ticker datasets, each scored into a {direction, strength, score, …}
dict that the report builder turns into a deep-dive signal card:

  * Dark pool / off-exchange short volume  (Tier 1 — daily, quantitative)
  * Government contracts                    (Tier 2 — sector-dependent catalyst)
  * Lobbying spend                          (Tier 3 — context, low signal/noise)
  * Corporate flights (private jets)        (Tier 3 — M&A novelty, low signal/noise)

Tier 3 signals are deliberately capped to a low `strength` so they read as
context rather than conviction.

Per CLAUDE.md: data layer. Calls the Quiver API + caches in trading.db.
Returns None when disabled / no data / on error — never fabricates. The pure
`score_*` helpers take already-fetched rows and are unit-tested.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import httpx

from src.utils.config import QUIVER_API_TOKEN
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.retry import with_retry

_BASE = "https://api.quiverquant.com/beta"
_TIMEOUT = 40
_TTL_DAILY = 12 * 60       # dark pool / flights refresh daily
_TTL_SLOW = 24 * 60        # gov contracts / lobbying update quarterly


def _enabled() -> bool:
    return bool(QUIVER_API_TOKEN)


def _to_float(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


@with_retry(max_retries=3, source="quiver")
def _quiver_get(path: str) -> list:
    headers = {"Authorization": f"Token {QUIVER_API_TOKEN}", "Accept": "application/json"}
    resp = httpx.get(f"{_BASE}{path}", headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _fetch(path: str, cache_key: str, ttl: int) -> list | None:
    if not _enabled():
        return None
    cached = cache_get(cache_key)
    if cached is not None:
        return cached.get("rows", [])
    try:
        rows = _quiver_get(path)
        log_api_call("quiver", path, "success", f"{len(rows)} rows")
        cache_set(cache_key, {"rows": rows}, ttl_minutes=ttl)
        return rows
    except Exception as exc:
        log_api_call("quiver", path, "error", str(exc))
        return None


# ── Tier 1: dark pool / off-exchange short volume ───────────────────────────


def score_dark_pool(rows: list[dict], *, recent_days: int = 10, base_days: int = 60) -> dict | None:
    """Off-exchange short-volume pressure. High/ rising short share = bearish.

    Each row: {Date, OTC_Short, OTC_Total, DPI}. short_ratio = short/total of
    off-exchange volume; ~0.5 is typical, >0.55 leans bearish, <0.45 bullish.
    """
    rows = [r for r in (rows or []) if _to_float(r.get("OTC_Total")) > 0]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r.get("Date") or "")

    def ratio(window: list[dict]) -> float | None:
        s = sum(_to_float(r.get("OTC_Short")) for r in window)
        t = sum(_to_float(r.get("OTC_Total")) for r in window)
        return (s / t) if t > 0 else None

    r_recent = ratio(rows[-recent_days:])
    r_base = ratio(rows[-base_days:])
    if r_recent is None:
        return None
    delta = (r_recent - r_base) if r_base is not None else 0.0

    if r_recent >= 0.55:
        direction, score = "bearish", -1
    elif r_recent <= 0.45:
        direction, score = "bullish", 1
    else:
        direction, score = "neutral", 0
    strength = max(0.2, min(0.85, abs(r_recent - 0.5) * 1.6 + abs(delta) * 6))

    return {
        "direction": direction,
        "strength": round(strength, 2),
        "score": score,
        "signal": direction,
        "recent_short_pct": round(r_recent * 100, 1),
        "baseline_short_pct": round(r_base * 100, 1) if r_base is not None else None,
        "trend": "rising" if delta > 0.01 else "falling" if delta < -0.01 else "flat",
        "dark_pool_index": round(_to_float(rows[-1].get("DPI")), 3) or None,
        "days_observed": len(rows),
        "latest_date": rows[-1].get("Date"),
    }


def get_dark_pool(symbol: str) -> dict | None:
    if not symbol:
        return None
    sym = symbol.upper().strip()
    rows = _fetch(f"/historical/offexchange/{sym}", f"quiver:darkpool:{sym}", _TTL_DAILY)
    return score_dark_pool(rows) if rows else None


# ── Tier 2: government contracts ────────────────────────────────────────────


def score_gov_contracts(rows: list[dict]) -> dict | None:
    """Federal contract awards. Growing recent awards = bullish catalyst.

    Each row: {Amount, Qtr, Year}. Returns None when the company has no
    contract history (most non-gov names) so the card is suppressed.
    """
    by_q: dict[tuple, float] = defaultdict(float)
    for r in rows or []:
        y = int(_to_float(r.get("Year")))
        q = int(_to_float(r.get("Qtr")))
        if y:
            by_q[(y, q)] += _to_float(r.get("Amount"))
    if not by_q:
        return None
    keys = sorted(by_q)
    amounts = [by_q[k] for k in keys]
    total = sum(amounts)
    if total <= 0:
        return None

    recent4 = sum(amounts[-4:])
    prior4 = sum(amounts[-8:-4])
    growth = ((recent4 - prior4) / prior4) if prior4 > 0 else None

    if growth is not None and growth >= 0.15:
        direction, score = "bullish", 1
    elif growth is not None and growth <= -0.40:
        direction, score = "bearish", -1
    else:
        direction, score = "neutral", 0
    strength = 0.45 + min(0.25, abs(growth) * 0.3) if growth is not None else 0.4
    if direction == "neutral":
        strength = min(strength, 0.45)

    return {
        "direction": direction,
        "strength": round(strength, 2),
        "score": score,
        "signal": direction,
        "recent_4q_total": round(recent4, 2),
        "prior_4q_total": round(prior4, 2),
        "yoy_growth_pct": round(growth * 100, 1) if growth is not None else None,
        "total_awarded": round(total, 2),
        "latest_period": f"Q{keys[-1][1]} {keys[-1][0]}",
    }


def get_gov_contracts(symbol: str) -> dict | None:
    if not symbol:
        return None
    sym = symbol.upper().strip()
    rows = _fetch(f"/historical/govcontracts/{sym}", f"quiver:govcon:{sym}", _TTL_SLOW)
    return score_gov_contracts(rows) if rows else None


# ── Tier 3: lobbying spend (low signal/noise) ───────────────────────────────


def score_lobbying(rows: list[dict]) -> dict | None:
    """Corporate lobbying spend + trend. Context only — capped low strength."""
    rows = rows or []
    by_year: dict[str, float] = defaultdict(float)
    issues: Counter = Counter()
    for r in rows:
        yr = (r.get("Date") or "")[:4]
        if yr:
            by_year[yr] += _to_float(r.get("Amount"))
        if r.get("Issue"):
            issues[" ".join(str(r["Issue"]).split())] += 1  # collapse embedded newlines
    if not by_year:
        return None
    years = sorted(by_year)
    recent = by_year[years[-1]]
    prior = by_year[years[-2]] if len(years) >= 2 else 0.0
    trend = "rising" if recent > prior * 1.15 else "falling" if recent < prior * 0.85 else "steady"

    return {
        "direction": "neutral",          # lobbying spend is ambiguous as a trade signal
        "strength": 0.3,                 # Tier 3 — context, not conviction
        "score": 0,
        "signal": "context",
        "recent_year": years[-1],
        "recent_spend": round(recent, 2),
        "prior_spend": round(prior, 2),
        "trend": trend,
        "top_issues": [i for i, _ in issues.most_common(3)],
        "filings": len(rows),
    }


def get_lobbying(symbol: str) -> dict | None:
    if not symbol:
        return None
    sym = symbol.upper().strip()
    rows = _fetch(f"/historical/lobbying/{sym}", f"quiver:lobby:{sym}", _TTL_SLOW)
    return score_lobbying(rows) if rows else None


# ── Tier 3: corporate flights / private jets (low signal/noise) ─────────────


def score_flights(rows: list[dict]) -> dict | None:
    """Recent corporate-jet activity for the ticker — M&A-rumor novelty."""
    rows = sorted(rows or [], key=lambda r: r.get("Date") or "")
    if not rows:
        return None
    routes = [
        f"{r.get('DepartureCity') or '?'} → {r.get('ArrivalCity') or '?'}"
        for r in rows[-5:]
    ]
    return {
        "direction": "neutral",
        "strength": round(min(0.3, 0.1 + len(rows) * 0.04), 2),  # Tier 3
        "score": 0,
        "signal": "activity",
        "flight_count": len(rows),
        "recent_routes": routes,
        "latest_date": rows[-1].get("Date"),
    }


def get_corporate_flights(symbol: str) -> dict | None:
    if not symbol:
        return None
    sym = symbol.upper().strip()
    # Live feed is global (all tickers); cache once and filter to this symbol.
    rows = _fetch("/live/flights", "quiver:flights:live", _TTL_DAILY)
    if not rows:
        return None
    mine = [r for r in rows if (r.get("Ticker") or "").upper().strip() == sym]
    return score_flights(mine) if mine else None
