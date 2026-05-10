"""Universe service — query the 4,800-stock universe with tier and industry filters."""

from __future__ import annotations

from typing import Iterable

from src.utils.db import get_connection, init_db


def _industries_for_symbols(conn, symbols: list[str]) -> dict[str, list[dict]]:
    """Return {symbol: [{code, sector, weight, is_primary}, ...]} for given symbols."""
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    rows = conn.execute(
        f"""
        SELECT si.symbol, si.industry_code, si.weight, si.is_primary, i.sector
        FROM stock_industry si
        LEFT JOIN industries i ON i.code = si.industry_code
        WHERE si.symbol IN ({placeholders})
        ORDER BY si.symbol, si.is_primary DESC, si.weight DESC
        """,
        symbols,
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append({
            "code": r["industry_code"],
            "sector": r["sector"],
            "weight": r["weight"],
            "is_primary": bool(r["is_primary"]),
        })
    return out


def get_universe(
    *,
    tier: Iterable[str] | None = None,
    industry: str | None = None,
    sector: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict:
    """Return universe slice with industries attached.

    Filters compose: tier ∩ industry ∩ sector. limit defaults to 500.
    """
    init_db()
    conn = get_connection()

    try:
        # Compose WHERE on stocks_universe.
        where = []
        params: list = []

        if tier:
            tlist = [t.upper() for t in tier]
            where.append("u.tier IN (" + ",".join("?" * len(tlist)) + ")")
            params.extend(tlist)

        # industry / sector filter joins through stock_industry + industries
        joins = ""
        if industry or sector:
            joins = """
                JOIN stock_industry si ON si.symbol = u.symbol
                LEFT JOIN industries i  ON i.code   = si.industry_code
            """
            if industry:
                where.append("si.industry_code = ?")
                params.append(industry)
            if sector:
                where.append("i.sector = ?")
                params.append(sector)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        sql = f"""
            SELECT DISTINCT u.symbol, u.name, u.tier, u.exchange, u.country,
                   u.market_cap, u.avg_dollar_volume,
                   u.in_sp500, u.in_russell1000, u.in_russell2000, u.in_tsx60, u.in_qqq
            FROM stocks_universe u
            {joins}
            {where_sql}
            ORDER BY
                CASE u.tier WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2 ELSE 3 END,
                u.market_cap DESC NULLS LAST,
                u.symbol
            LIMIT ? OFFSET ?
        """
        params2 = list(params) + [limit, offset]
        rows = conn.execute(sql, params2).fetchall()
        symbols = [r["symbol"] for r in rows]
        ind_map = _industries_for_symbols(conn, symbols)

        stocks = []
        for r in rows:
            stocks.append({
                "symbol": r["symbol"],
                "name": r["name"],
                "tier": r["tier"],
                "exchange": r["exchange"],
                "country": r["country"],
                "market_cap": r["market_cap"],
                "avg_dollar_volume": r["avg_dollar_volume"],
                "in_sp500": bool(r["in_sp500"]),
                "in_russell1000": bool(r["in_russell1000"]),
                "in_russell2000": bool(r["in_russell2000"]),
                "in_tsx60": bool(r["in_tsx60"]),
                "in_qqq": bool(r["in_qqq"]),
                "industries": ind_map.get(r["symbol"], []),
            })

        # Tier counts (over the entire universe — independent of pagination).
        count_rows = conn.execute(
            "SELECT tier, COUNT(*) FROM stocks_universe GROUP BY tier"
        ).fetchall()
        counts = {"A": 0, "B": 0, "C": 0, "D": 0, "total": 0}
        for row in count_rows:
            t = row[0]
            n = row[1]
            counts[t] = n
            counts["total"] += n

        return {
            "stocks": stocks,
            "counts": counts,
            "filters_applied": {
                "tier": ",".join(tier) if tier else None,
                "industry": industry,
                "sector": sector,
            },
        }
    finally:
        conn.close()
