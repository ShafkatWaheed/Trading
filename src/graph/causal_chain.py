"""Commodity-aware causal-chain traversal (Phase 6).

This module is the bridge between commodity-price events (the trigger) and
the stocks that respond. It walks the graph:

    1. matched commodity   →  stocks with stock_commodity_exposure on it
    2. those stocks        →  via stock_relations.supplier / customer / complement
                              up to N hops (re-using src.graph.traverse)
    3. cost-passthrough chains: an input squeeze flips to revenue tailwind
       for the producer of the squeezed input. Example:
            gas price ↑ → CF feedstock cost ↑ →
            urea supply tightens → CF revenue ↑ (via output exposure)

Key concepts:

    CausalHit       — one stock that responds to the commodity event with a
                      polarity (+ → bullish, - → bearish), a magnitude (0..1),
                      and a chain (list of human-readable steps for the UI).

The commodity layer is the "first hop"; the stock_relations + stock_peers
layers handle subsequent hops via the existing `traverse.expand` helper.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from src.graph import traverse
from src.utils.db import get_connection, init_db


@dataclass
class CommodityExposure:
    """One row from `stock_commodity_exposure` joined with commodity name."""
    symbol: str
    commodity_code: str
    role: str            # 'input' | 'output' | 'hedge'
    polarity: float      # -1..+1
    elasticity: float    # 0..1


@dataclass
class CausalHit:
    """One stock surfaced by a commodity event."""
    symbol: str
    polarity: float                # final sign (cumulative through chain)
    magnitude: float               # 0..1 strength
    chain: list[str] = field(default_factory=list)
    role: str | None = None        # 'input' | 'output' for direct hits
    commodity_code: str | None = None


# ── primary lookup: commodity → exposed stocks ────────────────────


def stocks_exposed_to(
    commodity_code: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[CommodityExposure]:
    """All stocks tagged with this commodity (any role)."""
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT symbol, commodity_code, role, polarity, elasticity
            FROM stock_commodity_exposure
            WHERE commodity_code = ?
            """,
            (commodity_code,),
        ).fetchall()
        return [
            CommodityExposure(
                symbol=r["symbol"],
                commodity_code=r["commodity_code"],
                role=r["role"],
                polarity=float(r["polarity"]),
                elasticity=float(r["elasticity"]),
            )
            for r in rows
        ]
    finally:
        if own_conn:
            conn.close()


# ── chain composition ─────────────────────────────────────────────


def _chain_step(commodity: str, direction: str, exposure: CommodityExposure) -> str:
    """Human-readable step for the UI trace."""
    arrow = "↑" if direction == "up" else "↓"
    role_label = "input cost" if exposure.role == "input" else "output revenue"
    sign = "+" if exposure.polarity > 0 else "-"
    return (
        f"{commodity} {arrow} → {exposure.symbol} {role_label} "
        f"({sign}{exposure.elasticity:.2f})"
    )


