"""Ownership service — top holders / also-held queries (Phase 7A)."""

from __future__ import annotations

from src.utils.db import get_connection, init_db


def top_holders(symbol: str, *, max_results: int = 20) -> dict:
    """Top institutional holders of a stock, sorted by pct_outstanding desc.

    Returns the latest as_of per (cik) — older filings are not shown.
    """
    init_db()
    sym = symbol.upper()
    conn = get_connection()
    try:
        # For each cik, take the most-recent holding row for this symbol.
        rows = conn.execute(
            """
            SELECT
                ih.cik,
                i.name AS institution_name,
                i.type AS institution_type,
                ih.value_usd,
                ih.pct_portfolio,
                ih.pct_outstanding,
                ih.as_of,
                ih.source
            FROM institution_holdings ih
            LEFT JOIN institutions i ON i.cik = ih.cik
            WHERE ih.symbol = ?
              AND ih.as_of = (
                  SELECT MAX(as_of)
                  FROM institution_holdings ih2
                  WHERE ih2.cik = ih.cik AND ih2.symbol = ih.symbol
              )
            ORDER BY ih.pct_outstanding DESC NULLS LAST, ih.value_usd DESC NULLS LAST
            LIMIT ?
            """,
            (sym, max_results),
        ).fetchall()

        return {
            "symbol": sym,
            "holders": [dict(r) for r in rows],
            "total": len(rows),
        }
    finally:
        conn.close()


def also_held(cik: str, *, max_results: int = 50) -> dict:
    """Other stocks held by a given institution, sorted by pct_portfolio desc."""
    init_db()
    conn = get_connection()
    try:
        institution_row = conn.execute(
            "SELECT cik, name, type, total_aum FROM institutions WHERE cik = ?",
            (cik,),
        ).fetchone()
        if institution_row is None:
            return {"cik": cik, "name": None, "type": None, "holdings": [], "total": 0}

        rows = conn.execute(
            """
            SELECT
                ih.symbol,
                u.name AS stock_name,
                u.tier,
                ih.value_usd,
                ih.pct_portfolio,
                ih.pct_outstanding,
                ih.rank_in_portfolio,
                ih.as_of
            FROM institution_holdings ih
            LEFT JOIN stocks_universe u ON u.symbol = ih.symbol
            WHERE ih.cik = ?
              AND ih.as_of = (
                  SELECT MAX(as_of)
                  FROM institution_holdings ih2
                  WHERE ih2.cik = ih.cik AND ih2.symbol = ih.symbol
              )
            ORDER BY ih.pct_portfolio DESC NULLS LAST, ih.value_usd DESC NULLS LAST
            LIMIT ?
            """,
            (cik, max_results),
        ).fetchall()

        return {
            "cik": cik,
            "name": institution_row["name"],
            "type": institution_row["type"],
            "total_aum": institution_row["total_aum"],
            "holdings": [dict(r) for r in rows],
            "total": len(rows),
        }
    finally:
        conn.close()
