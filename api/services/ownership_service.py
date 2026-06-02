"""Ownership service — top holders / also-held queries (Phase 7A)."""

from __future__ import annotations

from src.utils.db import get_connection, init_db


def top_holders(symbol: str, *, max_results: int = 20) -> dict:
    """Top institutional holders of a stock (or its share-class siblings),
    sorted by pct_outstanding desc.

    Returns the latest as_of per (cik) — older filings are not shown.

    Dual-class tickers (GOOG/GOOGL, BRK.A/BRK.B, ...) — a 13F filer might
    hold one class only or both. We query across all sibling tickers and
    aggregate per institution: sum value_usd and pct_outstanding across
    classes, keep the most-recent as_of, dedupe by CIK.
    """
    from src.graph.share_classes import equivalents

    init_db()
    sym = symbol.upper()
    syms = equivalents(sym)
    placeholders = ",".join("?" * len(syms))

    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT
                ih.cik,
                ih.symbol AS holding_symbol,
                i.name AS institution_name,
                i.type AS institution_type,
                ih.value_usd,
                ih.pct_portfolio,
                ih.pct_outstanding,
                ih.as_of,
                ih.source
            FROM institution_holdings ih
            LEFT JOIN institutions i ON i.cik = ih.cik
            WHERE ih.symbol IN ({placeholders})
              AND ih.as_of = (
                  SELECT MAX(as_of)
                  FROM institution_holdings ih2
                  WHERE ih2.cik = ih.cik AND ih2.symbol = ih.symbol
              )
            """,
            tuple(syms),
        ).fetchall()

        # Aggregate per CIK across share classes
        agg: dict[str, dict] = {}
        for r in rows:
            cik = r["cik"]
            if cik not in agg:
                agg[cik] = {
                    "cik": cik,
                    "institution_name": r["institution_name"],
                    "institution_type": r["institution_type"],
                    "value_usd": float(r["value_usd"] or 0),
                    "pct_portfolio": float(r["pct_portfolio"] or 0),
                    "pct_outstanding": float(r["pct_outstanding"] or 0),
                    "as_of": r["as_of"],
                    "source": r["source"],
                }
            else:
                row = agg[cik]
                row["value_usd"]      += float(r["value_usd"] or 0)
                row["pct_portfolio"]  += float(r["pct_portfolio"] or 0)
                row["pct_outstanding"]+= float(r["pct_outstanding"] or 0)
                # Keep the most-recent as_of for the aggregate
                if (r["as_of"] or "") > (row["as_of"] or ""):
                    row["as_of"] = r["as_of"]

        # Sort by pct_outstanding desc then value desc; cap to max_results
        holders = sorted(
            agg.values(),
            key=lambda h: (-(h["pct_outstanding"] or 0), -(h["value_usd"] or 0)),
        )[:max_results]

        # Strip zero-fill — restore None for fields that aggregated to 0 from
        # all-null inputs so the UI shows "—" instead of "0.00%".
        for h in holders:
            if h["value_usd"] == 0:       h["value_usd"] = None
            if h["pct_portfolio"] == 0:   h["pct_portfolio"] = None
            if h["pct_outstanding"] == 0: h["pct_outstanding"] = None

        return {
            "symbol": sym,
            "holders": holders,
            "total": len(holders),
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
