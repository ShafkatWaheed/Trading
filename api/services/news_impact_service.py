"""News-impact orchestrator — compose tokenize → aggregate → expand → graph → causal.

Pulls keyword_impact rows from the DB on demand (cached in process for a
short window), feeds them through the news engine, and:
    * Phase 4: expands top hits 1 hop via supply-chain + peer graph
    * Phase 6: fires commodity causal-chain traversal for any commodity-keyword
      matches (e.g. "oil refinery" / "gas crisis" / "uranium") → surfaces
      cross-sector beneficiaries via stock_commodity_exposure

Combined, the result list includes:
    * Direct keyword/industry hits  (Phase 2)
    * 1-hop supply-chain expansion  (Phase 4)
    * Commodity causal-chain hits   (Phase 6)
"""

from __future__ import annotations

import time

from src.graph import causal_chain, rank as graph_rank
from src.graph.traverse import expand as graph_expand
from src.news.aggregate import KeywordImpactRow, aggregate
from src.news.expand import NewsImpactResult, StockResult, expand
from src.news.tokenize import extract_matches
from src.utils.db import get_connection, init_db


# Only expand via graph from stocks that scored above this — avoids fan-out
# from weak/marginal hits.
EXPANSION_SCORE_FLOOR: float = 0.20

# Edge types used for auto-expansion. Substitutes are excluded because their
# polarity flip can confuse users seeing the same headline from multiple angles.
EXPANSION_EDGE_TYPES: tuple[str, ...] = ("peer", "supplier", "customer", "complement")


# ── Phase 6: commodity-keyword → commodity-code mapping ────────────
#
# Maps matched keywords to (commodity_code, default_direction) so the
# causal chain knows which commodity event to trace. The default direction
# is "up" because most news triggers (e.g. "oil refinery hit") imply price
# pressure upward; a negated keyword flips it to "down".
KEYWORD_COMMODITY_MAP: dict[str, tuple[str, str]] = {
    # Energy
    "oil":              ("crude_oil",   "up"),
    "crude":            ("crude_oil",   "up"),
    "oil refinery":     ("crude_oil",   "up"),
    "opec":             ("crude_oil",   "up"),
    "output cut":       ("crude_oil",   "up"),
    "gas":              ("natural_gas", "up"),
    "natural gas":      ("natural_gas", "up"),
    "lng":              ("natural_gas", "up"),
    "fertilizer":       ("natural_gas", "up"),  # via gas-feedstock squeeze
    "oilfield":         ("crude_oil",   "up"),
    # Metals / mining
    "copper":           ("copper",      "up"),
    "copper supercycle":("copper",      "up"),
    "gold":             ("gold",        "up"),
    "silver":           ("silver",      "up"),
    "uranium":          ("uranium",     "up"),
    "nuclear":          ("uranium",     "up"),
    "lithium":          ("lithium",     "up"),
    "rare earths":      ("rare_earths", "up"),
    # Agriculture
    "wheat":            ("wheat",       "up"),
    "corn":             ("corn",        "up"),
    "cocoa":            ("cocoa",       "up"),
    "coffee":           ("coffee",      "up"),
    "sugar":            ("sugar",       "up"),
    "cotton":           ("cotton",      "up"),
    "lumber":           ("lumber",      "up"),
}

# Process-local cache for keyword_impact + universe symbols, refreshed every N seconds
_CACHE_TTL_SEC = 60
_cache: dict[str, object] = {"loaded_at": 0.0}


def _refresh_cache_if_stale() -> None:
    now = time.time()
    if now - float(_cache.get("loaded_at", 0.0)) < _CACHE_TTL_SEC and "keywords" in _cache:
        return

    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT keyword, industry_code, target_stock, polarity, weight, domain "
            "FROM keyword_impact"
        ).fetchall()
        impact_rows = [
            KeywordImpactRow(
                keyword=r["keyword"],
                industry_code=r["industry_code"],
                target_stock=r["target_stock"],
                polarity=float(r["polarity"]),
                weight=float(r["weight"]),
                domain=r["domain"],
            )
            for r in rows
        ]
        symbols = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        }
    finally:
        conn.close()

    _cache["impact_rows"] = impact_rows
    _cache["keywords"] = {r.keyword for r in impact_rows}
    _cache["symbols"] = symbols
    _cache["loaded_at"] = now


