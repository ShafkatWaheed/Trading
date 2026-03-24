"""Unified market data service: Yahoo Finance (primary) → Alpha Vantage (fallback).

Single interface for quotes, fundamentals, and historical prices.
Yahoo is preferred (no API key, higher rate limit).
Alpha Vantage is the fallback (keyed, 5/min free tier).
"""

from datetime import datetime
from decimal import Decimal

import httpx
import pandas as pd
import yfinance as yf

from src.models.stock import StockFundamentals, StockQuote
from src.utils.config import ALPHAVANTAGE_API_KEY, CACHE_TTL_QUOTE, CACHE_TTL_FUNDAMENTALS
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.rate_limit import AV_LIMITER
from src.utils.retry import with_retry


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

    # --- Yahoo Finance (via yfinance library) ---

    def _fetch_quote_yahoo(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or "regularMarketPrice" not in info:
            raise ValueError(f"No Yahoo quote for {symbol}")

        return {
            "price": str(info.get("regularMarketPrice", 0)),
            "open": str(info.get("regularMarketOpen", 0)),
            "high": str(info.get("regularMarketDayHigh", 0)),
            "low": str(info.get("regularMarketDayLow", 0)),
            "volume": int(info.get("regularMarketVolume", 0)),
            "previous_close": str(info.get("regularMarketPreviousClose", 0)),
        }

    def _fetch_fundamentals_yahoo(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or "symbol" not in info:
            raise ValueError(f"No Yahoo fundamentals for {symbol}")

        return {
            "market_cap": str(info.get("marketCap", 0)),
            "pe_ratio": str(info["trailingPE"]) if info.get("trailingPE") else None,
            "peg_ratio": str(info["pegRatio"]) if info.get("pegRatio") else None,
            "eps": str(info["trailingEps"]) if info.get("trailingEps") else None,
            "eps_growth": str(info["earningsQuarterlyGrowth"]) if info.get("earningsQuarterlyGrowth") else None,
            "revenue": str(info["totalRevenue"]) if info.get("totalRevenue") else None,
            "revenue_growth": str(info["revenueGrowth"]) if info.get("revenueGrowth") else None,
            "profit_margin": str(info["profitMargins"]) if info.get("profitMargins") else None,
            "roe": str(info["returnOnEquity"]) if info.get("returnOnEquity") else None,
            "debt_to_equity": str(info["debtToEquity"]) if info.get("debtToEquity") else None,
            "free_cash_flow": str(info["freeCashflow"]) if info.get("freeCashflow") else None,
            "dividend_yield": str(info["dividendYield"]) if info.get("dividendYield") else None,
            "beta": str(info["beta"]) if info.get("beta") else None,
            "week_52_high": str(info["fiftyTwoWeekHigh"]) if info.get("fiftyTwoWeekHigh") else None,
            "week_52_low": str(info["fiftyTwoWeekLow"]) if info.get("fiftyTwoWeekLow") else None,
            "avg_volume": str(info.get("averageVolume", 0)),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "description": info.get("longBusinessSummary", ""),
        }

    def _fetch_historical_yahoo(self, symbol: str, period_days: int) -> pd.DataFrame:
        period = "1y" if period_days > 200 else "6mo" if period_days > 90 else "3mo"
        df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError(f"No Yahoo historical data for {symbol}")

        # Flatten multi-level columns if present
        if hasattr(df.columns, 'levels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

        if period_days < len(df):
            df = df.tail(period_days).reset_index(drop=True)
        return df[["date", "open", "high", "low", "close", "volume"]]

    # --- Earnings Calendar ---

    def get_earnings_calendar(self, symbol: str) -> list[dict]:
        cache_key = f"market:earnings:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        try:
            ticker = yf.Ticker(symbol)
            dates = ticker.earnings_dates
            if dates is None or dates.empty:
                return []

            results = []
            for date_idx, row in dates.iterrows():
                date_str = date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, 'strftime') else str(date_idx)[:10]
                eps_est = row.get("EPS Estimate")
                eps_act = row.get("Reported EPS")
                surprise = row.get("Surprise(%)")

                results.append({
                    "date": date_str,
                    "eps_estimate": float(eps_est) if eps_est is not None and str(eps_est) != "nan" else None,
                    "eps_actual": float(eps_act) if eps_act is not None and str(eps_act) != "nan" else None,
                    "surprise_pct": float(surprise) if surprise is not None and str(surprise) != "nan" else None,
                })

            cache_set(cache_key, results, ttl_minutes=CACHE_TTL_FUNDAMENTALS)
            log_api_call("yahoo", f"earnings/{symbol}", "success")
            return results
        except Exception as e:
            log_api_call("yahoo", f"earnings/{symbol}", "error", str(e))
            return []

    # --- Alpha Vantage (REST API) ---

    @with_retry(max_retries=2, source="alphavantage")
    def _fetch_quote_av(self, symbol: str) -> dict:
        AV_LIMITER.acquire()
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

    @with_retry(max_retries=2, source="alphavantage")
    def _fetch_fundamentals_av(self, symbol: str) -> dict:
        AV_LIMITER.acquire()
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

    @with_retry(max_retries=2, source="alphavantage")
    def _fetch_historical_av(self, symbol: str, period_days: int) -> pd.DataFrame:
        AV_LIMITER.acquire()
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
