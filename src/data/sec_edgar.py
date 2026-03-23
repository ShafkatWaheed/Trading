"""SEC EDGAR data provider for insider filings and institutional holdings.

Sources:
- SEC EDGAR API (free, no key required)
- Form 4: Corporate insider trades (CEO, CFO, directors, 10% owners)
- Form 13F: Institutional holdings (hedge funds, mutual funds)
"""

from datetime import datetime, timedelta
from decimal import Decimal
from xml.etree import ElementTree

import httpx

from src.models.data_types import (
    InsiderTrade, InsiderSummary, InstitutionalHolding, InstitutionalSummary,
)
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.config import CACHE_TTL_FUNDAMENTALS
from src.utils.rate_limit import SEC_LIMITER

SEC_USER_AGENT = "TradingAnalysis/1.0 admin@tradinganalysis.local"
SEC_BASE = "https://efts.sec.gov/LATEST"
SEC_DATA = "https://data.sec.gov"


class SECEdgarProvider:
    """Fetch SEC Form 4 (insider) and Form 13F (institutional) filings."""

    # --- Form 4: Insider Trades ---

    def get_insider_trades(self, symbol: str, days: int = 90) -> list[InsiderTrade]:
        cache_key = f"sec:insider:{symbol}:{days}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_insider(t) for t in cached]

        trades = self._fetch_insider_trades(symbol, days)
        cache_set(cache_key, [self._insider_to_dict(t) for t in trades], ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("sec_edgar", f"form4/{symbol}", "success")
        return trades

    def get_insider_summary(self, symbol: str, days: int = 90) -> InsiderSummary:
        trades = self.get_insider_trades(symbol, days)
        return self._build_insider_summary(symbol, trades, days)

    # --- Form 13F: Institutional Holdings ---

    def get_institutional_holdings(self, symbol: str) -> list[InstitutionalHolding]:
        cache_key = f"sec:13f:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_holding(h) for h in cached]

        holdings = self._fetch_institutional_holdings(symbol)
        cache_set(cache_key, [self._holding_to_dict(h) for h in holdings], ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("sec_edgar", f"13f/{symbol}", "success")
        return holdings

    def get_institutional_summary(self, symbol: str) -> InstitutionalSummary:
        holdings = self.get_institutional_holdings(symbol)
        return self._build_institutional_summary(symbol, holdings)

    # --- Fetch via SEC EDGAR EFTS API ---

    def _sec_get(self, url: str, params: dict | None = None) -> httpx.Response:
        SEC_LIMITER.acquire()
        headers = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}
        resp = httpx.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp

    def _get_cik(self, symbol: str) -> str:
        resp = self._sec_get(f"{SEC_DATA}/submissions/CIK{symbol}.json")
        if resp.status_code == 200:
            return resp.json().get("cik", "")
        # Fallback: search company tickers
        resp = self._sec_get("https://www.sec.gov/files/company_tickers.json")
        tickers = resp.json()
        for entry in tickers.values():
            if entry.get("ticker", "").upper() == symbol.upper():
                return str(entry["cik_str"]).zfill(10)
        return ""

    def _fetch_insider_trades(self, symbol: str, days: int) -> list[InsiderTrade]:
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "q": f'"{symbol}"',
            "dateRange": "custom",
            "startdt": start_date,
            "forms": "4",
            "from": "0",
            "size": "40",
        }
        resp = self._sec_get(f"{SEC_BASE}/search-index", params)
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])

        trades: list[InsiderTrade] = []
        for hit in hits:
            source = hit.get("_source", {})
            file_date = source.get("file_date", "")
            # Try to fetch the actual Form 4 XML for details
            filing_url = source.get("file_url", "")
            if filing_url:
                trade = self._parse_form4_from_index(symbol, source, filing_url)
                if trade:
                    trades.append(trade)

        # If EFTS didn't yield good results, try yfinance insider data as fallback
        if not trades:
            trades = self._fetch_insider_via_yfinance(symbol, days)

        return trades

    def _parse_form4_from_index(self, symbol: str, source: dict, filing_url: str) -> InsiderTrade | None:
        display_names = source.get("display_names", [])
        filer_name = display_names[0] if display_names else "Unknown"
        file_date = source.get("file_date", "")

        return InsiderTrade(
            filer_name=filer_name,
            filer_title="Insider",
            symbol=symbol,
            company=source.get("display_names", [""])[0] if len(source.get("display_names", [])) > 1 else symbol,
            transaction_type="sell",  # Default; actual type requires XML parsing
            shares=0,
            price=Decimal("0"),
            total_value=Decimal("0"),
            shares_owned_after=0,
            transaction_date=file_date,
            filing_date=file_date,
            sec_url=f"https://www.sec.gov/Archives/{filing_url}" if filing_url else "",
        )

    def _fetch_insider_via_yfinance(self, symbol: str, days: int) -> list[InsiderTrade]:
        """Fallback: use yfinance for insider transaction data."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)

            # Get insider transactions
            txns = ticker.insider_transactions
            if txns is None or txns.empty:
                return []

            cutoff = datetime.utcnow() - timedelta(days=days)
            trades: list[InsiderTrade] = []

            for _, row in txns.iterrows():
                start_date = row.get("Start Date") or row.get("startDate")
                if start_date is None:
                    continue
                if hasattr(start_date, 'to_pydatetime'):
                    trade_dt = start_date.to_pydatetime()
                else:
                    trade_dt = datetime.fromisoformat(str(start_date)[:10])

                if trade_dt.replace(tzinfo=None) < cutoff:
                    continue

                shares = int(row.get("Shares", 0) or 0)
                value = Decimal(str(abs(row.get("Value", 0) or 0)))
                price = Decimal(str(abs(value / shares))) if shares != 0 else Decimal("0")

                txn_text = str(row.get("Text", "") or row.get("Transaction", "")).lower()
                if "purchase" in txn_text or "buy" in txn_text or "acquisition" in txn_text:
                    txn_type = "buy"
                elif "sale" in txn_text or "sell" in txn_text or "disposition" in txn_text:
                    txn_type = "sell"
                else:
                    txn_type = "sell" if shares < 0 else "buy"

                trades.append(InsiderTrade(
                    filer_name=str(row.get("Insider", "") or row.get("insider", "Unknown")),
                    filer_title=str(row.get("Position", "") or row.get("position", "Insider")),
                    symbol=symbol,
                    company=symbol,
                    transaction_type=txn_type,
                    shares=abs(shares),
                    price=price,
                    total_value=value,
                    shares_owned_after=0,
                    transaction_date=trade_dt.strftime("%Y-%m-%d"),
                    filing_date=trade_dt.strftime("%Y-%m-%d"),
                    sec_url="",
                ))

            return trades
        except Exception:
            return []

    def _fetch_institutional_holdings(self, symbol: str) -> list[InstitutionalHolding]:
        """Fetch top institutional holders via yfinance (backed by Yahoo Finance)."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            holders = ticker.institutional_holders
            if holders is None or holders.empty:
                return []

            result: list[InstitutionalHolding] = []
            for _, row in holders.iterrows():
                shares = int(row.get("Shares", 0) or 0)
                value = Decimal(str(row.get("Value", 0) or 0))
                pct = Decimal(str(row.get("% Out", 0) or row.get("pctHeld", 0) or 0))

                date_reported = row.get("Date Reported", "")
                if hasattr(date_reported, 'strftime'):
                    date_str = date_reported.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_reported)[:10]

                result.append(InstitutionalHolding(
                    institution=str(row.get("Holder", "Unknown")),
                    symbol=symbol,
                    shares=shares,
                    value=value,
                    change_shares=0,
                    change_percent=Decimal("0"),
                    portfolio_percent=pct,
                    filing_date=date_str,
                    report_date=date_str,
                ))

            return result
        except Exception:
            return []

    # --- Build summaries ---

    def _build_insider_summary(self, symbol: str, trades: list[InsiderTrade], days: int) -> InsiderSummary:
        buys = [t for t in trades if t.transaction_type == "buy"]
        sells = [t for t in trades if t.transaction_type == "sell"]

        buy_value = sum(t.total_value for t in buys)
        sell_value = sum(t.total_value for t in sells)
        net_shares = sum(t.shares for t in buys) - sum(t.shares for t in sells)

        # Cluster buy detection: 2+ insiders buying within 7-day window
        cluster_buy = self._detect_cluster_buy(buys)

        # Signal
        if cluster_buy:
            signal = "strong buy"
        elif len(buys) > len(sells) * 2 and buy_value > sell_value:
            signal = "buy"
        elif len(sells) > len(buys) * 2 and sell_value > buy_value:
            signal = "sell"
        elif len(sells) > len(buys) * 3:
            signal = "strong sell"
        else:
            signal = "neutral"

        buyer_counts: dict[str, int] = {}
        seller_counts: dict[str, int] = {}
        for t in buys:
            buyer_counts[t.filer_name] = buyer_counts.get(t.filer_name, 0) + 1
        for t in sells:
            seller_counts[t.filer_name] = seller_counts.get(t.filer_name, 0) + 1

        return InsiderSummary(
            symbol=symbol,
            period_days=days,
            total_trades=len(trades),
            total_buys=len(buys),
            total_sells=len(sells),
            net_shares=net_shares,
            buy_value=buy_value,
            sell_value=sell_value,
            unique_insiders=len(set(t.filer_name for t in trades)),
            cluster_buy=cluster_buy,
            recent_trades=sorted(trades, key=lambda t: t.transaction_date, reverse=True)[:10],
            top_buyers=sorted(buyer_counts, key=buyer_counts.get, reverse=True)[:5],
            top_sellers=sorted(seller_counts, key=seller_counts.get, reverse=True)[:5],
            signal=signal,
        )

    def _detect_cluster_buy(self, buys: list[InsiderTrade]) -> bool:
        if len(buys) < 2:
            return False
        dates = sorted(set(t.transaction_date for t in buys))
        for i in range(len(dates) - 1):
            d1 = datetime.fromisoformat(dates[i])
            d2 = datetime.fromisoformat(dates[i + 1])
            if (d2 - d1).days <= 7:
                filers_in_window = set(
                    t.filer_name for t in buys
                    if dates[i] <= t.transaction_date <= dates[i + 1]
                )
                if len(filers_in_window) >= 2:
                    return True
        return False

    def _build_institutional_summary(self, symbol: str, holdings: list[InstitutionalHolding]) -> InstitutionalSummary:
        total_shares = sum(h.shares for h in holdings)
        net_change = sum(h.change_shares for h in holdings)
        new_pos = sum(1 for h in holdings if h.change_shares > 0 and h.change_shares == h.shares)
        closed = sum(1 for h in holdings if h.shares == 0)
        increased = sum(1 for h in holdings if h.change_shares > 0)
        decreased = sum(1 for h in holdings if h.change_shares < 0)

        top_holders = sorted(holdings, key=lambda h: h.value, reverse=True)[:10]
        notable = sorted(holdings, key=lambda h: abs(h.change_shares), reverse=True)[:10]

        return InstitutionalSummary(
            symbol=symbol,
            total_institutions=len(holdings),
            total_shares_held=total_shares,
            institutional_ownership_percent=Decimal("0"),  # requires float shares outstanding
            net_change_shares=net_change,
            new_positions=new_pos,
            closed_positions=closed,
            increased=increased,
            decreased=decreased,
            top_holders=top_holders,
            notable_changes=notable,
        )

    # --- Serialization ---

    def _insider_to_dict(self, t: InsiderTrade) -> dict:
        return {
            "filer_name": t.filer_name, "filer_title": t.filer_title,
            "symbol": t.symbol, "company": t.company,
            "transaction_type": t.transaction_type, "shares": t.shares,
            "price": str(t.price), "total_value": str(t.total_value),
            "shares_owned_after": t.shares_owned_after,
            "transaction_date": t.transaction_date, "filing_date": t.filing_date,
            "sec_url": t.sec_url,
        }

    def _dict_to_insider(self, d: dict) -> InsiderTrade:
        return InsiderTrade(
            filer_name=d["filer_name"], filer_title=d["filer_title"],
            symbol=d["symbol"], company=d["company"],
            transaction_type=d["transaction_type"], shares=d["shares"],
            price=Decimal(d["price"]), total_value=Decimal(d["total_value"]),
            shares_owned_after=d["shares_owned_after"],
            transaction_date=d["transaction_date"], filing_date=d["filing_date"],
            sec_url=d.get("sec_url", ""),
        )

    def _holding_to_dict(self, h: InstitutionalHolding) -> dict:
        return {
            "institution": h.institution, "symbol": h.symbol,
            "shares": h.shares, "value": str(h.value),
            "change_shares": h.change_shares, "change_percent": str(h.change_percent),
            "portfolio_percent": str(h.portfolio_percent),
            "filing_date": h.filing_date, "report_date": h.report_date,
        }

    def _dict_to_holding(self, d: dict) -> InstitutionalHolding:
        return InstitutionalHolding(
            institution=d["institution"], symbol=d["symbol"],
            shares=d["shares"], value=Decimal(d["value"]),
            change_shares=d["change_shares"], change_percent=Decimal(d["change_percent"]),
            portfolio_percent=Decimal(d["portfolio_percent"]),
            filing_date=d["filing_date"], report_date=d["report_date"],
        )
