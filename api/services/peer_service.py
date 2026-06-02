"""Peer / competitor lookup service.

Reads `stock_peers` for a given stock with tier + industry attached.
Sorts by (source priority, confidence, similarity desc).

Source priority for ordering: hand > claude_validated > claude_batch.
Within source: confidence high > medium > low; then similarity desc.
"""

from __future__ import annotations

from src.utils.db import get_connection, init_db


_SOURCE_RANK: dict[str, int] = {
    "hand": 0,
    "claude_validated": 1,
    "claude_batch": 2,
}

_CONF_RANK: dict[str, int] = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def get_peers(symbol: str, *, max_results: int = 20) -> dict:
    """Return peers of `symbol` (and its share-class siblings) with tier +
    industry context.

    Dual-class tickers (GOOG/GOOGL, BRK.A/BRK.B, ...) have peer edges seeded
    against whichever class was canonical at the time. We expand the query
    to include siblings and drop sibling-pointing rows from the result so
    the returned peer set is the real competitor universe.

    Returns a dict shaped for `api.schemas.PeerListResponse`.
    """
    from src.graph.share_classes import equivalents, siblings as _siblings

    init_db()
    sym = symbol.upper()
    syms = equivalents(sym)
    sibling_set = _siblings(sym)
    sym_set = set(syms)            # queried sym + all siblings — used to skip self-edges
    placeholders = ",".join("?" * len(syms))

    conn = get_connection()
    try:
        # The stock itself — use the queried symbol for the self row, even if
        # we expand the query to siblings. Falls back to a sibling if the
        # queried symbol isn't in stocks_universe (rare).
        self_row = conn.execute(
            "SELECT symbol, name, tier FROM stocks_universe WHERE symbol = ?",
            (sym,),
        ).fetchone()
        if self_row is None:
            for sibling in sorted(sibling_set):
                self_row = conn.execute(
                    "SELECT symbol, name, tier FROM stocks_universe WHERE symbol = ?",
                    (sibling,),
                ).fetchone()
                if self_row:
                    break
        if self_row is None:
            return {"symbol": sym, "name": None, "tier": None, "peers": [], "total": 0}

        # Peer edges from EITHER share class
        rows = conn.execute(
            f"""
            SELECT
                sp.to_symbol AS symbol,
                u.name AS name,
                u.tier AS tier,
                i.sector AS sector,
                si.industry_code AS industry_code,
                sp.similarity,
                sp.overlap_dimensions,
                sp.source,
                sp.confidence,
                sp.evidence
            FROM stock_peers sp
            LEFT JOIN stocks_universe u ON u.symbol = sp.to_symbol
            LEFT JOIN stock_industry si
                ON si.symbol = sp.to_symbol AND si.is_primary = 1
            LEFT JOIN industries i ON i.code = si.industry_code
            WHERE sp.from_symbol IN ({placeholders})
            """,
            tuple(syms),
        ).fetchall()

        # Dedup by to_symbol (in case both share classes have edges to the
        # same peer) — keep the strongest (highest source rank + similarity).
        # Drop edges pointing AT the queried sym or a sibling (the GOOG↔GOOGL
        # "same company" edge shouldn't show up in either's peer list).
        best_by_to: dict[str, dict] = {}
        for r in rows:
            to_sym = r["symbol"]
            if to_sym in sym_set:
                continue
            new_row = {
                "symbol": to_sym,
                "name": r["name"],
                "tier": r["tier"],
                "sector": r["sector"],
                "industry_code": r["industry_code"],
                "similarity": float(r["similarity"]),
                "overlap_dimensions": _parse_overlap(r["overlap_dimensions"]),
                "source": r["source"],
                "confidence": r["confidence"],
                "evidence": r["evidence"],
            }
            existing = best_by_to.get(to_sym)
            if existing is None:
                best_by_to[to_sym] = new_row
                continue
            # Choose: better source first, then higher similarity
            new_key = (_SOURCE_RANK.get(new_row["source"], 99), -new_row["similarity"])
            old_key = (_SOURCE_RANK.get(existing["source"], 99), -existing["similarity"])
            if new_key < old_key:
                best_by_to[to_sym] = new_row

        peers = list(best_by_to.values())

        # Stable sort: (source rank, confidence rank, -similarity)
        peers.sort(
            key=lambda p: (
                _SOURCE_RANK.get(p["source"], 99),
                _CONF_RANK.get(p["confidence"], 99),
                -p["similarity"],
            )
        )

        total = len(peers)
        return {
            "symbol": sym,
            "name": self_row["name"],
            "tier": self_row["tier"],
            "peers": peers[:max_results],
            "total": total,
        }
    finally:
        conn.close()


def _parse_overlap(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]
