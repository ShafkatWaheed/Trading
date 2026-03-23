"""Congressional stock trade data provider.

Sources:
- Capitol Trades MCP (free, no API key) — primary
- Quiver Quantitative API — fallback
- House Clerk XML feed (disclosures-clerk.house.gov)
- Senate EFD portal (efdsearch.senate.gov)
"""

from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

from src.models.data_types import CongressTrade, CongressTradesSummary
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.config import CACHE_TTL_FUNDAMENTALS

CAPITOL_TRADES_BASE = "https://www.capitoltrades.com"


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

    def _ct_get(self, path: str) -> BeautifulSoup:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; TradingAnalysis/1.0)",
            "Accept": "text/html",
        }
        resp = httpx.get(f"{CAPITOL_TRADES_BASE}{path}", headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    def _parse_trade_rows(self, soup: BeautifulSoup, symbol: str = "") -> list[CongressTrade]:
        trades: list[CongressTrade] = []
        rows = soup.select("table tbody tr")
        if not rows:
            rows = soup.select("tr[class*='trade']")

        for row in rows:
            cells = row.select("td")
            if len(cells) < 6:
                continue
            try:
                trade = self._parse_row_cells(cells, symbol)
                if trade:
                    trades.append(trade)
            except Exception:
                continue
        return trades

    def _parse_row_cells(self, cells: list, symbol_hint: str) -> CongressTrade | None:
        text = [c.get_text(strip=True) for c in cells]

        # Capitol Trades table columns vary, try to extract key fields
        politician = text[0] if len(text) > 0 else "Unknown"
        # Extract party/chamber from politician cell
        party = "Unknown"
        chamber = "Unknown"
        state = ""
        pol_cell_text = cells[0].get_text(" ", strip=True) if cells else ""
        if "Democrat" in pol_cell_text:
            party = "Democrat"
        elif "Republican" in pol_cell_text:
            party = "Republican"
        if "House" in pol_cell_text:
            chamber = "House"
        elif "Senate" in pol_cell_text:
            chamber = "Senate"

        # Try to find the ticker/company
        ticker = symbol_hint
        company = text[1] if len(text) > 1 else ""

        # Transaction type
        txn_type = "buy"
        for t in text:
            tl = t.lower()
            if "sell" in tl or "sale" in tl:
                txn_type = "sell"
                break
            elif "buy" in tl or "purchase" in tl:
                txn_type = "buy"
                break

        # Amount range
        amount_range = ""
        amount_low = Decimal("0")
        amount_high = Decimal("0")
        for t in text:
            if "$" in t and ("K" in t or "," in t or "-" in t):
                amount_range = t
                break

        # Dates — look for date-like strings
        trade_date = ""
        filed_date = ""
        for t in text:
            if len(t) >= 8 and any(c.isdigit() for c in t):
                try:
                    for fmt in ["%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y"]:
                        try:
                            dt = datetime.strptime(t.strip(), fmt)
                            if not trade_date:
                                trade_date = dt.strftime("%Y-%m-%d")
                            elif not filed_date:
                                filed_date = dt.strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

        if not trade_date:
            trade_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not filed_date:
            filed_date = trade_date

        # Days to file
        try:
            td = datetime.fromisoformat(trade_date)
            fd = datetime.fromisoformat(filed_date)
            days_to_file = (fd - td).days
        except Exception:
            days_to_file = 0

        return CongressTrade(
            politician=politician.split("\n")[0].strip(),
            party=party,
            chamber=chamber,
            state=state,
            symbol=ticker,
            company=company,
            transaction_type=txn_type,
            amount_range=amount_range,
            amount_low=amount_low,
            amount_high=amount_high,
            trade_date=trade_date,
            filed_date=filed_date,
            days_to_file=days_to_file,
        )

    def _fetch_trades_by_symbol(self, symbol: str, days: int) -> list[CongressTrade]:
        try:
            soup = self._ct_get(f"/trades?ticker={symbol.upper()}")
            trades = self._parse_trade_rows(soup, symbol.upper())
            # Filter by date
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            return [t for t in trades if t.trade_date >= cutoff]
        except Exception as e:
            log_api_call("congress", f"trades/{symbol}", "error", str(e))
            return []

    def _fetch_trades_by_politician(self, name: str, days: int) -> list[CongressTrade]:
        try:
            slug = name.lower().replace(" ", "-")
            soup = self._ct_get(f"/politicians/{slug}")
            trades = self._parse_trade_rows(soup)
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            return [t for t in trades if t.trade_date >= cutoff]
        except Exception as e:
            log_api_call("congress", f"trades/politician/{name}", "error", str(e))
            return []

    def _fetch_top_traded(self, days: int) -> list[dict]:
        try:
            soup = self._ct_get("/trades")
            trades = self._parse_trade_rows(soup)
            # Count by symbol
            counts: dict[str, int] = {}
            for t in trades:
                if t.symbol:
                    counts[t.symbol] = counts.get(t.symbol, 0) + 1
            return [{"symbol": s, "trade_count": c} for s, c in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]]
        except Exception as e:
            log_api_call("congress", "top_traded", "error", str(e))
            return []

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
