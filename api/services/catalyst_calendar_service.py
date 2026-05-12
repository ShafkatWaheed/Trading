"""30-day forward catalyst calendar for a stock.

Combines:
  - Earnings date (yfinance .calendar)
  - Ex-dividend + dividend pay dates (yfinance)
  - Stock splits if upcoming (rare)
  - Known macro events that move broad market (Fed FOMC, CPI, NFP) — hardcoded
    for current quarter.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta

from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 6 * 60
_HORIZON_DAYS = 30


# ── Hardcoded macro calendar (FOMC + key data releases) ───────────
# Update quarterly. Times are best-effort UTC. Only events in the next horizon
# show up.
_MACRO_EVENTS_2026: list[dict] = [
    {"date": "2026-05-14", "title": "CPI Apr",         "kind": "macro", "weight": "high"},
    {"date": "2026-05-30", "title": "Q1 GDP (2nd est)", "kind": "macro", "weight": "med"},
    {"date": "2026-06-06", "title": "NFP May",          "kind": "macro", "weight": "high"},
    {"date": "2026-06-12", "title": "CPI May",          "kind": "macro", "weight": "high"},
    {"date": "2026-06-18", "title": "FOMC Decision",    "kind": "macro", "weight": "very_high"},
    {"date": "2026-07-03", "title": "NFP Jun",          "kind": "macro", "weight": "high"},
    {"date": "2026-07-15", "title": "CPI Jun",          "kind": "macro", "weight": "high"},
    {"date": "2026-07-30", "title": "FOMC Decision",    "kind": "macro", "weight": "very_high"},
]


def _to_iso(d) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        return d[:10]
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    try:
        return str(d)[:10]
    except Exception:
        return None


def _collect_stock_catalysts(symbol: str, today: date) -> list[dict]:
    """Pull stock-specific events from yfinance."""
    events: list[dict] = []
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        cal = t.calendar or {}

        # Earnings date — yfinance returns a list (sometimes 1 or 2 dates)
        earn_dates = cal.get("Earnings Date") or []
        if not isinstance(earn_dates, list):
            earn_dates = [earn_dates]
        for ed in earn_dates:
            iso = _to_iso(ed)
            if iso:
                eps_avg = cal.get("Earnings Average")
                rev_avg = cal.get("Revenue Average")
                est = []
                if eps_avg is not None:
                    est.append(f"EPS est ${eps_avg:.2f}")
                if rev_avg is not None:
                    est.append(f"rev est ${rev_avg/1e9:.1f}B")
                events.append({
                    "date": iso,
                    "title": "Earnings Report",
                    "kind": "earnings",
                    "weight": "very_high",
                    "detail": " · ".join(est) if est else None,
                    "symbol_specific": True,
                })

        # Ex-dividend
        ex_div = _to_iso(cal.get("Ex-Dividend Date"))
        if ex_div:
            events.append({
                "date": ex_div,
                "title": "Ex-Dividend Date",
                "kind": "dividend",
                "weight": "low",
                "detail": "Buy before this date to receive the next dividend.",
                "symbol_specific": True,
            })

        # Dividend pay
        pay_div = _to_iso(cal.get("Dividend Date"))
        if pay_div:
            events.append({
                "date": pay_div,
                "title": "Dividend Pay Date",
                "kind": "dividend",
                "weight": "low",
                "detail": "Dividend distributed to holders of record.",
                "symbol_specific": True,
            })
    except Exception:
        pass

    return events


def _macro_in_horizon(today: date, end: date) -> list[dict]:
    out: list[dict] = []
    for e in _MACRO_EVENTS_2026:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if today <= d <= end:
            out.append({
                "date": e["date"],
                "title": e["title"],
                "kind": "macro",
                "weight": e["weight"],
                "detail": "Macro release — moves broad market and sector ETFs.",
                "symbol_specific": False,
            })
    return out


def get_catalyst_calendar(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"catalyst_calendar:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    today = date.today()
    end   = today + timedelta(days=_HORIZON_DAYS)

    events = _collect_stock_catalysts(symbol, today)
    events.extend(_macro_in_horizon(today, end))

    # Filter to horizon and sort
    in_horizon: list[dict] = []
    for e in events:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if today <= d <= end:
            days_out = (d - today).days
            in_horizon.append({**e, "days_out": days_out})

    in_horizon.sort(key=lambda e: (e["date"], e["title"]))

    payload = {
        "symbol":        symbol,
        "horizon_days":  _HORIZON_DAYS,
        "events":        in_horizon,
        "earnings_count": sum(1 for e in in_horizon if e["kind"] == "earnings"),
        "macro_count":    sum(1 for e in in_horizon if e["kind"] == "macro"),
        "dividend_count": sum(1 for e in in_horizon if e["kind"] == "dividend"),
        "last_updated":  datetime.utcnow().isoformat() + "Z",
        "from_cache":    False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