def trace_from_commodity(
    commodity_code: str,
    *,
    direction: str = "up",
    expand_hops: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, CausalHit]:
    """Given a commodity-price move (default: 'up'), surface affected stocks.

    Args:
        commodity_code: lowercase code from `commodities` (e.g. 'natural_gas').
        direction: 'up' or 'down'.
        expand_hops: 0 = direct exposures only; 1 = also walk supplier/customer
                     /complement edges from the direct hits; 2 = two hops.
                     (Use sparingly; magnitudes decay quickly.)

    Returns dict[symbol → CausalHit].
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        direct_exposures = stocks_exposed_to(commodity_code, conn=conn)
        if not direct_exposures:
            return {}

        # Direction multiplier: up = +1, down = -1 (flips polarity of all roles).
        dir_mult = 1.0 if direction == "up" else -1.0

        # 1) Direct hits: cumulative polarity = role.polarity × dir_mult,
        #    magnitude = elasticity. Output stocks benefit from price up; input
        #    stocks suffer.
        hits: dict[str, CausalHit] = {}
        for ce in direct_exposures:
            cumulative_pol = ce.polarity * dir_mult
            magnitude = ce.elasticity
            chain = [_chain_step(commodity_code, direction, ce)]
            existing = hits.get(ce.symbol)
            if existing is None or magnitude > existing.magnitude:
                hits[ce.symbol] = CausalHit(
                    symbol=ce.symbol,
                    polarity=cumulative_pol,
                    magnitude=magnitude,
                    chain=chain,
                    role=ce.role,
                    commodity_code=ce.commodity_code,
                )
            else:
                existing.chain.extend(chain)

        # 2) Cost-passthrough flip: when a stock has BOTH input exposure to
        #    commodity X AND output exposure to a different commodity Y, an
        #    input squeeze typically tightens supply of Y → CF revenue lift.
        #    Detect: if the same symbol appears with role='output' on another
        #    commodity, model the chain as a positive "supply tightness flip".
        for ce in direct_exposures:
            if ce.role != "input":
                continue
            outputs = conn.execute(
                """
                SELECT commodity_code, polarity, elasticity
                FROM stock_commodity_exposure
                WHERE symbol = ? AND role = 'output'
                """,
                (ce.symbol,),
            ).fetchall()
            if not outputs:
                continue
            # Flip the input-pressure into output revenue (gas crisis → CF urea ↑)
            for out_row in outputs:
                # Flip magnitude is the output elasticity — that's the side
                # the revenue story tracks. The input pressure is what TRIGGERS
                # the supply tightness, but the magnitude of the response is
                # determined by how much the output price passes through.
                flip_strength = float(out_row["elasticity"])
                # Take the output direction (typically +1) × dir_mult
                flip_polarity = float(out_row["polarity"]) * dir_mult
                if abs(flip_polarity) * flip_strength > abs(hits[ce.symbol].polarity) * hits[ce.symbol].magnitude:
                    hits[ce.symbol].polarity = flip_polarity
                    hits[ce.symbol].magnitude = flip_strength
                    hits[ce.symbol].chain.append(
                        f"{commodity_code} ↑ feedstock squeeze → "
                        f"{out_row['commodity_code']} supply tightens → "
                        f"{ce.symbol} output ({flip_polarity:+.2f})"
                    )

        # 3) Optional 1-N hop graph expansion via supplier/customer/complement
        #    AND peer (peer co-movement is a real signal — when XOM is bullish,
        #    cross-sector peers like NEE that aren't directly commodity-exposed
        #    can still co-move). The polarity carried into the graph is each
        #    direct hit's cumulative.
        if expand_hops > 0:
            seed_polarity = {sym: h.polarity for sym, h in hits.items()}
            expanded = traverse.expand(
                seed_polarity.keys(),
                hops=expand_hops,
                edge_types=["supplier", "customer", "complement", "peer"],
                starting_polarity=seed_polarity,
                conn=conn,
            )
            for sym, gr in expanded.items():
                if sym in hits or gr.hop == 0:
                    continue
                # Only retain genuinely-discovered hops, not seed nodes.
                # Magnitude decays per hop (0.6, 0.36, ...).
                hop_decay = 0.6 ** gr.hop
                magnitude = gr.cumulative_strength * hop_decay
                if magnitude < 0.05:
                    continue
                hits[sym] = CausalHit(
                    symbol=sym,
                    polarity=gr.cumulative_polarity,
                    magnitude=magnitude,
                    chain=[
                        f"  via {e.from_symbol} →{e.edge_type}→ {e.to_symbol}"
                        for e in gr.incoming_edges
                    ],
                    role=None,
                    commodity_code=None,
                )

        return hits
    finally:
        if own_conn:
            conn.close()


# ── batched: multiple commodities → merged hits ──────────────────


def trace_from_commodities(
    moves: Iterable[tuple[str, str]],
    *,
    expand_hops: int = 1,
) -> dict[str, CausalHit]:
    """Run multiple commodity-direction pairs and merge into one ranked dict.

    Args:
        moves: iterable of (commodity_code, direction) tuples.
        expand_hops: same as `trace_from_commodity`.

    Returns merged hits (one entry per symbol; the strongest contribution wins).
    """
    merged: dict[str, CausalHit] = {}
    for code, direction in moves:
        hits = trace_from_commodity(code, direction=direction, expand_hops=expand_hops)
        for sym, h in hits.items():
            existing = merged.get(sym)
            if existing is None:
                merged[sym] = h
                continue
            # Multi-commodity confluence: if the new hit has the same polarity
            # sign, boost magnitude (capped at 1.0). If opposite sign, take the
            # stronger one.
            if (existing.polarity >= 0) == (h.polarity >= 0):
                # Same-sign: diminishing-returns merge
                merged_mag = 1.0 - (1.0 - existing.magnitude) * (1.0 - h.magnitude)
                existing.magnitude = merged_mag
                existing.chain.extend(h.chain)
            else:
                # Opposite-sign: keep stronger; chains both kept for the trace
                if h.magnitude > existing.magnitude:
                    merged[sym] = h
                    merged[sym].chain = h.chain + existing.chain
                else:
                    existing.chain.extend(h.chain)
    return merged


# ── ranked output for UI ─────────────────────────────────────────


def rank_hits(hits: dict[str, CausalHit]) -> list[CausalHit]:
    """Sort hits by |polarity| × magnitude descending."""
    return sorted(hits.values(), key=lambda h: -abs(h.polarity) * h.magnitude)
