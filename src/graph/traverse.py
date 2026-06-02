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


def _peers_of(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    as_of: str | None = None,
) -> list[Edge]:
    """All peer edges from `symbol` OR its share-class siblings.

    Dual-class tickers (GOOG/GOOGL, BRK.A/BRK.B, ...) have edges historically
    seeded against whichever class was canonical at seeding time. We expand
    the query set to include siblings, then filter out edges that point AT a
    sibling (your other share class isn't a "peer" — it's you).

    `as_of` (ISO 8601 date): point-in-time filter — see `_relations_of` for
    the rule. Peer edges with NULL effective_from / _to pass any as_of.
    """
    from src.graph.share_classes import equivalents

    syms = equivalents(symbol)
    sym_set = set(syms)            # queried sym + all siblings
    placeholders = ",".join("?" * len(syms))

    if as_of is None:
        sql = f"""
            SELECT to_symbol, similarity, source, confidence, evidence
            FROM stock_peers
            WHERE from_symbol IN ({placeholders})
        """
        params: tuple = tuple(syms)
    else:
        sql = f"""
            SELECT to_symbol, similarity, source, confidence, evidence
            FROM stock_peers
            WHERE from_symbol IN ({placeholders})
              AND (effective_from IS NULL OR effective_from <= ?)
              AND (effective_to IS NULL OR effective_to > ?)
        """
        params = (*syms, as_of, as_of)

    rows = conn.execute(sql, params).fetchall()

    # Dedup by to_symbol (in case both share classes have edges to the same
    # peer) — keep the highest similarity. Also drop edges pointing AT the
    # queried sym OR a sibling (sibling tickers aren't peers, they're the
    # same business; the queried sym shouldn't peer-list itself).
    best_by_to: dict[str, dict] = {}
    for r in rows:
        to_sym = r["to_symbol"]
        if to_sym in sym_set:
            continue
        sim = float(r["similarity"])
        existing = best_by_to.get(to_sym)
        if existing is None or sim > existing["similarity"]:
            best_by_to[to_sym] = {
                "similarity": sim,
                "source": r["source"],
                "confidence": r["confidence"],
                "evidence": r["evidence"],
            }

    return [
        Edge(
            from_symbol=symbol,            # always report from caller's perspective
            to_symbol=to_sym,
            edge_type="peer",
            strength=row["similarity"],
            polarity=1.0,                  # peers always positive at the edge level
            confidence=row["confidence"],
            source=row["source"],
            evidence=row["evidence"],
        )
        for to_sym, row in best_by_to.items()
    ]


# Flip table for asymmetric edge types. When a row (A→B, type=X) is read from
# B's perspective, the edge type becomes `_FLIP[X]`. Substitute and complement
# are symmetric and pass through unchanged.
_FLIP: dict[str, str] = {"supplier": "customer", "customer": "supplier"}


def _flip(edge_type: str) -> str:
    """Return the edge type from the opposite endpoint's perspective."""
    return _FLIP.get(edge_type, edge_type)


