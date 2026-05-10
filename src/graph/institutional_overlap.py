"""Pairwise institutional-ownership overlap (Phase 7A).

Given two stocks, compute how strongly they share institutional holders.
The overlap score is the sum of `min(holdA_pct, holdB_pct)` across institutions
where both stocks appear in the institution's holdings — this captures the
"common large holders" notion: when BlackRock holds 7% of A and 7% of B, those
two stocks are coupled in the index-fund flow regime.

Materialised as `stock_relations` rows with `relation_type='common_institutional_holder'`
so the graph traversal layer can pick them up alongside supplier/customer edges.

The score is symmetric, so we write both directions (A→B and B→A) and only
the top-K neighbors per stock to keep the graph sparse.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from src.utils.db import get_connection, init_db


# ── primitive: score one pair ────────────────────────────────────


def overlap_score(
    holdings_a: dict[str, float],
    holdings_b: dict[str, float],
) -> tuple[float, list[str]]:
    """Compute the overlap score from two dicts {cik: pct_outstanding}.

    Score = sum(min(pct_A, pct_B)) across CIKs both hold.
    Returns (score, list_of_overlapping_ciks_sorted_by_min_pct_desc).
    """
    common = set(holdings_a) & set(holdings_b)
    if not common:
        return 0.0, []
    pairs = [
        (cik, min(holdings_a[cik], holdings_b[cik]))
        for cik in common
    ]
    pairs.sort(key=lambda p: -p[1])
    return sum(p[1] for p in pairs), [cik for cik, _ in pairs]


# ── batched computation: build the full edge set ────────────────


def materialise_overlap_edges(
    *,
    top_k: int = 20,
    min_score: float = 0.05,
    as_of: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Compute pairwise overlap and write top-K neighbors per symbol into stock_relations.

    Args:
        top_k: keep at most K strongest neighbors per symbol.
        min_score: drop overlaps below this floor (cleans noise).
        as_of: filter holdings to a specific filing-period. None = use latest
            available per (cik, symbol).

    Returns counts dict: {symbols, edges_written, deleted}.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        # 1) Wipe prior common_institutional_holder rows (idempotent refresh)
        cur = conn.execute(
            "DELETE FROM stock_relations WHERE relation_type='common_institutional_holder'"
        )
        deleted = cur.rowcount

        # 2) Pull holdings: {symbol: {cik: pct_outstanding}}
        if as_of:
            rows = conn.execute(
                """
                SELECT symbol, cik, pct_outstanding
                FROM institution_holdings
                WHERE as_of = ? AND pct_outstanding IS NOT NULL
                """,
                (as_of,),
            ).fetchall()
        else:
            # Use the latest as_of per (cik, symbol) — heuristic: take the row
            # with max(as_of) per (cik, symbol).
            rows = conn.execute(
                """
                SELECT cik, symbol, pct_outstanding
                FROM institution_holdings ih
                WHERE pct_outstanding IS NOT NULL
                  AND as_of = (
                      SELECT MAX(as_of)
                      FROM institution_holdings ih2
                      WHERE ih2.cik = ih.cik AND ih2.symbol = ih.symbol
                  )
                """,
            ).fetchall()

        holdings_by_symbol: dict[str, dict[str, float]] = defaultdict(dict)
        for r in rows:
            holdings_by_symbol[r["symbol"]][r["cik"]] = float(r["pct_outstanding"])

        symbols = sorted(holdings_by_symbol.keys())
        if len(symbols) < 2:
            conn.commit()
            return {"symbols": len(symbols), "edges_written": 0, "deleted": deleted}

        # 3) Compute pairwise scores. O(n²) — fine at prototype scale (~150 symbols).
        edges: dict[str, list[tuple[str, float, list[str]]]] = defaultdict(list)
        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i + 1:]:
                score, common_ciks = overlap_score(
                    holdings_by_symbol[sym_a],
                    holdings_by_symbol[sym_b],
                )
                if score < min_score:
                    continue
                edges[sym_a].append((sym_b, score, common_ciks))
                edges[sym_b].append((sym_a, score, common_ciks))

        # 4) For each symbol, keep top-K and write to stock_relations
        edges_written = 0
        for sym, neighbors in edges.items():
            neighbors.sort(key=lambda t: -t[1])
            for to_sym, score, common_ciks in neighbors[:top_k]:
                strength = min(1.0, score / 30.0)   # normalise: ~30% combined
                                                   # ownership is "very high"
                evidence = f"common holders ({len(common_ciks)}): " + ",".join(common_ciks[:3])
                conn.execute(
                    """
                    INSERT INTO stock_relations
                        (from_symbol, to_symbol, relation_type, strength, polarity, evidence)
                    VALUES (?, ?, 'common_institutional_holder', ?, 1.0, ?)
                    ON CONFLICT(from_symbol, to_symbol, relation_type) DO UPDATE SET
                        strength = excluded.strength,
                        evidence = excluded.evidence
                    """,
                    (sym, to_sym, strength, evidence),
                )
                edges_written += 1

        conn.commit()
        return {
            "symbols": len(symbols),
            "edges_written": edges_written,
            "deleted": deleted,
        }
    finally:
        if own_conn:
            conn.close()
