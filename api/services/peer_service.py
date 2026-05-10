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
    """Return peers of `symbol` with tier + industry context.

    Returns a dict shaped for `api.schemas.PeerListResponse`.
    """
    init_db()
    sym = symbol.upper()
    conn = get_connection()
    try:
        # The stock itself
        self_row = conn.execute(
            "SELECT symbol, name, tier FROM stocks_universe WHERE symbol = ?",
            (sym,),
        ).fetchone()
        if self_row is None:
            return {"symbol": sym, "name": None, "tier": None, "peers": [], "total": 0}

        # Peer edges + the peer's tier + (primary) industry
        rows = conn.execute(
            """
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
            WHERE sp.from_symbol = ?
            """,
            (sym,),
        ).fetchall()

        peers = []
        for r in rows:
            peers.append({
                "symbol": r["symbol"],
                "name": r["name"],
                "tier": r["tier"],
                "sector": r["sector"],
                "industry_code": r["industry_code"],
                "similarity": float(r["similarity"]),
                "overlap_dimensions": _parse_overlap(r["overlap_dimensions"]),
                "source": r["source"],
                "confidence": r["confidence"],
                "evidence": r["evidence"],
            })

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
