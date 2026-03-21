"""Congressional stock trade data provider.

Sources:
- Capitol Trades MCP (free, no API key) — primary
- Quiver Quantitative API — fallback
- House Clerk XML feed (disclosures-clerk.house.gov)
- Senate EFD portal (efdsearch.senate.gov)
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.config import CACHE_TTL_FUNDAMENTALS


@dataclass
class CongressTrade:
    politician: str
    party: str  # Democrat / Republican / Independent
    chamber: str  # House / Senate
    state: str
    symbol: str
    company: str
    transaction_type: str  # buy / sell
    amount_range: str  # e.g. "$1K-$15K", "$50K-$100K"
    amount_low: Decimal
    amount_high: Decimal
    trade_date: str  # ISO 8601
    filed_date: str  # ISO 8601
    days_to_file: int
    price_at_trade: Decimal | None = None
    committees: list[str] = field(default_factory=list)


@dataclass
class CongressTradesSummary:
    symbol: str
    total_trades: int
    total_buys: int
    total_sells: int
    unique_politicians: int
    net_sentiment: str  # "bullish" / "bearish" / "mixed"
    top_buyers: list[str] = field(default_factory=list)
    top_sellers: list[str] = field(default_factory=list)
    recent_trades: list[CongressTrade] = field(default_factory=list)
    party_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)


class CongressDataProvider:
    """Fetch congressional stock trading disclosures."""

    def get_trades_by_symbol(self, symbol: str, days: int = 180) -> list[CongressTrade]:
        cache_key = f"congress:symbol:{symbol}:{days}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_trade(t) for t in cached]

        trades = self._fetch_trades_by_symbol(symbol, days)
        cache_set(cache_key, [self._trade_to_dict(t) for t in trades], ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("congress", f"trades/symbol/{symbol}", "success")
        return trades

    def get_trades_by_politician(self, name: str, days: int = 180) -> list[CongressTrade]:
        cache_key = f"congress:politician:{name}:{days}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_trade(t) for t in cached]

        trades = self._fetch_trades_by_politician(name, days)
        cache_set(cache_key, [self._trade_to_dict(t) for t in trades], ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("congress", f"trades/politician/{name}", "success")
        return trades

    def get_summary(self, symbol: str, days: int = 180) -> CongressTradesSummary:
        trades = self.get_trades_by_symbol(symbol, days)
        return self._build_summary(symbol, trades)

    def get_top_traded_stocks(self, days: int = 90) -> list[dict]:
        cache_key = f"congress:top_traded:{days}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        result = self._fetch_top_traded(days)
        cache_set(cache_key, result, ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("congress", "top_traded", "success")
        return result

    def _fetch_trades_by_symbol(self, symbol: str, days: int) -> list[CongressTrade]:
        # TODO: Implement via Capitol Trades MCP or direct API
        raise NotImplementedError("Connect to Capitol Trades MCP")

    def _fetch_trades_by_politician(self, name: str, days: int) -> list[CongressTrade]:
        # TODO: Implement via Capitol Trades MCP or direct API
        raise NotImplementedError("Connect to Capitol Trades MCP")

    def _fetch_top_traded(self, days: int) -> list[dict]:
        # TODO: Implement via Capitol Trades MCP
        raise NotImplementedError("Connect to Capitol Trades MCP")

    def _build_summary(self, symbol: str, trades: list[CongressTrade]) -> CongressTradesSummary:
        buys = [t for t in trades if t.transaction_type == "buy"]
        sells = [t for t in trades if t.transaction_type == "sell"]
        politicians = set(t.politician for t in trades)

        # Party breakdown
        party_breakdown: dict[str, dict[str, int]] = {}
        for t in trades:
            if t.party not in party_breakdown:
                party_breakdown[t.party] = {"buy": 0, "sell": 0}
            party_breakdown[t.party][t.transaction_type] = party_breakdown[t.party].get(t.transaction_type, 0) + 1

        # Net sentiment
        if len(buys) > len(sells) * 2:
            net_sentiment = "bullish"
        elif len(sells) > len(buys) * 2:
            net_sentiment = "bearish"
        else:
            net_sentiment = "mixed"

        # Top buyers/sellers by trade count
        buyer_counts: dict[str, int] = {}
        seller_counts: dict[str, int] = {}
        for t in buys:
            buyer_counts[t.politician] = buyer_counts.get(t.politician, 0) + 1
        for t in sells:
            seller_counts[t.politician] = seller_counts.get(t.politician, 0) + 1

        top_buyers = sorted(buyer_counts, key=buyer_counts.get, reverse=True)[:5]
        top_sellers = sorted(seller_counts, key=seller_counts.get, reverse=True)[:5]

        return CongressTradesSummary(
            symbol=symbol,
            total_trades=len(trades),
            total_buys=len(buys),
            total_sells=len(sells),
            unique_politicians=len(politicians),
            net_sentiment=net_sentiment,
            top_buyers=top_buyers,
            top_sellers=top_sellers,
            recent_trades=sorted(trades, key=lambda t: t.trade_date, reverse=True)[:10],
            party_breakdown=party_breakdown,
        )

    def _trade_to_dict(self, trade: CongressTrade) -> dict:
        return {
            "politician": trade.politician,
            "party": trade.party,
            "chamber": trade.chamber,
            "state": trade.state,
            "symbol": trade.symbol,
            "company": trade.company,
            "transaction_type": trade.transaction_type,
            "amount_range": trade.amount_range,
            "amount_low": str(trade.amount_low),
            "amount_high": str(trade.amount_high),
            "trade_date": trade.trade_date,
            "filed_date": trade.filed_date,
            "days_to_file": trade.days_to_file,
            "price_at_trade": str(trade.price_at_trade) if trade.price_at_trade else None,
            "committees": trade.committees,
        }

    def _dict_to_trade(self, d: dict) -> CongressTrade:
        return CongressTrade(
            politician=d["politician"],
            party=d["party"],
            chamber=d["chamber"],
            state=d["state"],
            symbol=d["symbol"],
            company=d["company"],
            transaction_type=d["transaction_type"],
            amount_range=d["amount_range"],
            amount_low=Decimal(d["amount_low"]),
            amount_high=Decimal(d["amount_high"]),
            trade_date=d["trade_date"],
            filed_date=d["filed_date"],
            days_to_file=d["days_to_file"],
            price_at_trade=Decimal(d["price_at_trade"]) if d.get("price_at_trade") else None,
            committees=d.get("committees", []),
        )
