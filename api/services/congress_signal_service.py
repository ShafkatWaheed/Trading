"""Congress sector tape — market-wide rollup of STOCK Act trades by sector.

Used by the market pulse page and brief Phase A to surface "where political
insiders have been buying/selling" alongside price flow and 13F flow.

Data path: Capitol Trades scrape via `src.data.congress.CongressDataProvider`
(no local DB). Strategy:
  1. `get_top_traded_stocks(days=window)` → top ~20 most-traded symbols.
  2. Per symbol, fetch the buys/sells summary (cached upstream 24h).
  3. Join via `stock_industry` → roll up buys/sells per sector.

Counts-based, NOT dollar-based. Capitol Trades discloses amounts as wide
ranges (e.g. "$1,001 - $15,000") with up to 15× spread, so a trade-count
aggregate is more honest than a midpoint-dollar one. The narrator can frame
"3 senators bought NVDA last 90d" without inventing a precise dollar figure.

45-day disclosure lag applies per the STOCK Act.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging

from src.utils.db import cache_get, cache_set, get_connection

logger = logging.getLogger(__name__)

_TAPE_CACHE_TTL_MINUTES = 6 * 60
_VALID_WINDOWS = (90, 180, 365)
_PARALLEL_WORKERS = 4


def get_sector_tape(window_days: int = 180, *, force: bool = False) -> dict:
    """Sector-level congress trade rollup over the trailing window.

    Returns:
        {
          "window_days": int,
          "as_of": "YYYY-MM-DD",
          "sectors": [
            {
              "sector": str,
              "net_trades": int,                 # buys - sells (signed)
              "buys_count": int,                 # number of buy trades
              "sells_count": int,                # number of sell trades
              "unique_politicians": int,         # distinct politicians active
              "direction": "buying"|"selling"|"neutral",
              "top_bought": [{"symbol", "buys", "sells", "politicians"}],  # top 5
              "top_sold":   [{"symbol", "buys", "sells", "politicians"}],  # top 3
            }, ...
          ],
          "symbols_scraped": int,
          "coverage_note": str,
        }
    """
    if window_days not in _VALID_WINDOWS:
        window_days = 180

    cache_key = f"congress:sector_tape:v1:{window_days}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    # 1. Top traded symbols (cheap — single scrape, cached upstream)
    try:
        from src.data.congress import CongressDataProvider
        prov = CongressDataProvider()
        top = prov.get_top_traded_stocks(days=window_days) or []
    except Exception as e:
        logger.warning("congress sector tape: top_traded fetch failed %r", e)
        return _empty_payload(window_days, note=f"Capitol Trades unavailable: {e}")

    symbols = [s["symbol"] for s in top if s.get("symbol")]
    if not symbols:
        return _empty_payload(window_days, note="No top-traded symbols returned by Capitol Trades")

    # 2. Per-symbol summaries in parallel (each cached upstream)
    summaries: dict[str, object] = {}
    def _fetch_one(sym: str):
        try:
            prov_local = CongressDataProvider()
            return sym, prov_local.get_summary(sym, days=window_days)
        except Exception as e:
            logger.info("congress sector tape: summary failed for %s: %r", sym, e)
            return sym, None

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
        for fut in as_completed([pool.submit(_fetch_one, s) for s in symbols]):
            sym, s = fut.result()
            if s is not None:
                summaries[sym] = s

    if not summaries:
        return _empty_payload(window_days, note="No per-symbol summaries available — Capitol Trades scrape silent")

    # 3. Sector join + roll-up
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT si.symbol, ind.sector
            FROM stock_industry si
            JOIN industries ind ON ind.code = si.industry_code
            WHERE si.is_primary = 1 AND si.symbol IN ({})
            """.format(",".join("?" for _ in summaries)),
            list(summaries.keys()),
        ).fetchall()
        sector_by_symbol = {r["symbol"]: r["sector"] for r in rows}
    finally:
        conn.close()

    deltas_by_sector: dict[str, dict] = {}
    for sym, s in summaries.items():
        sector = sector_by_symbol.get(sym)
        if not sector:
            continue
        bucket = deltas_by_sector.setdefault(sector, {
            "buys": 0, "sells": 0, "politicians": set(),
            "per_symbol": {},
        })
        buys = getattr(s, "total_buys", 0) or 0
        sells = getattr(s, "total_sells", 0) or 0
        bucket["buys"] += buys
        bucket["sells"] += sells
        for trade in (getattr(s, "recent_trades", []) or []):
            if getattr(trade, "politician", None):
                bucket["politicians"].add(trade.politician)
        bucket["per_symbol"][sym] = {
            "buys": buys, "sells": sells,
            "politicians": len(set(t.politician for t in (s.recent_trades or []) if getattr(t, "politician", None))),
        }

    # 4. Order sectors by absolute net activity
    out_sectors = []
    for sector in sorted(deltas_by_sector.keys(),
                          key=lambda s: abs(deltas_by_sector[s]["buys"] - deltas_by_sector[s]["sells"]),
                          reverse=True):
        bucket = deltas_by_sector[sector]
        buys, sells = bucket["buys"], bucket["sells"]
        net = buys - sells
        direction = "buying" if net > 0 else "selling" if net < 0 else "neutral"
        # Rank symbols within sector by net activity
        per_sym_sorted = sorted(
            ({"symbol": s, **v, "net": v["buys"] - v["sells"]}
             for s, v in bucket["per_symbol"].items()),
            key=lambda x: x["net"], reverse=True,
        )
        top_bought = [x for x in per_sym_sorted if x["net"] > 0][:5]
        top_sold = [x for x in reversed(per_sym_sorted) if x["net"] < 0][:3]
        out_sectors.append({
            "sector": sector,
            "net_trades": net,
            "buys_count": buys,
            "sells_count": sells,
            "unique_politicians": len(bucket["politicians"]),
            "direction": direction,
            "top_bought": top_bought,
            "top_sold": top_sold,
        })

    payload = {
        "window_days": window_days,
        "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
        "sectors": out_sectors,
        "symbols_scraped": len(summaries),
        "coverage_note": (
            f"Based on top {len(summaries)} most-traded symbols on Capitol Trades over "
            f"the trailing {window_days}d window. STOCK Act disclosures lag up to 45 days."
        ),
        "from_cache": False,
    }

    if out_sectors:
        try:
            cache_set(cache_key, payload, ttl_minutes=_TAPE_CACHE_TTL_MINUTES)
        except Exception:
            pass
    return payload


def _empty_payload(window_days: int, *, note: str) -> dict:
    return {
        "window_days": window_days,
        "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
        "sectors": [],
        "symbols_scraped": 0,
        "coverage_note": note,
        "from_cache": False,
    }
