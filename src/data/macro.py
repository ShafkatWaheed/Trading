"""Macroeconomic data provider using Alpha Vantage + Yahoo Finance.

No separate API key needed — reuses existing Alpha Vantage key.

Alpha Vantage economic endpoints:
- FEDERAL_FUNDS_RATE, TREASURY_YIELD, CPI, INFLATION
- RETAIL_SALES, UNEMPLOYMENT, NONFARM_PAYROLL, REAL_GDP

Yahoo Finance tickers for real-time:
- ^TNX (10Y Treasury), ^FVX (5Y), ^IRX (13-week)
- ^VIX (volatility), DX-Y.NYB (dollar index)
"""

from datetime import datetime
from decimal import Decimal

import httpx
import pandas as pd

from src.models.data_types import MacroDataPoint, MacroSnapshot
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.config import ALPHAVANTAGE_API_KEY, CACHE_TTL_FUNDAMENTALS
from src.utils.rate_limit import AV_LIMITER


# Alpha Vantage economic function mappings
AV_ECONOMIC = {
    "fed_funds_rate": {"function": "FEDERAL_FUNDS_RATE", "interval": "monthly"},
    "treasury_10y": {"function": "TREASURY_YIELD", "interval": "monthly", "maturity": "10year"},
    "treasury_2y": {"function": "TREASURY_YIELD", "interval": "monthly", "maturity": "2year"},
    "treasury_3m": {"function": "TREASURY_YIELD", "interval": "monthly", "maturity": "3month"},
    "cpi": {"function": "CPI", "interval": "monthly"},
    "inflation": {"function": "INFLATION"},
    "unemployment_rate": {"function": "UNEMPLOYMENT"},
    "nonfarm_payrolls": {"function": "NONFARM_PAYROLL"},
    "real_gdp": {"function": "REAL_GDP", "interval": "quarterly"},
    "retail_sales": {"function": "RETAIL_SALES"},
}

# Yahoo Finance tickers for real-time market indicators
YAHOO_MACRO_TICKERS = {
    "vix": "^VIX",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "treasury_10y_rt": "^TNX",
    "treasury_5y_rt": "^FVX",
    "treasury_13w_rt": "^IRX",
    "dollar_index": "DX-Y.NYB",
    "gold": "GC=F",
    "oil": "CL=F",
}