def _relations_of(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    relation_types: Iterable[str] | None = None,
    as_of: str | None = None,
) -> list[Edge]:
    """All stock_relations edges touching `symbol`, filtered by type.

    Edges are returned from `symbol`'s perspective:
      * `from_symbol` is always `symbol`
      * `to_symbol` is the neighbor
      * `edge_type` is flipped for inverse-direction rows (supplier↔customer);
        substitute/complement are symmetric and pass through unchanged

    This makes traversal symmetric over a one-row-per-relationship storage:
    we don't need to write mirror rows, the reader sees both directions.

    `as_of` (ISO 8601 date): point-in-time filter. When set, an edge is
    returned only if it was in effect at that date — i.e.
        (effective_from IS NULL OR effective_from <= as_of)
        AND (effective_to IS NULL OR effective_to > as_of)
    NULL bounds mean "always valid" / "still in effect" — the default for
    every hand-seeded edge. Required by CLAUDE.md's no-lookahead rule.
    """
    # When the caller filters by edge_type, we must also pull rows whose stored
    # type flips to the requested one. e.g. "give me suppliers of X" requires
    # both (from_symbol=X, type=supplier) AND (to_symbol=X, type=customer).
    #
    # Share-class expansion: dual-class tickers (GOOG/GOOGL, BRK.A/BRK.B, ...)
    # have edges seeded against whichever class was canonical at seeding time.
    # Pull rows from either side of the sibling set, then filter sibling-pointing
    # rows out of the final result (your other share class isn't a "neighbor").
    from src.graph.share_classes import equivalents, siblings as _siblings
    syms = equivalents(symbol)
    sibling_set = _siblings(symbol)
    sym_placeholders = ",".join("?" * len(syms))

    temporal_clause = ""
    temporal_params: list = []
    if as_of is not None:
        temporal_clause = (
            " AND (effective_from IS NULL OR effective_from <= ?)"
            " AND (effective_to IS NULL OR effective_to > ?)"
        )
        temporal_params = [as_of, as_of]

    if relation_types:
        forward_types = {t for t in relation_types}
        inverse_types = {_flip(t) for t in relation_types}
        types_to_match = forward_types | inverse_types
        ph = ",".join("?" * len(types_to_match))
        sql = f"""
            SELECT from_symbol, to_symbol, relation_type, strength, polarity, evidence
            FROM stock_relations
            WHERE (from_symbol IN ({sym_placeholders}) OR to_symbol IN ({sym_placeholders}))
              AND relation_type IN ({ph})
              {temporal_clause}
        """
        params = [*syms, *syms, *types_to_match, *temporal_params]
    else:
        sql = f"""
            SELECT from_symbol, to_symbol, relation_type, strength, polarity, evidence
            FROM stock_relations
            WHERE (from_symbol IN ({sym_placeholders}) OR to_symbol IN ({sym_placeholders}))
              {temporal_clause}
        """
        params = [*syms, *syms, *temporal_params]

    rows = conn.execute(sql, params).fetchall()

    # Dedup on (neighbor, edge_type_from_my_view). Forward rows take priority
    # over the inverse — if both directions are seeded for the same pair, we
    # keep the explicit one to honor whatever evidence it carries.
    edges_by_key: dict[tuple[str, str], Edge] = {}
    inverse_pending: list[Edge] = []

    sym_set = set(syms)  # all tickers belonging to the queried company
    for r in rows:
        # Skip edges where the OTHER endpoint is a sibling — those are the
        # "same business as me" edges (e.g. GOOG↔GOOGL) and shouldn't appear
        # in a neighborhood. The non-sibling rows are the real neighbors.
        if r["from_symbol"] in sym_set and r["to_symbol"] in sym_set:
            continue

        if r["from_symbol"] in sym_set:
            # Forward edge — type as stored, other endpoint is the neighbor
            neighbor = r["to_symbol"]
            if neighbor in sibling_set:
                continue
            edge = Edge(
                from_symbol=symbol,        # report from caller's perspective
                to_symbol=neighbor,
                edge_type=r["relation_type"],
                strength=float(r["strength"]),
                polarity=float(r["polarity"]),
                confidence="high",
                source="stock_relations",
                evidence=r["evidence"],
            )
            edges_by_key[(edge.to_symbol, edge.edge_type)] = edge
        else:
            # Inverse edge — to_symbol is one of ours, from_symbol is the neighbor.
            # Flip the type (supplier↔customer; substitute/complement stay).
            neighbor = r["from_symbol"]
            if neighbor in sibling_set:
                continue
            flipped_type = _flip(r["relation_type"])
            edge = Edge(
                from_symbol=symbol,
                to_symbol=neighbor,
                edge_type=flipped_type,
                strength=float(r["strength"]),
                polarity=float(r["polarity"]),
                confidence="high",
                source="stock_relations",
                evidence=r["evidence"],
            )
            inverse_pending.append(edge)

    # Apply inverse only if a forward edge for the same (neighbor, type) isn't already present.
    for edge in inverse_pending:
        key = (edge.to_symbol, edge.edge_type)
        if key not in edges_by_key:
            edges_by_key[key] = edge

    # If the caller filtered, drop edges that ended up as types they didn't ask for.
    if relation_types:
        wanted = {t for t in relation_types}
        return [e for e in edges_by_key.values() if e.edge_type in wanted]
    return list(edges_by_key.values())


# ── public expansion ────────────────────────────────────────────


def expand(
    seed: Iterable[str],
    *,
    hops: int = 1,
    edge_types: Iterable[str] | None = None,
    starting_polarity: dict[str, float] | None = None,
    as_of: str | None = None,
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
        as_of: ISO 8601 date — point-in-time filter. Applies to BOTH peer
            edges and relation edges. NULL effective_from/_to bounds mean
            "always valid" and pass any as_of. Required by CLAUDE.md
            no-lookahead rule.

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
                    edges.extend(_peers_of(conn, sym, as_of=as_of))
                relation_subset = types & {"supplier", "customer", "substitute", "complement"}
                if relation_subset:
                    edges.extend(_relations_of(conn, sym, relation_types=relation_subset, as_of=as_of))

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
    as_of: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, list[Edge]]:
    """Convenience: 1-hop expansion split by direction.

    `as_of` (ISO 8601 date) filters BOTH peer and relation edges to those
    in effect at that date — see `_relations_of` for the rule. NULL bounds
    pass any as_of (the default for all hand-seeded edges).

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
        peers = _peers_of(conn, sym, as_of=as_of)
        rels = _relations_of(conn, sym, as_of=as_of)
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
