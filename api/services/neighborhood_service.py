"""Neighborhood service — return a stock's 1-hop graph view.

Pulls suppliers (upstream), customers (downstream), peers, substitutes, and
complements with full metadata + tier of each neighbor for the React panel.
"""

from __future__ import annotations

from src.graph.traverse import neighborhood as graph_neighborhood
from src.utils.db import get_connection, init_db


def _enrich(rows: list, conn) -> list[dict]:
    """Add tier + name + sector for each edge target so the UI can render badges."""
    out = []
    if not rows:
        return out
    syms = {e.to_symbol for e in rows}
    placeholders = ",".join("?" * len(syms))
    meta = {
        r["symbol"]: dict(r)
        for r in conn.execute(
            f"""
            SELECT u.symbol, u.name, u.tier, i.sector
            FROM stocks_universe u
            LEFT JOIN stock_industry si
                ON si.symbol = u.symbol AND si.is_primary = 1
            LEFT JOIN industries i ON i.code = si.industry_code
            WHERE u.symbol IN ({placeholders})
            """,
            list(syms),
        ).fetchall()
    }
    for e in rows:
        m = meta.get(e.to_symbol, {})
        out.append({
            "symbol": e.to_symbol,
            "name": m.get("name"),
            "tier": m.get("tier"),
            "sector": m.get("sector"),
            "edge_type": e.edge_type,
            "strength": e.strength,
            "polarity": e.polarity,
            "confidence": e.confidence,
            "source": e.source,
            "evidence": e.evidence,
        })
    out.sort(key=lambda x: -x["strength"])
    return out


def get_neighborhood(symbol: str) -> dict:
    """1-hop graph view of a stock's relationships."""
    init_db()
    conn = get_connection()
    sym = symbol.upper()
    try:
        # Self metadata
        self_row = conn.execute(
            """
            SELECT u.symbol, u.name, u.tier, i.sector
            FROM stocks_universe u
            LEFT JOIN stock_industry si
                ON si.symbol = u.symbol AND si.is_primary = 1
            LEFT JOIN industries i ON i.code = si.industry_code
            WHERE u.symbol = ?
            """,
            (sym,),
        ).fetchone()

        groups = graph_neighborhood(sym, conn=conn)
        return {
            "symbol": sym,
            "name": self_row["name"] if self_row else None,
            "tier": self_row["tier"] if self_row else None,
            "sector": self_row["sector"] if self_row else None,
            "suppliers":   _enrich(groups["suppliers"], conn),
            "customers":   _enrich(groups["customers"], conn),
            "peers":       _enrich(groups["peers"], conn),
            "substitutes": _enrich(groups["substitutes"], conn),
            "complements": _enrich(groups["complements"], conn),
        }
    finally:
        conn.close()
