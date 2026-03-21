"""SEC EDGAR data provider for insider filings and institutional holdings.

Sources:
- SEC EDGAR API (free, no key required)
- Form 4: Corporate insider trades (CEO, CFO, directors, 10% owners)
- Form 13F: Institutional holdings (hedge funds, mutual funds)
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.config import CACHE_TTL_FUNDAMENTALS


@dataclass
class InsiderTrade:
    """SEC Form 4 — corporate insider transaction."""
    filer_name: str
    filer_title: str  # CEO, CFO, Director, 10% Owner, etc.
    symbol: str
    company: str
    transaction_type: str  # buy / sell / exercise
    shares: int
    price: Decimal
    total_value: Decimal
    shares_owned_after: int
    transaction_date: str  # ISO 8601
    filing_date: str  # ISO 8601
    sec_url: str = ""


@dataclass
class InsiderSummary:
    """Aggregated insider activity for a stock."""
    symbol: str
    period_days: int
    total_trades: int
    total_buys: int
    total_sells: int
    net_shares: int  # positive = net buying
    buy_value: Decimal
    sell_value: Decimal
    unique_insiders: int
    cluster_buy: bool  # 2+ insiders buying within 7 days
    recent_trades: list[InsiderTrade] = field(default_factory=list)
    top_buyers: list[str] = field(default_factory=list)
    top_sellers: list[str] = field(default_factory=list)
    signal: str = ""  # "strong buy" / "buy" / "neutral" / "sell" / "strong sell"


@dataclass
class InstitutionalHolding:
    """SEC Form 13F — institutional position."""
    institution: str
    symbol: str
    shares: int
    value: Decimal
    change_shares: int  # vs previous quarter
    change_percent: Decimal
    portfolio_percent: Decimal
    filing_date: str  # ISO 8601
    report_date: str  # quarter end date


@dataclass
class InstitutionalSummary:
    symbol: str
    total_institutions: int
    total_shares_held: int
    institutional_ownership_percent: Decimal
    net_change_shares: int  # positive = net accumulation
    new_positions: int
    closed_positions: int
    increased: int
    decreased: int
    top_holders: list[InstitutionalHolding] = field(default_factory=list)
    notable_changes: list[InstitutionalHolding] = field(default_factory=list)


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

    # --- Fetch (TODO: wire to SEC EDGAR API or MCP) ---

    def _fetch_insider_trades(self, symbol: str, days: int) -> list[InsiderTrade]:
        # TODO: Implement via SEC EDGAR API (https://efts.sec.gov/LATEST/search-index?q=...)
        # or via sec-edgar MCP server
        raise NotImplementedError("Connect to SEC EDGAR API")

    def _fetch_institutional_holdings(self, symbol: str) -> list[InstitutionalHolding]:
        # TODO: Implement via SEC EDGAR 13F API
        raise NotImplementedError("Connect to SEC EDGAR API")

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
