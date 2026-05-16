"""FRED (St. Louis Fed) data provider — macro indicators.

Free API key, no rate limit. https://fred.stlouisfed.org/docs/api/api_key.html

Exposed shapes (None on failure / API key missing — never raises):

  * `get_series(series_id, start=None, end=None)` — full observation history
  * `get_latest(series_id)`                        — most recent value + date
  * `get_macro_snapshot()`                         — pre-bundled dashboard view

Common series IDs (built-in shortcuts via `MACRO_SERIES`):

    fed_funds       FEDFUNDS         monthly avg Fed funds rate
    treasury_10y    DGS10            10-year Treasury yield
    treasury_2y     DGS2             2-year Treasury yield
    cpi             CPIAUCSL         CPI All Urban
    cpi_core        CPILFESL         Core CPI (ex food/energy)
    unemployment    UNRATE           U-3 unemployment rate
    payrolls        PAYEMS           Total nonfarm payrolls
    gdp             GDP              Real GDP (chained 2017 $)
    housing_starts  HOUST            Housing starts
    industrial_prod INDPRO           Industrial production index
    consumer_sent   UMCSENT          U Michigan consumer sentiment
    vix             VIXCLS           CBOE VIX close
    yield_spread    T10Y2Y           10y minus 2y spread
    retail_sales    RSAFS            Retail & Food Services Sales

(ISM Manufacturing PMI is intentionally omitted — ISM revoked its FRED
license and the NAPM series is no longer updated.)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from src.utils.config import FRED_API_KEY
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.rate_limit import FRED_LIMITER


BASE = "https://api.stlouisfed.org/fred"
_TIMEOUT = 25


MACRO_SERIES: dict[str, dict[str, str]] = {
    "fed_funds":       {"id": "FEDFUNDS",  "label": "Fed Funds Rate (%)",        "unit": "%"},
    "treasury_10y":    {"id": "DGS10",     "label": "10Y Treasury Yield",        "unit": "%"},
    "treasury_2y":     {"id": "DGS2",      "label": "2Y Treasury Yield",         "unit": "%"},
    "yield_spread":    {"id": "T10Y2Y",    "label": "10Y–2Y Spread",             "unit": "%"},
    "cpi":             {"id": "CPIAUCSL",  "label": "CPI (All Urban)",           "unit": "index"},
    "cpi_core":        {"id": "CPILFESL",  "label": "Core CPI",                  "unit": "index"},
    "unemployment":    {"id": "UNRATE",    "label": "Unemployment Rate (U-3)",   "unit": "%"},
    "payrolls":        {"id": "PAYEMS",    "label": "Nonfarm Payrolls",          "unit": "thousands"},
    "gdp":             {"id": "GDP",       "label": "Real GDP",                  "unit": "$B"},
    "housing_starts":  {"id": "HOUST",     "label": "Housing Starts",            "unit": "thousands"},
    "industrial_prod": {"id": "INDPRO",    "label": "Industrial Production",     "unit": "index"},
    "consumer_sent":   {"id": "UMCSENT",   "label": "Consumer Sentiment (UoM)",  "unit": "index"},
    "vix":             {"id": "VIXCLS",    "label": "VIX (CBOE)",                "unit": "index"},
    "retail_sales":    {"id": "RSAFS",     "label": "Retail Sales",              "unit": "$M"},
}


def _enabled() -> bool:
    return bool(FRED_API_KEY)


def _request(path: str, params: dict | None = None) -> Any:
    if not _enabled():
        return None
    params = dict(params or {})
    params["api_key"] = FRED_API_KEY
    params["file_type"] = "json"
    FRED_LIMITER.acquire()
    try:
        resp = httpx.get(f"{BASE}{path}", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        log_api_call("fred", path, "success")
        return resp.json()
    except Exception as exc:
        log_api_call("fred", path, "error", str(exc))
        return None


# ── core ─────────────────────────────────────────────────────────────


def get_series(
    series_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[dict] | None:
    """Full observation history for a FRED series.

    Each row: {date, value} where `value` is `float | None` (None for
    missing periods like holidays/weekends in daily series).
    """
    key = f"fred:series:{series_id}:{start or 'all'}:{end or 'today'}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    params: dict[str, str] = {"series_id": series_id}
    if start:
        params["observation_start"] = start
    if end:
        params["observation_end"] = end
    data = _request("/series/observations", params)
    if not data or "observations" not in data:
        return None
    rows = []
    for o in data["observations"]:
        try:
            v = float(o["value"]) if o["value"] not in (".", "", None) else None
        except (TypeError, ValueError):
            v = None
        rows.append({"date": o["date"], "value": v})
    # Daily series like DGS10 update once per business day — cache 6h.
    cache_set(key, {"rows": rows}, ttl_minutes=6 * 60)
    return rows


def get_latest(series_id: str) -> dict | None:
    """Most recent non-null observation: {date, value, series_id}."""
    rows = get_series(series_id)
    if not rows:
        return None
    for r in reversed(rows):
        if r["value"] is not None:
            return {"series_id": series_id, "date": r["date"], "value": r["value"]}
    return None


def get_macro_snapshot() -> dict | None:
    """Dashboard view: latest value for each `MACRO_SERIES` shortcut.

    Returns {<shortcut>: {label, unit, date, value, series_id}}. Skips
    series where the fetch fails so the snapshot degrades gracefully.
    """
    if not _enabled():
        return None
    out: dict[str, dict] = {}
    for short, meta in MACRO_SERIES.items():
        latest = get_latest(meta["id"])
        if latest:
            out[short] = {
                "series_id": meta["id"],
                "label": meta["label"],
                "unit": meta["unit"],
                "date": latest["date"],
                "value": latest["value"],
            }
    return out or None
