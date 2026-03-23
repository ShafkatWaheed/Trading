"""DataGateway: single entry point for all data in the system.

The report builder and app.py should ONLY use this class.
Never import individual providers directly from reports/ or app.py.
"""

import pandas as pd

from src.data.market import MarketDataService
from src.data.macro import MacroProvider
from src.data.polygon import PolygonProvider
from src.data.sec_edgar import SECEdgarProvider
from src.data.congress import CongressDataProvider
from src.data.news import NewsProvider
from src.models.stock import Stock, StockQuote, StockFundamentals
from src.models.data_types import (
    MacroSnapshot, OptionsSummary, MicrostructureSummary,
    InsiderSummary, InstitutionalSummary, CongressTradesSummary,
)


class DataGateway:
    """Unified data access for the entire application.

    Usage:
        gw = DataGateway()
        stock = gw.get_stock("AAPL")
        macro = gw.get_macro_snapshot()
        insider = gw.get_insider_summary("AAPL")
    """

    def __init__(self) -> None:
        self._market = MarketDataService()
        self._news = NewsProvider()
        # These may fail if API keys are missing — lazy init
        self._macro: MacroProvider | None = None
        self._polygon: PolygonProvider | None = None
        self._sec: SECEdgarProvider | None = None
        self._congress: CongressDataProvider | None = None

    # ── Lazy init for optional providers ─────────────────────────

    def _get_macro(self) -> MacroProvider:
        if self._macro is None:
            self._macro = MacroProvider()
        return self._macro

    def _get_polygon(self) -> PolygonProvider:
        if self._polygon is None:
            self._polygon = PolygonProvider()
        return self._polygon

    def _get_sec(self) -> SECEdgarProvider:
        if self._sec is None:
            self._sec = SECEdgarProvider()
        return self._sec

    def _get_congress(self) -> CongressDataProvider:
        if self._congress is None:
            self._congress = CongressDataProvider()
        return self._congress

    # ── Market Data (Yahoo → AV fallback) ────────────────────────

    def get_quote(self, symbol: str) -> StockQuote:
        return self._market.get_quote(symbol)

    def get_fundamentals(self, symbol: str) -> StockFundamentals:
        return self._market.get_fundamentals(symbol)

    def get_historical(self, symbol: str, period_days: int = 180) -> pd.DataFrame:
        return self._market.get_historical(symbol, period_days)

    def get_stock(self, symbol: str) -> Stock:
        """Convenience: fetch quote + fundamentals together. Either can fail."""
        quote = None
        fundamentals = None
        try:
            quote = self.get_quote(symbol)
        except Exception:
            pass
        try:
            fundamentals = self.get_fundamentals(symbol)
        except Exception:
            pass
        name = symbol
        if fundamentals and fundamentals.description:
            name = fundamentals.description.split(".")[0]
        return Stock(symbol=symbol, name=name, quote=quote, fundamentals=fundamentals)

    # ── Macro ────────────────────────────────────────────────────

    def get_macro_snapshot(self) -> MacroSnapshot | None:
        try:
            return self._get_macro().get_macro_snapshot()
        except Exception:
            return None

    # ── Options & Level 2 ────────────────────────────────────────

    def get_options_summary(self, symbol: str) -> OptionsSummary | None:
        try:
            return self._get_polygon().get_options_summary(symbol)
        except Exception:
            return None

    def get_microstructure(self, symbol: str) -> MicrostructureSummary | None:
        try:
            return self._get_polygon().get_microstructure_summary(symbol)
        except Exception:
            return None

    # ── Insider & Institutional (SEC EDGAR) ──────────────────────

    def get_insider_summary(self, symbol: str, days: int = 90) -> InsiderSummary | None:
        try:
            return self._get_sec().get_insider_summary(symbol, days)
        except Exception:
            return None

    def get_institutional_summary(self, symbol: str) -> InstitutionalSummary | None:
        try:
            return self._get_sec().get_institutional_summary(symbol)
        except Exception:
            return None

    # ── Congressional Trades ─────────────────────────────────────

    def get_congress_summary(self, symbol: str, days: int = 180) -> CongressTradesSummary | None:
        try:
            return self._get_congress().get_summary(symbol, days)
        except Exception:
            return None

    # ── News & Sentiment ─────────────────────────────────────────

    def get_stock_news(self, symbol: str, days: int = 7) -> list[dict]:
        try:
            return self._news.search_stock_news(symbol, days)
        except Exception:
            return []

    def get_research(self, query: str) -> list[dict]:
        try:
            return self._news.search_research(query)
        except Exception:
            return []

    # ── Sector Flows ────────────────────────────────────────────

    def get_sector_flows(self, period: str = "1mo") -> list[dict]:
        """Fetch sector ETF performance as proxy for money flows."""
        try:
            import yfinance as yf
            sectors = {
                "XLK": "Technology", "XLV": "Healthcare", "XLF": "Financials",
                "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
                "XLE": "Energy", "XLI": "Industrials", "XLRE": "Real Estate",
                "XLU": "Utilities", "XLB": "Materials", "XLC": "Communication Services",
            }
            results = []
            for ticker, name in sectors.items():
                try:
                    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
                    if data.empty or len(data) < 2:
                        continue
                    start_price = float(data["Close"].iloc[0])
                    end_price = float(data["Close"].iloc[-1])
                    change_pct = ((end_price - start_price) / start_price) * 100
                    volume_avg = float(data["Volume"].mean())
                    results.append({
                        "ticker": ticker, "sector": name,
                        "change_pct": round(change_pct, 2),
                        "start_price": round(start_price, 2),
                        "end_price": round(end_price, 2),
                        "avg_volume": int(volume_avg),
                    })
                except Exception:
                    continue
            return sorted(results, key=lambda x: x["change_pct"])
        except Exception:
            return []
