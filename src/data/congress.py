"""Congressional stock trade data provider.

Source: Quiver Quantitative (`src.data.quiver_congress`), which ingests both
chambers' STOCK Act disclosures into the `congress_trades` table. This module
adapts that layer into the `CongressTrade` / `CongressTradesSummary` shapes so
`congress_signal_service`, `smart_money_service`, and `ai_analyst_service`
keep working without changes.

History: this used to scrape Capitol Trades, then the House Clerk PDFs +
Senate eFD portal directly. Those sources became unreliable or IP-blocked
(Akamai / CloudFront), so ingestion moved to Quiver, which uniquely carries
party AND chamber for every trade.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.data import quiver_congress
from src.models.data_types import CongressTrade, CongressTradesSummary
from src.utils.config import CACHE_TTL_FUNDAMENTALS
from src.utils.db import cache_get, cache_set, log_api_call


class CongressDataProvider:
    """Fetch congressional stock trading disclosures (House Clerk + Senate eFD backed)."""

    # ── Public API (unchanged shape) ──────────────────────────────────

    def get_trades_by_symbol(self, symbol: str, days: int = 180) -> list[CongressTrade]:
        cache_key = f"congress:symbol:{symbol}:{days}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_trade(t) for t in cached]

        trades = self._fetch_trades_by_symbol(symbol, days)
        cache_set(
            cache_key,
            [self._trade_to_dict(t) for t in trades],
            ttl_minutes=CACHE_TTL_FUNDAMENTALS,
        )
        log_api_call("congress", f"trades/symbol/{symbol}", "success")
        return trades

    def get_trades_by_politician(self, name: str, days: int = 180) -> list[CongressTrade]:
        cache_key = f"congress:politician:{name}:{days}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_trade(t) for t in cached]

        trades = self._fetch_trades_by_politician(name, days)
        cache_set(
            cache_key,
            [self._trade_to_dict(t) for t in trades],
            ttl_minutes=CACHE_TTL_FUNDAMENTALS,
        )
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

        result = quiver_congress.get_top_traded_stocks(days=days, limit=20)
        cache_set(cache_key, result, ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("congress", "top_traded", "success")
        return result

    # ── Quiver (congress_trades) adapter ─────────────────────────────

    def _fetch_trades_by_symbol(self, symbol: str, days: int) -> list[CongressTrade]:
        return [self._row_to_trade(r)
                for r in quiver_congress.get_trades_by_symbol(symbol, days=days)]

    def _fetch_trades_by_politician(self, name: str, days: int) -> list[CongressTrade]:
        return [self._row_to_trade(r)
                for r in quiver_congress.get_trades_by_politician(name, days=days)]

    def _row_to_trade(self, r: dict) -> CongressTrade:
        """Convert a `congress_trades` row dict to a CongressTrade.

        Chamber and party come straight from the row (Quiver carries both).
        """
        chamber = (r.get("chamber") or "House").strip() or "House"
        party = (r.get("party") or "Unknown").strip() or "Unknown"
        state = (r.get("state") or "").strip()

        amount_low = Decimal(str(r.get("amount_low") or 0))
        amount_high = Decimal(str(r.get("amount_high") or 0))
        amount_range = ""
        if amount_low or amount_high:
            amount_range = f"${int(amount_low):,} - ${int(amount_high):,}"

        trade_date = r.get("transaction_date") or ""
        notified = r.get("notification_date") or trade_date
        filed_date = self._parse_filing_date(r.get("filing_date") or "") or notified or trade_date

        days_to_file = 0
        try:
            if trade_date and filed_date:
                days_to_file = (
                    datetime.fromisoformat(filed_date)
                    - datetime.fromisoformat(trade_date)
                ).days
        except Exception:
            days_to_file = 0

        return CongressTrade(
            politician=(r.get("politician_name") or "Unknown").strip() or "Unknown",
            party=party,
            chamber=chamber,
            state=state,
            symbol=(r.get("ticker") or "").upper(),
            company="",  # not carried in the disclosure feed
            transaction_type=r.get("transaction_type") or "buy",
            amount_range=amount_range,
            amount_low=amount_low,
            amount_high=amount_high,
            trade_date=trade_date,
            filed_date=filed_date,
            days_to_file=days_to_file,
        )

    @staticmethod
    def _parse_filing_date(s: str) -> str:
        """Normalize Clerk's 'M/D/YYYY' filing_date to ISO 'YYYY-MM-DD'."""
        if not s:
            return ""
        for fmt in ("%m/%d/%Y", "%-m/%-d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s.strip(), fmt).date().isoformat()
            except ValueError:
                continue
        # Last-ditch try without padded zeros
        try:
            parts = s.strip().split("/")
            if len(parts) == 3:
                m, d, y = parts
                return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except Exception:
            pass
        return s.strip()

    # ── Summary roll-up (unchanged logic) ─────────────────────────────

    def _build_summary(self, symbol: str, trades: list[CongressTrade]) -> CongressTradesSummary:
        buys = [t for t in trades if t.transaction_type == "buy"]
        sells = [t for t in trades if t.transaction_type == "sell"]
        politicians = set(t.politician for t in trades)

        party_breakdown: dict[str, dict[str, int]] = {}
        for t in trades:
            if t.party not in party_breakdown:
                party_breakdown[t.party] = {"buy": 0, "sell": 0}
            party_breakdown[t.party][t.transaction_type] = (
                party_breakdown[t.party].get(t.transaction_type, 0) + 1
            )

        if len(buys) > len(sells) * 2:
            net_sentiment = "bullish"
        elif len(sells) > len(buys) * 2:
            net_sentiment = "bearish"
        else:
            net_sentiment = "mixed"

        buyer_counts: dict[str, int] = {}
        seller_counts: dict[str, int] = {}
        for t in buys:
            buyer_counts[t.politician] = buyer_counts.get(t.politician, 0) + 1
        for t in sells:
            seller_counts[t.politician] = seller_counts.get(t.politician, 0) + 1

        top_buyers = sorted(buyer_counts, key=buyer_counts.get, reverse=True)[:25]
        top_sellers = sorted(seller_counts, key=seller_counts.get, reverse=True)[:25]

        return CongressTradesSummary(
            symbol=symbol,
            total_trades=len(trades),
            total_buys=len(buys),
            total_sells=len(sells),
            unique_politicians=len(politicians),
            net_sentiment=net_sentiment,
            top_buyers=top_buyers,
            top_sellers=top_sellers,
            recent_trades=sorted(trades, key=lambda t: t.trade_date, reverse=True)[:50],
            party_breakdown=party_breakdown,
        )

    # ── Cache (de)serialization ───────────────────────────────────────

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
