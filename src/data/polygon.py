"""Polygon.io data provider: Level 2 microstructure + options data.

Provides:
- NBBO quotes with bid/ask depth
- Level 2 order book
- Tick-by-tick trade feed
- Aggregated bars (1min to 1day)
- Options chains, Greeks, IV, unusual activity
- Put/Call ratio, max pain
"""

from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pandas as pd

from src.models.data_types import (
    Level2Quote, OrderBook, OrderBookLevel, Tick, MicrostructureSummary,
    OptionContract, OptionsChain, UnusualActivity, OptionsSummary,
)
from src.utils.config import POLYGON_API_KEY, CACHE_TTL_QUOTE
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.rate_limit import POLYGON_LIMITER


POLYGON_BASE = "https://api.polygon.io"


# ── Provider ────────────────────────────────────────────────────────

class PolygonProvider:
    """Unified Polygon.io provider for Level 2 data + options."""

    def __init__(self) -> None:
        if not POLYGON_API_KEY:
            raise ValueError("POLYGON_API_KEY not set")

    def _get(self, path: str, params: dict | None = None) -> dict:
        POLYGON_LIMITER.acquire()
        params = params or {}
        params["apiKey"] = POLYGON_API_KEY
        resp = httpx.get(f"{POLYGON_BASE}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Level 2 ─────────────────────────────────────────────────────

    def get_nbbo(self, symbol: str) -> Level2Quote:
        cache_key = f"polygon:nbbo:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return self._dict_to_quote(cached)

        raw = self._get(f"/v3/quotes/{symbol}", {"limit": 1})
        results = raw.get("results", [])
        if not results:
            raise ValueError(f"No NBBO data for {symbol}")

        r = results[0]
        bid = Decimal(str(r.get("bid_price", 0)))
        ask = Decimal(str(r.get("ask_price", 0)))
        mid = (bid + ask) / 2 if (bid + ask) > 0 else Decimal("0")
        spread = ask - bid
        spread_pct = (spread / mid * 100) if mid > 0 else Decimal("0")

        data = {
            "symbol": symbol, "bid_price": str(bid), "bid_size": r.get("bid_size", 0),
            "ask_price": str(ask), "ask_size": r.get("ask_size", 0),
            "spread": str(spread), "spread_percent": str(spread_pct),
            "midpoint": str(mid), "timestamp": r.get("sip_timestamp", ""),
        }
        cache_set(cache_key, data, ttl_minutes=1)
        log_api_call("polygon", f"nbbo/{symbol}", "success")
        return self._dict_to_quote(data)

    def get_trades(self, symbol: str, limit: int = 1000) -> list[Tick]:
        cache_key = f"polygon:trades:{symbol}:{limit}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_tick(t) for t in cached]

        raw = self._get(f"/v3/trades/{symbol}", {"limit": limit})
        results = raw.get("results", [])

        ticks = []
        for r in results:
            ticks.append(Tick(
                symbol=symbol,
                price=Decimal(str(r.get("price", 0))),
                size=r.get("size", 0),
                exchange=str(r.get("exchange", "")),
                conditions=r.get("conditions", []),
                timestamp=str(r.get("sip_timestamp", "")),
            ))

        cache_set(cache_key, [self._tick_to_dict(t) for t in ticks], ttl_minutes=CACHE_TTL_QUOTE)
        log_api_call("polygon", f"trades/{symbol}", "success")
        return ticks

    def get_aggregates(self, symbol: str, timespan: str = "day", period_days: int = 30) -> pd.DataFrame:
        cache_key = f"polygon:aggs:{symbol}:{timespan}:{period_days}"
        cached = cache_get(cache_key)
        if cached:
            return pd.DataFrame(cached)

        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=period_days)).strftime("%Y-%m-%d")

        raw = self._get(f"/v2/aggs/ticker/{symbol}/range/1/{timespan}/{start}/{end}")
        results = raw.get("results", [])

        rows = []
        for r in results:
            rows.append({
                "date": datetime.fromtimestamp(r["t"] / 1000).strftime("%Y-%m-%d"),
                "open": r.get("o", 0), "high": r.get("h", 0),
                "low": r.get("l", 0), "close": r.get("c", 0),
                "volume": r.get("v", 0), "vwap": r.get("vw", 0),
            })

        df = pd.DataFrame(rows)
        cache_set(cache_key, df.to_dict(orient="list"), ttl_minutes=CACHE_TTL_QUOTE)
        log_api_call("polygon", f"aggs/{symbol}/{timespan}", "success")
        return df

    def get_microstructure_summary(self, symbol: str) -> MicrostructureSummary:
        cache_key = f"polygon:micro:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return MicrostructureSummary(**{k: Decimal(v) if isinstance(v, str) and k not in ("symbol", "liquidity_score", "timestamp") else v for k, v in cached.items()})

        ticks = self.get_trades(symbol, limit=5000)
        nbbo = self.get_nbbo(symbol)

        buy_vol = sum(t.size for t in ticks if not t.is_buyer_maker)
        sell_vol = sum(t.size for t in ticks if t.is_buyer_maker)

        if ticks:
            total_value = sum(float(t.price) * t.size for t in ticks)
            total_shares = sum(t.size for t in ticks)
            vwap = Decimal(str(round(total_value / total_shares, 4))) if total_shares else Decimal("0")
        else:
            vwap = Decimal("0")

        large_trades = sum(1 for t in ticks if t.size > 10000)
        avg_depth = (nbbo.bid_size + nbbo.ask_size) / 2
        liquidity = "high" if avg_depth > 50000 else "medium" if avg_depth > 10000 else "low"

        summary = MicrostructureSummary(
            symbol=symbol, avg_spread=nbbo.spread, avg_spread_percent=nbbo.spread_percent,
            avg_bid_depth=nbbo.bid_size, avg_ask_depth=nbbo.ask_size,
            order_imbalance=Decimal(str(round((nbbo.bid_size - nbbo.ask_size) / max(nbbo.bid_size + nbbo.ask_size, 1), 4))),
            tick_count=len(ticks), vwap=vwap, buy_volume=buy_vol, sell_volume=sell_vol,
            buy_sell_ratio=Decimal(str(round(buy_vol / max(sell_vol, 1), 2))),
            large_trade_count=large_trades, liquidity_score=liquidity,
            timestamp=datetime.utcnow().isoformat(),
        )

        cache_set(cache_key, {
            "symbol": summary.symbol, "avg_spread": str(summary.avg_spread),
            "avg_spread_percent": str(summary.avg_spread_percent),
            "avg_bid_depth": summary.avg_bid_depth, "avg_ask_depth": summary.avg_ask_depth,
            "order_imbalance": str(summary.order_imbalance), "tick_count": summary.tick_count,
            "vwap": str(summary.vwap), "buy_volume": summary.buy_volume,
            "sell_volume": summary.sell_volume, "buy_sell_ratio": str(summary.buy_sell_ratio),
            "large_trade_count": summary.large_trade_count, "liquidity_score": summary.liquidity_score,
            "timestamp": summary.timestamp,
        }, ttl_minutes=CACHE_TTL_QUOTE)
        return summary

    # ── Options ─────────────────────────────────────────────────────

    def get_options_chain(self, symbol: str, expiration: str | None = None) -> list[OptionsChain]:
        cache_key = f"polygon:options:{symbol}:{expiration or 'next'}"
        cached = cache_get(cache_key)
        if cached:
            return [self._dict_to_chain(c) for c in cached]

        params: dict[str, str | int] = {"underlying_ticker": symbol, "limit": 250, "order": "asc", "sort": "strike_price"}
        if expiration:
            params["expiration_date"] = expiration

        raw = self._get("/v3/snapshot/options/" + symbol, params)
        results = raw.get("results", [])
        if not results:
            log_api_call("polygon", f"options/{symbol}", "error", "No options data")
            return []

        # Group by expiration
        chains_map: dict[str, OptionsChain] = {}
        for r in results:
            details = r.get("details", {})
            greeks = r.get("greeks", {})
            day = r.get("day", {})
            exp = details.get("expiration_date", "")

            if exp not in chains_map:
                chains_map[exp] = OptionsChain(
                    underlying=symbol,
                    underlying_price=Decimal(str(r.get("underlying_asset", {}).get("price", 0))),
                    expiration=exp,
                )

            contract = OptionContract(
                symbol=details.get("ticker", ""),
                underlying=symbol,
                contract_type=details.get("contract_type", "").lower(),
                strike=Decimal(str(details.get("strike_price", 0))),
                expiration=exp,
                bid=Decimal(str(r.get("last_quote", {}).get("bid", 0))),
                ask=Decimal(str(r.get("last_quote", {}).get("ask", 0))),
                last_price=Decimal(str(day.get("close", 0))),
                volume=day.get("volume", 0),
                open_interest=r.get("open_interest", 0),
                implied_volatility=Decimal(str(r.get("implied_volatility", 0))),
                delta=Decimal(str(greeks["delta"])) if greeks.get("delta") else None,
                gamma=Decimal(str(greeks["gamma"])) if greeks.get("gamma") else None,
                theta=Decimal(str(greeks["theta"])) if greeks.get("theta") else None,
                vega=Decimal(str(greeks["vega"])) if greeks.get("vega") else None,
            )

            chain = chains_map[exp]
            if contract.contract_type == "call":
                chain.calls.append(contract)
            else:
                chain.puts.append(contract)

        chains = list(chains_map.values())
        cache_set(cache_key, [self._chain_to_dict(c) for c in chains], ttl_minutes=CACHE_TTL_QUOTE)
        log_api_call("polygon", f"options/{symbol}", "success")
        return chains

    def get_options_summary(self, symbol: str) -> OptionsSummary:
        cache_key = f"polygon:optsummary:{symbol}"
        cached = cache_get(cache_key)
        if cached:
            return self._dict_to_optsummary(cached)

        chains = self.get_options_chain(symbol)
        if not chains:
            return OptionsSummary(
                underlying=symbol, underlying_price=Decimal("0"),
                put_call_ratio=Decimal("0"), total_call_volume=0,
                total_put_volume=0, total_call_oi=0, total_put_oi=0,
                avg_iv=Decimal("0"),
            )

        total_call_vol = sum(c.volume for chain in chains for c in chain.calls)
        total_put_vol = sum(c.volume for chain in chains for c in chain.puts)
        total_call_oi = sum(c.open_interest for chain in chains for c in chain.calls)
        total_put_oi = sum(c.open_interest for chain in chains for c in chain.puts)
        pcr = Decimal(str(round(total_put_vol / max(total_call_vol, 1), 4)))

        all_contracts = [c for chain in chains for c in chain.calls + chain.puts]
        iv_values = [c.implied_volatility for c in all_contracts if c.implied_volatility > 0]
        avg_iv = sum(iv_values) / len(iv_values) if iv_values else Decimal("0")

        summary = OptionsSummary(
            underlying=symbol,
            underlying_price=chains[0].underlying_price if chains else Decimal("0"),
            put_call_ratio=pcr,
            total_call_volume=total_call_vol, total_put_volume=total_put_vol,
            total_call_oi=total_call_oi, total_put_oi=total_put_oi,
            avg_iv=avg_iv,
        )
        summary.compute_sentiment()

        cache_set(cache_key, self._optsummary_to_dict(summary), ttl_minutes=CACHE_TTL_QUOTE)
        return summary

    # ── Serialization helpers ───────────────────────────────────────

    def _dict_to_quote(self, d: dict) -> Level2Quote:
        return Level2Quote(
            symbol=d["symbol"], bid_price=Decimal(d["bid_price"]), bid_size=d["bid_size"],
            ask_price=Decimal(d["ask_price"]), ask_size=d["ask_size"],
            spread=Decimal(d["spread"]), spread_percent=Decimal(d["spread_percent"]),
            midpoint=Decimal(d["midpoint"]), timestamp=d["timestamp"],
        )

    def _tick_to_dict(self, t: Tick) -> dict:
        return {"symbol": t.symbol, "price": str(t.price), "size": t.size, "exchange": t.exchange, "conditions": t.conditions, "timestamp": t.timestamp, "is_buyer_maker": t.is_buyer_maker}

    def _dict_to_tick(self, d: dict) -> Tick:
        return Tick(symbol=d["symbol"], price=Decimal(d["price"]), size=d["size"], exchange=d["exchange"], conditions=d["conditions"], timestamp=d["timestamp"], is_buyer_maker=d.get("is_buyer_maker", False))

    def _chain_to_dict(self, c: OptionsChain) -> dict:
        return {"underlying": c.underlying, "underlying_price": str(c.underlying_price), "expiration": c.expiration, "calls": [self._contract_to_dict(x) for x in c.calls], "puts": [self._contract_to_dict(x) for x in c.puts]}

    def _contract_to_dict(self, c: OptionContract) -> dict:
        return {"symbol": c.symbol, "underlying": c.underlying, "contract_type": c.contract_type, "strike": str(c.strike), "expiration": c.expiration, "bid": str(c.bid), "ask": str(c.ask), "last_price": str(c.last_price), "volume": c.volume, "open_interest": c.open_interest, "implied_volatility": str(c.implied_volatility), "delta": str(c.delta) if c.delta else None, "gamma": str(c.gamma) if c.gamma else None, "theta": str(c.theta) if c.theta else None, "vega": str(c.vega) if c.vega else None, "in_the_money": c.in_the_money}

    def _dict_to_chain(self, d: dict) -> OptionsChain:
        return OptionsChain(
            underlying=d["underlying"], underlying_price=Decimal(d["underlying_price"]),
            expiration=d["expiration"],
            calls=[self._dict_to_contract(c) for c in d["calls"]],
            puts=[self._dict_to_contract(c) for c in d["puts"]],
        )

    def _dict_to_contract(self, d: dict) -> OptionContract:
        def dec(k: str) -> Decimal | None:
            return Decimal(d[k]) if d.get(k) else None
        return OptionContract(symbol=d["symbol"], underlying=d["underlying"], contract_type=d["contract_type"], strike=Decimal(d["strike"]), expiration=d["expiration"], bid=Decimal(d["bid"]), ask=Decimal(d["ask"]), last_price=Decimal(d["last_price"]), volume=d["volume"], open_interest=d["open_interest"], implied_volatility=Decimal(d["implied_volatility"]), delta=dec("delta"), gamma=dec("gamma"), theta=dec("theta"), vega=dec("vega"), in_the_money=d.get("in_the_money", False))

    def _optsummary_to_dict(self, s: OptionsSummary) -> dict:
        return {"underlying": s.underlying, "underlying_price": str(s.underlying_price), "put_call_ratio": str(s.put_call_ratio), "total_call_volume": s.total_call_volume, "total_put_volume": s.total_put_volume, "total_call_oi": s.total_call_oi, "total_put_oi": s.total_put_oi, "avg_iv": str(s.avg_iv), "sentiment": s.sentiment}

    def _dict_to_optsummary(self, d: dict) -> OptionsSummary:
        s = OptionsSummary(underlying=d["underlying"], underlying_price=Decimal(d["underlying_price"]), put_call_ratio=Decimal(d["put_call_ratio"]), total_call_volume=d["total_call_volume"], total_put_volume=d["total_put_volume"], total_call_oi=d["total_call_oi"], total_put_oi=d["total_put_oi"], avg_iv=Decimal(d["avg_iv"]), sentiment=d.get("sentiment", ""))
        return s
