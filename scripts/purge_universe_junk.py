"""One-off: purge non-equity junk rows from stocks_universe.

`index_loader` scraped a handful of non-equity line items out of ETF-holdings
CSVs: futures/cash placeholders and one row whose "symbol" is the iShares CSV
legal-disclaimer footer. They are not tradeable equities and carry no graph
edges. This removes exactly those, guarding every deletion on a zero-edge check
so a real (edge-bearing) ticker can never be removed by accident — even if the
hardcoded list were wrong.

Scoped to `source='index_loader'`. Committed for auditability (CLAUDE.md:
real-DB mutations live in scripts/, never tests).

Run: .venv/bin/python -m scripts.purge_universe_junk
"""
from __future__ import annotations

import logging
import sqlite3

from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)

# Explicit junk symbols — non-equity artifacts, all verified zero-edge.
JUNK_SYMBOLS = [
    "ESM6", "FAM6", "MSFUT", "RTYM6", "UBFUT",   # index futures
    "ETD_USD", "P5N994", "SGAFT", "XTSLA",        # cash / FX / internal codes
]
# The disclaimer-blob row has no fixed symbol — match it structurally. No real
# ticker is anywhere near this long.
_BLOB_MIN_LEN = 100

# (table, column) pairs that reference a universe symbol as a graph edge.
_EDGE_REFS = [
    ("stock_peers", "from_symbol"), ("stock_peers", "to_symbol"),
    ("stock_relations", "src_symbol"), ("stock_relations", "dst_symbol"),
    ("stock_industry", "symbol"), ("stock_commodity_exposure", "symbol"),
    ("institution_holdings", "symbol"), ("precomputed_scores", "symbol"),
    ("congress_trades", "ticker"),
]


def _present_edge_refs(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """The subset of _EDGE_REFS whose table+column actually exist in this DB."""
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = []
    for table, col in _EDGE_REFS:
        if table not in have:
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col in cols:
            out.append((table, col))
    return out


def _edge_count(conn: sqlite3.Connection, refs: list[tuple[str, str]], symbol: str) -> int:
    total = 0
    for table, col in refs:
        total += conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (symbol,)
        ).fetchone()[0]
    return total


def purge_junk_universe_rows(
    *,
    conn: sqlite3.Connection | None = None,
    source: str = "index_loader",
    symbols: list[str] | None = None,
    blob_min_len: int = _BLOB_MIN_LEN,
) -> dict:
    """Delete known non-equity junk rows, guarding on a zero-edge check.

    Resolves candidates from `symbols` (default JUNK_SYMBOLS) plus any row whose
    symbol length exceeds `blob_min_len`, all restricted to `source`. Any
    candidate that unexpectedly carries a graph edge is SKIPPED (never deleted)
    and reported. Returns {deleted: [...], skipped_with_edges: [(symbol, n), ...]}.
    """
    symbols = JUNK_SYMBOLS if symbols is None else symbols
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        refs = _present_edge_refs(conn)

        candidates: list[str] = []
        for sym in symbols:
            row = conn.execute(
                "SELECT symbol FROM stocks_universe WHERE symbol = ? AND source = ?",
                (sym, source),
            ).fetchone()
            if row:
                candidates.append(row["symbol"])
        for row in conn.execute(
            "SELECT symbol FROM stocks_universe WHERE LENGTH(symbol) > ? AND source = ?",
            (blob_min_len, source),
        ):
            candidates.append(row["symbol"])

        deleted: list[str] = []
        skipped: list[tuple[str, int]] = []
        for sym in candidates:
            edges = _edge_count(conn, refs, sym)
            label = sym if len(sym) <= 30 else sym[:30] + "…"
            if edges:
                logger.warning("keeping %r — has %d graph edge(s)", label, edges)
                skipped.append((label, edges))
                continue
            conn.execute(
                "DELETE FROM stocks_universe WHERE symbol = ? AND source = ?",
                (sym, source),
            )
            deleted.append(label)
        conn.commit()
        return {"deleted": deleted, "skipped_with_edges": skipped}
    finally:
        if own_conn:
            conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) FROM stocks_universe").fetchone()[0]
    finally:
        conn.close()

    res = purge_junk_universe_rows()

    conn = get_connection()
    try:
        after = conn.execute("SELECT COUNT(*) FROM stocks_universe").fetchone()[0]
    finally:
        conn.close()

    print(f"stocks_universe: {before} -> {after} ({before - after} removed)")
    print("deleted:", res["deleted"])
    if res["skipped_with_edges"]:
        print("SKIPPED (had edges, kept):", res["skipped_with_edges"])


if __name__ == "__main__":
    main()