class MacroProvider:
    """Fetch macroeconomic data via Alpha Vantage and Yahoo Finance."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        if not ALPHAVANTAGE_API_KEY:
            raise ValueError("ALPHAVANTAGE_API_KEY not set")

    def get_series(self, series_name: str, limit: int = 50) -> list[MacroDataPoint]:
        """Fetch an economic time series by name (e.g. 'fed_funds_rate', 'cpi')."""
        cache_key = f"macro:{series_name}:{limit}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_point(d) for d in cached]

        if series_name not in AV_ECONOMIC:
            raise ValueError(f"Unknown series: {series_name}. Available: {list(AV_ECONOMIC.keys())}")

        data = self._fetch_av_series(series_name, limit)
        if data:  # Only cache non-empty results
            cache_set(cache_key, [self._point_to_dict(d) for d in data], ttl_minutes=CACHE_TTL_FUNDAMENTALS)
            log_api_call("alphavantage", f"macro/{series_name}", "success")
        return data

    def get_latest(self, series_name: str) -> MacroDataPoint | None:
        data = self.get_series(series_name, limit=5)
        return data[0] if data else None

    def get_macro_snapshot(self) -> MacroSnapshot:
        """Build a snapshot of key macro indicators."""
        cache_key = "macro:snapshot"
        cached = cache_get(cache_key)
        if cached:
            return self._dict_to_snapshot(cached)

        snapshot = self._build_snapshot()
        cache_set(cache_key, self._snapshot_to_dict(snapshot), ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        return snapshot

    def get_historical_df(self, series_name: str, limit: int = 100) -> pd.DataFrame:
        data = self.get_series(series_name, limit)
        if not data:
            return pd.DataFrame()
        return pd.DataFrame([{"date": d.date, "value": float(d.value)} for d in data])

    # --- Alpha Vantage fetch ---

    def _fetch_av_series(self, series_name: str, limit: int) -> list[MacroDataPoint]:
        config = AV_ECONOMIC[series_name]
        params: dict[str, str] = {
            "function": config["function"],
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        if "interval" in config:
            params["interval"] = config["interval"]
        if "maturity" in config:
            params["maturity"] = config["maturity"]

        try:
            AV_LIMITER.acquire()
            resp = httpx.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:
            log_api_call("alphavantage", f"macro/{series_name}", "error", str(e))
            return []

        # Alpha Vantage returns {"name": "...", "interval": "...", "unit": "...", "data": [...]}
        data_key = "data"
        if data_key not in raw:
            log_api_call("alphavantage", f"macro/{series_name}", "error", f"No 'data' key in response: {list(raw.keys())}")
            return []

        points: list[MacroDataPoint] = []
        for entry in raw[data_key][:limit]:
            val = entry.get("value", "")
            if val == "." or val == "":
                continue
            points.append(MacroDataPoint(
                series_id=config["function"],
                series_name=series_name,
                value=Decimal(val),
                date=entry.get("date", ""),
                unit=raw.get("unit", ""),
                frequency=raw.get("interval", config.get("interval", "")),
            ))

        return points

    # --- Snapshot builder ---

    def _build_snapshot(self) -> MacroSnapshot:
        snapshot = MacroSnapshot(timestamp=datetime.utcnow())

        # ── Yahoo Finance for real-time indicators (no rate limit) ──
        try:
            import yfinance as yf
            yahoo_map = {
                "^TNX": "treasury_10y",   # 10Y Treasury yield (in %)
                "^VIX": "vix",
                "DX-Y.NYB": "dollar_index",
            }
            for ticker, attr in yahoo_map.items():
                try:
                    data = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
                    if not data.empty:
                        if hasattr(data.columns, 'levels') and data.columns.nlevels > 1:
                            data.columns = data.columns.get_level_values(0)
                        val = float(data["Close"].iloc[-1])
                        setattr(snapshot, attr, Decimal(str(round(val, 4))))
                except Exception:
                    continue

            # 2Y Treasury — ^TWO is unreliable, try IRX (13-week) as proxy or compute
            try:
                data_2y = yf.download("2YY=F", period="5d", progress=False, auto_adjust=True)
                if not data_2y.empty:
                    if hasattr(data_2y.columns, 'levels') and data_2y.columns.nlevels > 1:
                        data_2y.columns = data_2y.columns.get_level_values(0)
                    snapshot.treasury_2y = Decimal(str(round(float(data_2y["Close"].iloc[-1]), 4)))
            except Exception:
                pass
        except ImportError:
            pass

        # ── Alpha Vantage for slow-moving economic series ──
        # These change monthly/quarterly — make direct calls, skip get_series cache layer
        # to avoid caching empty results from rate limits
        av_direct_calls = [
            ("FEDERAL_FUNDS_RATE", {"interval": "monthly"}),
            ("UNEMPLOYMENT", {}),
            ("CPI", {"interval": "monthly"}),
            ("REAL_GDP", {"interval": "quarterly"}),
        ]

        av_results: dict[str, list[dict]] = {}
        for func_name, extra_params in av_direct_calls:
            try:
                AV_LIMITER.acquire()
                params = {"function": func_name, "apikey": ALPHAVANTAGE_API_KEY}
                params.update(extra_params)
                resp = httpx.get(self.BASE_URL, params=params, timeout=30)
                raw = resp.json()
                data_list = raw.get("data", [])
                valid = [d for d in data_list if d.get("value", ".") != "." and d.get("value", "") != ""]
                if valid:
                    av_results[func_name] = valid
                    log_api_call("alphavantage", f"macro/{func_name}", "success")
                else:
                    log_api_call("alphavantage", f"macro/{func_name}", "error", "empty data")
            except Exception as e:
                log_api_call("alphavantage", f"macro/{func_name}", "error", str(e))

        # Map results to snapshot fields
        if "FEDERAL_FUNDS_RATE" in av_results:
            snapshot.fed_funds_rate = Decimal(av_results["FEDERAL_FUNDS_RATE"][0]["value"])

        if "UNEMPLOYMENT" in av_results:
            snapshot.unemployment_rate = Decimal(av_results["UNEMPLOYMENT"][0]["value"])

        if "CPI" in av_results and len(av_results["CPI"]) >= 13:
            current = float(av_results["CPI"][0]["value"])
            year_ago = float(av_results["CPI"][12]["value"])
            yoy = ((current - year_ago) / year_ago) * 100
            snapshot.cpi_yoy = Decimal(str(round(yoy, 2)))

        if "REAL_GDP" in av_results and len(av_results["REAL_GDP"]) >= 2:
            current = float(av_results["REAL_GDP"][0]["value"])
            prev = float(av_results["REAL_GDP"][1]["value"])
            growth = ((current - prev) / prev) * 100
            snapshot.gdp_growth = Decimal(str(round(growth, 2)))

        # Compute yield spread
        if snapshot.treasury_10y and snapshot.treasury_2y:
            snapshot.yield_spread_10y2y = snapshot.treasury_10y - snapshot.treasury_2y

        return snapshot

    # --- Serialization ---

    def _point_to_dict(self, p: MacroDataPoint) -> dict:
        return {
            "series_id": p.series_id, "series_name": p.series_name,
            "value": str(p.value), "date": p.date,
            "unit": p.unit, "frequency": p.frequency,
        }

    def _dict_to_point(self, d: dict) -> MacroDataPoint:
        return MacroDataPoint(
            series_id=d["series_id"], series_name=d["series_name"],
            value=Decimal(d["value"]), date=d["date"],
            unit=d["unit"], frequency=d["frequency"],
        )

    def _snapshot_to_dict(self, s: MacroSnapshot) -> dict:
        return {
            "timestamp": s.timestamp.isoformat(),
            "fed_funds_rate": str(s.fed_funds_rate) if s.fed_funds_rate else None,
            "treasury_10y": str(s.treasury_10y) if s.treasury_10y else None,
            "treasury_2y": str(s.treasury_2y) if s.treasury_2y else None,
            "yield_spread_10y2y": str(s.yield_spread_10y2y) if s.yield_spread_10y2y else None,
            "cpi_yoy": str(s.cpi_yoy) if s.cpi_yoy else None,
            "unemployment_rate": str(s.unemployment_rate) if s.unemployment_rate else None,
            "gdp_growth": str(s.gdp_growth) if s.gdp_growth else None,
            "vix": str(s.vix) if s.vix else None,
            "consumer_sentiment": str(s.consumer_sentiment) if s.consumer_sentiment else None,
            "dollar_index": str(s.dollar_index) if s.dollar_index else None,
        }

    def _dict_to_snapshot(self, d: dict) -> MacroSnapshot:
        def dec(key: str) -> Decimal | None:
            return Decimal(d[key]) if d.get(key) else None

        return MacroSnapshot(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            fed_funds_rate=dec("fed_funds_rate"),
            treasury_10y=dec("treasury_10y"),
            treasury_2y=dec("treasury_2y"),
            yield_spread_10y2y=dec("yield_spread_10y2y"),
            cpi_yoy=dec("cpi_yoy"),
            unemployment_rate=dec("unemployment_rate"),
            gdp_growth=dec("gdp_growth"),
            vix=dec("vix"),
            consumer_sentiment=dec("consumer_sentiment"),
            dollar_index=dec("dollar_index"),
        )
