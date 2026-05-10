"""BFS-style traversal over the knowledge graph.

Walks `stock_peers` and/or `stock_relations` from a set of seed symbols up
to N hops. Returns one entry per discovered symbol with its hop distance,
the edge that brought it in, and aggregated polarity.

Design goals:
    * Pure SQL lookups + Python set logic — no graph library, no ORM
    * Deterministic ordering (alphabetical within each layer)
    * Per-edge polarity carried forward so substitutes can flip signs
    * Caller-friendly: returns dataclass objects, not raw rows

Edge types respected:
    * stock_peers       — relation_type='peer' (implicit)
    * stock_relations   — relation_type ∈ {supplier, customer, substitute, complement}

Hop polarity rules:
    * peer / complement / supplier / customer  → polarity preserved
    * substitute  → flips sign at each hop (so AAPL → TSLA via substitute and
                    TSLA → XOM via substitute give AAPL ≈ XOM with double flip)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from src.utils.db import get_connection, init_db


# Allowed relation types for traversal. Not every type is always desired —
# callers can filter via `edge_types`.
ALL_EDGE_TYPES: frozenset[str] = frozenset({
    "peer", "supplier", "customer", "substitute", "complement",
})


@dataclass
class Edge:
    """One traversal step. `polarity` is the cumulative sign at this hop."""
    from_symbol: str
    to_symbol: str
    edge_type: str             # 'peer' | 'supplier' | 'customer' | 'substitute' | 'complement'
    strength: float            # 0..1 — magnitude of the relationship
    polarity: float            # -1..1 — sign at this hop (after accumulation)
    confidence: str            # 'high' | 'medium' | 'low' — peer confidence; 'high' for hand-loaded relations
    source: str                # 'hand' | 'claude_batch' | '10k_mined' | etc.
    evidence: str | None = None


@dataclass
class GraphResult:
    """Per-symbol expansion outcome."""
    symbol: str
    hop: int                   # 0 = seed, 1 = direct, 2 = 2-hop, ...
    incoming_edges: list[Edge] = field(default_factory=list)
    cumulative_polarity: float = 1.0    # net sign of best path to this node
    cumulative_strength: float = 1.0    # 0..1 — best path strength


# ── DB lookups ────────────────────────────────────────────────────


def _peers_of(conn: sqlite3.Connection, symbol: str) -> list[Edge]:
    """All peer edges from `symbol`."""
    rows = conn.execute(
        """
        SELECT to_symbol, similarity, source, confidence, evidence
        FROM stock_peers
        WHERE from_symbol = ?
        """,
        (symbol,),
    ).fetchall()
    return [
        Edge(
            from_symbol=symbol,
            to_symbol=r["to_symbol"],
            edge_type="peer",
            strength=float(r["similarity"]),
            polarity=1.0,                   # peers always positive at the edge level
            confidence=r["confidence"],
            source=r["source"],
            evidence=r["evidence"],
        )
        for r in rows
    ]


def _relations_of(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    relation_types: Iterable[str] | None = None,
) -> list[Edge]:
    """All stock_relations edges from `symbol`, filtered by type."""
    if relation_types:
        types = list(relation_types)
        ph = ",".join("?" * len(types))
        sql = f"""
            SELECT to_symbol, relation_type, strength, polarity, evidence
            FROM stock_relations
            WHERE from_symbol = ? AND relation_type IN ({ph})
        """
        params = [symbol, *types]
    else:
        sql = (
            "SELECT to_symbol, relation_type, strength, polarity, evidence "
            "FROM stock_relations WHERE from_symbol = ?"
        )
        params = [symbol]
    rows = conn.execute(sql, params).fetchall()
    return [
        Edge(
            from_symbol=symbol,
            to_symbol=r["to_symbol"],
            edge_type=r["relation_type"],
            strength=float(r["strength"]),
            polarity=float(r["polarity"]),
            confidence="high",              # hand/spine + 10k-mined are all "high" at relation level
            source="stock_relations",
            evidence=r["evidence"],
        )
        for r in rows
    ]


# ── public expansion ────────────────────────────────────────────


def expand(
    seed: Iterable[str],
    *,
    hops: int = 1,
    edge_types: Iterable[str] | None = None,
    starting_polarity: dict[str, float] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, GraphResult]:
    """Walk the graph BFS-style up to `hops` hops from `seed`.

    Args:
        seed: starting symbol set.
        hops: max distance to walk (1 = direct neighbors only; 2 = neighbors-of-neighbors).
        edge_types: subset of {'peer','supplier','customer','substitute','complement'}.
            None means all five.
        starting_polarity: optional per-seed polarity carrier (e.g. for news
            impact: a stock surfaced by a +keyword carries +1; by a -keyword
            carries -1). Defaults to +1 for every seed.

    Returns:
        Dict {symbol: GraphResult}. Seed symbols included with hop=0.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    seed_set = {s.upper() for s in seed}
    if edge_types is None:
        types = ALL_EDGE_TYPES
    else:
        types = {t.lower() for t in edge_types} & ALL_EDGE_TYPES
    starting_polarity = starting_polarity or {}

    # Seed nodes
    results: dict[str, GraphResult] = {
        sym: GraphResult(
            symbol=sym,
            hop=0,
            cumulative_polarity=starting_polarity.get(sym, 1.0),
            cumulative_strength=1.0,
        )
        for sym in seed_set
    }

    # Frontier: list of (symbol, current_polarity, current_strength)
    frontier: list[tuple[str, float, float]] = [
        (sym, results[sym].cumulative_polarity, 1.0) for sym in sorted(seed_set)
    ]

    try:
        for hop in range(1, hops + 1):
            next_frontier: list[tuple[str, float, float]] = []
            for sym, pol_in, str_in in frontier:
                edges: list[Edge] = []
                if "peer" in types:
                    edges.extend(_peers_of(conn, sym))
                relation_subset = types & {"supplier", "customer", "substitute", "complement"}
                if relation_subset:
                    edges.extend(_relations_of(conn, sym, relation_types=relation_subset))

                for edge in edges:
                    target = edge.to_symbol
                    new_pol = pol_in * edge.polarity
                    new_strength = str_in * edge.strength

                    # Annotate the edge with the polarity AT THIS HOP for the
                    # consumer's "why" trace.
                    annotated_edge = Edge(
                        from_symbol=edge.from_symbol,
                        to_symbol=edge.to_symbol,
                        edge_type=edge.edge_type,
                        strength=edge.strength,
                        polarity=edge.polarity,
                        confidence=edge.confidence,
                        source=edge.source,
                        evidence=edge.evidence,
                    )

                    if target not in results:
                        results[target] = GraphResult(
                            symbol=target,
                            hop=hop,
                            incoming_edges=[annotated_edge],
                            cumulative_polarity=new_pol,
                            cumulative_strength=new_strength,
                        )
                        next_frontier.append((target, new_pol, new_strength))
                    else:
                        existing = results[target]
                        # Don't append edges INTO a seed node — the seed is the
                        # starting point, not a discovery. Keeps the "why" trace
                        # clean for UI consumers.
                        if existing.hop == 0:
                            continue
                        existing.incoming_edges.append(annotated_edge)
                        # Keep the strongest path: highest |polarity|*strength
                        if abs(new_pol) * new_strength > abs(existing.cumulative_polarity) * existing.cumulative_strength:
                            existing.cumulative_polarity = new_pol
                            existing.cumulative_strength = new_strength

            # Deterministic next-layer order
            frontier = sorted(set(next_frontier), key=lambda t: t[0])
            if not frontier:
                break

        return results
    finally:
        if own_conn:
            conn.close()


def neighborhood(
    symbol: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, list[Edge]]:
    """Convenience: 1-hop expansion split by direction.

    Returns:
        {
            "suppliers":    [Edge ...],   # things `symbol` depends on (upstream)
            "customers":    [Edge ...],   # things that buy from `symbol` (downstream)
            "peers":        [Edge ...],
            "substitutes":  [Edge ...],
            "complements":  [Edge ...],
        }
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    sym = symbol.upper()
    try:
        peers = _peers_of(conn, sym)
        rels = _relations_of(conn, sym)
        return {
            "suppliers":   [e for e in rels if e.edge_type == "supplier"],
            "customers":   [e for e in rels if e.edge_type == "customer"],
            "peers":       peers,
            "substitutes": [e for e in rels if e.edge_type == "substitute"],
            "complements": [e for e in rels if e.edge_type == "complement"],
        }
    finally:
        if own_conn:
            conn.close()