def analyze_news(
    text: str,
    *,
    expand_graph: bool = True,
    expand_causal: bool = True,
) -> dict:
    """Run the news engine end-to-end and return a JSON-serializable result.

    Pipeline: tokenize → aggregate (keyword → industry) → expand (industry →
    stocks) → [Phase 4] graph 1-hop expansion → [Phase 6] commodity causal chain.

    `expand_graph=False` skips Phase 4 expansion.
    `expand_causal=False` skips Phase 6 commodity tracing.
    """
    _refresh_cache_if_stale()
    impact_rows = _cache["impact_rows"]
    keywords = _cache["keywords"]
    symbols = _cache["symbols"]

    # Phase 6: also tokenize commodity keywords (they may not be in
    # keyword_impact). The aggregator will produce no industry hit for
    # commodity-only keywords (no impact_rows match), but they appear in
    # matched_keywords so the causal-chain layer can read them.
    keyword_set = set(keywords) | set(KEYWORD_COMMODITY_MAP.keys())

    matches = extract_matches(text, keywords=keyword_set, universe=symbols)
    agg = aggregate(matches, impact_rows)
    expanded = expand(agg.industries, agg.stocks)

    if expand_graph and expanded.stocks:
        _attach_graph_expansion(expanded)

    if expand_causal:
        _attach_causal_chain_hits(
            expanded,
            matched_keywords=agg.matched_keywords,
            negated_keywords=set(agg.negated_keywords),
        )

    expanded.matched_keywords = agg.matched_keywords
    expanded.matched_countries = agg.matched_countries
    expanded.matched_symbols = agg.matched_symbols
    expanded.negated_keywords = agg.negated_keywords

    return _to_json(expanded)


def _attach_graph_expansion(result: NewsImpactResult) -> None:
    """Expand high-confidence hits 1 hop via the graph and merge new stocks
    into the result's stocks list with hop metadata.

    Strategy:
      1. Take stocks scoring above EXPANSION_SCORE_FLOOR as seeds
      2. Carry each seed's polarity into a 1-hop graph traversal
      3. For newly-discovered symbols, score with `graph.rank` and append
      4. Existing stocks (already in `result.stocks`) keep their original score —
         we don't replace direct hits with graph-derived ones.
    """
    # Seeds and their polarity
    seeds: dict[str, float] = {}
    for s in result.stocks:
        if s.composite_score >= EXPANSION_SCORE_FLOOR:
            seeds[s.symbol] = s.polarity
    if not seeds:
        return

    # Walk the graph 1 hop
    graph_results = graph_expand(
        seeds.keys(),
        hops=1,
        edge_types=EXPANSION_EDGE_TYPES,
        starting_polarity=seeds,
    )

    # Need tier + name + sector for the newly-discovered symbols
    new_symbols = {s for s in graph_results if s not in {x.symbol for x in result.stocks}}
    if not new_symbols:
        return
    init_db()
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(new_symbols))
        rows = conn.execute(
            f"""
            SELECT u.symbol, u.name, u.tier, i.code AS industry_code, i.sector
            FROM stocks_universe u
            LEFT JOIN stock_industry si
                ON si.symbol = u.symbol AND si.is_primary = 1
            LEFT JOIN industries i ON i.code = si.industry_code
            WHERE u.symbol IN ({placeholders})
            """,
            list(new_symbols),
        ).fetchall()
        meta = {r["symbol"]: dict(r) for r in rows}
    finally:
        conn.close()

    tiers = {sym: m["tier"] for sym, m in meta.items()}
    ranked = graph_rank.rank(
        {sym: graph_results[sym] for sym in new_symbols if sym in tiers},
        tiers=tiers,
    )

    # Merge: append the new stocks with hop metadata
    from src.news.expand import StockResult
    for r in ranked:
        if r.composite_score < 0.05:
            continue
        m = meta[r.symbol]
        # Keywords that surfaced this stock indirectly: aggregate from the
        # incoming-edge `from_symbol`s' keywords. Useful for the "why" trace.
        graph_origins = sorted({e.from_symbol for e in graph_results[r.symbol].incoming_edges})
        result.stocks.append(StockResult(
            symbol=r.symbol,
            name=m["name"],
            tier=r.tier or m["tier"],
            sector=m["sector"],
            industry_code=m["industry_code"],
            polarity=r.polarity,
            strength=r.strength,
            composite_score=r.composite_score,
            contributing_keywords=[],          # not from a keyword — from graph
            contributing_industries=[f"via:{o}" for o in graph_origins],
            direct_target=False,
        ))

    # Re-sort: direct_target first, then composite desc
    result.stocks.sort(key=lambda s: (-int(s.direct_target), -s.composite_score))


