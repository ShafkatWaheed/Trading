"""Unified market data service: Yahoo Finance (primary) → Alpha Vantage (fallback).

Single interface for quotes, fundamentals, and historical prices.
Yahoo is preferred (no API key, higher rate limit).
Alpha Vantage is the fallback (keyed, 5/min free tier).
"""

from datetime import datetime
from decimal import Decimal

import httpx
import pandas as pd

from src.models.stock import StockFundamentals, StockQuote
from src.utils.config import ALPHAVANTAGE_API_KEY, CACHE_TTL_QUOTE, CACHE_TTL_FUNDAMENTALS
from src.utils.db import cache_get, cache_set, log_api_call


AV_BASE = "https://www.alphavantage.co/query"


class MarketDataService:
    """Fetches quotes, fundamentals, and historical prices.

    Strategy: Yahoo Finance first (free, fast), Alpha Vantage fallback.
    """

    def get_quote(self, symbol: str) -> StockQuote:
        cache_key = f"market:quote:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return self._dict_to_quote(symbol, cached)

        data = self._try_sources(
            symbol,
            [self._fetch_quote_yahoo, self._fetch_quote_av],
            "quote",
        )
        cache_set(cache_key, data, ttl_minutes=CACHE_TTL_QUOTE)
        return self._dict_to_quote(symbol, data)

    def get_fundamentals(self, symbol: str) -> StockFundamentals:
        cache_key = f"market:fundamentals:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return self._dict_to_fundamentals(symbol, cached)

        data = self._try_sources(
            symbol,
            [self._fetch_fundamentals_yahoo, self._fetch_fundamentals_av],
            "fundamentals",
        )
        cache_set(cache_key, data, ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        return self._dict_to_fundamentals(symbol, data)

    def get_historical(self, symbol: str, period_days: int = 180) -> pd.DataFrame:
        cache_key = f"market:history:{symbol}:{period_days}"
        cached = cache_get(cache_key)
        if cached:
            return pd.DataFrame(cached)

        df = self._try_sources_df(
            symbol,
            period_days,
            [self._fetch_historical_yahoo, self._fetch_historical_av],
            "historical",
        )
        cache_set(cache_key, df.to_dict(orient="list"), ttl_minutes=CACHE_TTL_QUOTE)
        return df

    # --- Fallback orchestration ---

    def _try_sources(self, symbol: str, fetchers: list, data_type: str) -> dict:
        last_error: Exception | None = None
        for fetcher in fetchers:
            source = fetcher.__name__.split("_")[-1]  # "yahoo" or "av"
            try:
                data = fetcher(symbol)
                log_api_call(source, f"{data_type}/{symbol}", "success")
                return data
            except Exception as e:
                log_api_call(source, f"{data_type}/{symbol}", "error", str(e))
                last_error = e
                continue
        raise last_error or RuntimeError(f"All sources failed for {data_type}/{symbol}")

    def _try_sources_df(self, symbol: str, period_days: int, fetchers: list, data_type: str) -> pd.DataFrame:
        last_error: Exception | None = None
        for fetcher in fetchers:
            source = fetcher.__name__.split("_")[-1]
            try:
                df = fetcher(symbol, period_days)
                if df.empty:
                    raise ValueError("Empty DataFrame")
                log_api_call(source, f"{data_type}/{symbol}", "success")
                return df
            except Exception as e:
                log_api_call(source, f"{data_type}/{symbol}", "error", str(e))
                last_error = e
                continue
        raise last_error or RuntimeError(f"All sources failed for {data_type}/{symbol}")

    # --- Yahoo Finance (via MCP or yfinance) ---

    def _fetch_quote_yahoo(self, symbol: str) -> dict:
        # TODO: Wire to Yahoo Finance MCP server
        # The MCP server exposes tools like get_stock_quote(symbol)
        # For now, raise to trigger AV fallback
        raise NotImplementedError("Yahoo Finance MCP not yet wired")

    def _fetch_fundamentals_yahoo(self, symbol: str) -> dict:
        raise NotImplementedError("Yahoo Finance MCP not yet wired")

    def _fetch_historical_yahoo(self, symbol: str, period_days: int) -> pd.DataFrame:
        raise NotImplementedError("Yahoo Finance MCP not yet wired")

    # --- Alpha Vantage (REST API) ---

    def _fetch_quote_av(self, symbol: str) -> dict:
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        resp = httpx.get(AV_BASE, params=params, timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        gq = raw.get("Global Quote", {})
        if not gq:
            raise ValueError(f"No quote data for {symbol}")

        return {
            "price": gq.get("05. price", "0"),
            "open": gq.get("02. open", "0"),
            "high": gq.get("03. high", "0"),
            "low": gq.get("04. low", "0"),
            "volume": int(gq.get("06. volume", 0)),
            "previous_close": gq.get("08. previous close", "0"),
        }

    def _fetch_fundamentals_av(self, symbol: str) -> dict:
        params = {
            "function": "OVERVIEW",
            "symbol": symbol,
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        resp = httpx.get(AV_BASE, params=params, timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        if "Symbol" not in raw:
            raise ValueError(f"No overview data for {symbol}")

        return {
            "market_cap": raw.get("MarketCapitalization", "0"),
            "pe_ratio": raw.get("PERatio", None),
            "peg_ratio": raw.get("PEGRatio", None),
            "eps": raw.get("EPS", None),
            "eps_growth": raw.get("QuarterlyEarningsGrowthYOY", None),
            "revenue": raw.get("RevenueTTM", None),
            "revenue_growth": raw.get("QuarterlyRevenueGrowthYOY", None),
            "profit_margin": raw.get("ProfitMargin", None),
            "roe": raw.get("ReturnOnEquityTTM", None),
            "debt_to_equity": raw.get("DebtToEquityRatio", None),
            "free_cash_flow": raw.get("OperatingCashflowTTM", None),
            "dividend_yield": raw.get("DividendYield", None),
            "beta": raw.get("Beta", None),
            "week_52_high": raw.get("52WeekHigh", None),
            "week_52_low": raw.get("52WeekLow", None),
            "avg_volume": raw.get("AverageVolume", None),
            "sector": raw.get("Sector", ""),
            "industry": raw.get("Industry", ""),
            "description": raw.get("Description", ""),
        }

    def _fetch_historical_av(self, symbol: str, period_days: int) -> pd.DataFrame:
        outputsize = "full" if period_days > 100 else "compact"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        resp = httpx.get(AV_BASE, params=params, timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        ts = raw.get("Time Series (Daily)", {})
        if not ts:
            raise ValueError(f"No historical data for {symbol}")

        rows = []
        for date_str, values in sorted(ts.items()):
            rows.append({
                "date": date_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            })

        df = pd.DataFrame(rows)
        if period_days < len(df):
            df = df.tail(period_days).reset_index(drop=True)
        return df

    # --- Parsing ---

    def _dict_to_quote(self, symbol: str, data: dict) -> StockQuote:
        return StockQuote(
            symbol=symbol,
            price=Decimal(str(data.get("price", 0))),
            open=Decimal(str(data.get("open", 0))),
            high=Decimal(str(data.get("high", 0))),
            low=Decimal(str(data.get("low", 0))),
            volume=int(data.get("volume", 0)),
            previous_close=Decimal(str(data.get("previous_close", 0))),
            timestamp=datetime.utcnow(),
        )

    def _dict_to_fundamentals(self, symbol: str, data: dict) -> StockFundamentals:
        def dec(key: str) -> Decimal | None:
            val = data.get(key)
            if val is None or val == "None" or val == "-":
                return None
            return Decimal(str(val))

        return StockFundamentals(
            symbol=symbol,
            market_cap=Decimal(str(data.get("market_cap", 0))),
            pe_ratio=dec("pe_ratio"),
            peg_ratio=dec("peg_ratio"),
            eps=dec("eps"),
            eps_growth=dec("eps_growth"),
            revenue=dec("revenue"),
            revenue_growth=dec("revenue_growth"),
            profit_margin=dec("profit_margin"),
            roe=dec("roe"),
            debt_to_equity=dec("debt_to_equity"),
            free_cash_flow=dec("free_cash_flow"),
            dividend_yield=dec("dividend_yield"),
            beta=dec("beta"),
            week_52_high=dec("week_52_high"),
            week_52_low=dec("week_52_low"),
            avg_volume=int(data["avg_volume"]) if data.get("avg_volume") else None,
            sector=data.get("sector", ""),
            industry=data.get("industry", ""),
            description=data.get("description", ""),
        )