def _attach_causal_chain_hits(
    result: NewsImpactResult,
    *,
    matched_keywords: list[str],
    negated_keywords: set[str],
) -> None:
    """Phase 6: detect commodity-keyword matches and run the causal chain.

    For each matched keyword that maps to a commodity, fire trace_from_commodity
    in the appropriate direction (negation flips it). Merge results into the
    main `result.stocks` list, marking new entries with a 'causal:<commodity>'
    tag in `contributing_industries` so the UI can render the chain.
    """
    moves: list[tuple[str, str]] = []
    triggered_by: dict[str, list[str]] = {}  # commodity → list of keyword text
    for kw in matched_keywords:
        if kw not in KEYWORD_COMMODITY_MAP:
            continue
        commodity, default_direction = KEYWORD_COMMODITY_MAP[kw]
        # Negation flips direction
        direction = default_direction
        if kw in negated_keywords:
            direction = "down" if direction == "up" else "up"
        moves.append((commodity, direction))
        triggered_by.setdefault(commodity, []).append(kw)

    if not moves:
        return

    # Dedupe (same commodity, same direction) — simplest: take the strongest hit
    # per (commodity, direction) but pass merging to causal_chain.
    causal_hits = causal_chain.trace_from_commodities(moves, expand_hops=1)
    if not causal_hits:
        return

    # Build a lookup of existing stocks for merge logic
    by_symbol = {s.symbol: s for s in result.stocks}

    init_db()
    conn = get_connection()
    try:
        # Need name + tier + sector + industry for newly-discovered stocks
        new_syms = {sym for sym in causal_hits if sym not in by_symbol}
        meta = {}
        if new_syms:
            placeholders = ",".join("?" * len(new_syms))
            rows = conn.execute(
                f"""
                SELECT u.symbol, u.name, u.tier, i.code AS industry_code, i.sector
                FROM stocks_universe u
                LEFT JOIN stock_industry si
                    ON si.symbol = u.symbol AND si.is_primary = 1
                LEFT JOIN industries i ON i.code = si.industry_code
                WHERE u.symbol IN ({placeholders})
                """,
                list(new_syms),
            ).fetchall()
            meta = {r["symbol"]: dict(r) for r in rows}
    finally:
        conn.close()

    TIER_W = {"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.1}

    for sym, hit in causal_hits.items():
        # Build a "via:commodity" trace string for the contributing_industries list
        commodity_tag = (
            f"via:{hit.commodity_code}" if hit.commodity_code else "causal_chain"
        )

        existing = by_symbol.get(sym)
        if existing is not None:
            # Stock already in result list — annotate with causal info
            if commodity_tag not in existing.contributing_industries:
                existing.contributing_industries.append(commodity_tag)
            # If the causal hit suggests a stronger composite, bump it
            tier_w = TIER_W.get(existing.tier, 0.0) if existing.tier else 0.0
            causal_composite = abs(hit.polarity) * hit.magnitude * tier_w
            if causal_composite > existing.composite_score:
                existing.composite_score = causal_composite
            continue

        # New stock from causal chain — needs metadata
        m = meta.get(sym)
        if m is None or m["tier"] is None:
            continue
        tier = m["tier"]
        tier_w = TIER_W.get(tier, 0.0)
        composite = abs(hit.polarity) * hit.magnitude * tier_w
        if composite < 0.05:
            continue

        result.stocks.append(StockResult(
            symbol=sym,
            name=m["name"],
            tier=tier,
            sector=m["sector"],
            industry_code=m["industry_code"],
            polarity=hit.polarity,
            strength=hit.magnitude,
            composite_score=composite,
            contributing_keywords=[],
            contributing_industries=[commodity_tag],
            direct_target=False,
        ))

    # Re-sort by composite desc, direct_target first
    result.stocks.sort(key=lambda s: (-int(s.direct_target), -s.composite_score))


def _to_json(r: NewsImpactResult) -> dict:
    """Flatten dataclasses into plain dicts for the API layer."""
    return {
        "stocks": [
            {
                "symbol": s.symbol,
                "name": s.name,
                "tier": s.tier,
                "sector": s.sector,
                "industry_code": s.industry_code,
                "polarity": s.polarity,
                "strength": s.strength,
                "composite_score": s.composite_score,
                "contributing_keywords": s.contributing_keywords,
                "contributing_industries": s.contributing_industries,
                "direct_target": s.direct_target,
            }
            for s in r.stocks
        ],
        "industries": [
            {
                "industry_code": i.industry_code,
                "polarity": i.polarity,
                "strength": i.strength,
                "contributing_keywords": i.contributing_keywords,
                "contributing_domains": i.contributing_domains,
            }
            for i in r.industries
        ],
        "matched_keywords": r.matched_keywords,
        "matched_countries": r.matched_countries,
        "matched_symbols": r.matched_symbols,
        "negated_keywords": r.negated_keywords,
    }
