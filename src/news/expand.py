"""Industry-impact → stocks fan-out with tier-aware ranking.

Takes the `IndustryImpact` list from the aggregator and expands each industry
to its member stocks using `stock_industry`. Returns a flat ranked list with
provenance ("why" trace) per result.

Composite ranking factor for the prototype (no graph traversal yet — that's
Phase 4):

    score = abs(industry_polarity)
          * industry_strength
          * stock_industry_weight        # multi-tag weight (1.0 for single-tag)
          * tier_weight                  # A=1.0 B=0.7 C=0.4 D=0.1

Tier weight ensures Tier-A names rise above an equally-tagged Tier-D name.
The polarity sign is preserved so callers can render bullish vs bearish.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from src.news.aggregate import IndustryImpact, StockImpact
from src.utils.db import get_connection, init_db


TIER_WEIGHT: dict[str, float] = {"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.1}


@dataclass
class StockResult:
    """One stock that surfaced from the fan-out, with ranking and trace."""
    symbol: str
    name: str | None
    tier: str
    sector: str | None
    industry_code: str | None
    polarity: float            # -1..1; sign matters for UI bullish/bearish render
    strength: float            # 0..1 conviction
    composite_score: float     # final ranking key (always >= 0)
    contributing_keywords: list[str] = field(default_factory=list)
    contributing_industries: list[str] = field(default_factory=list)
    direct_target: bool = False    # True if a keyword named this stock explicitly


@dataclass
class NewsImpactResult:
    """Structured result of running a headline end-to-end."""
    stocks: list[StockResult]
    industries: list[IndustryImpact]
    matched_keywords: list[str]
    matched_countries: list[str]
    matched_symbols: list[str]
    negated_keywords: list[str]


# ── DB lookups ────────────────────────────────────────────────────


def _stocks_in_industry(
    conn: sqlite3.Connection,
    industry_code: str,
) -> list[dict]:
    """Return stocks tagged with this industry, with tier and weight."""
    rows = conn.execute(
        """
        SELECT u.symbol, u.name, u.tier, i.sector, si.weight, si.is_primary
        FROM stock_industry si
        JOIN stocks_universe u ON u.symbol = si.symbol
        LEFT JOIN industries i ON i.code = si.industry_code
        WHERE si.industry_code = ?
        ORDER BY si.is_primary DESC, si.weight DESC
        """,
        (industry_code,),
    ).fetchall()
    return [dict(r) for r in rows]


def _stock_lookup(conn: sqlite3.Connection, symbol: str) -> dict | None:
    """Resolve a directly-named symbol into universe metadata + primary industry."""
    row = conn.execute(
        """
        SELECT u.symbol, u.name, u.tier, i.code AS industry_code, i.sector
        FROM stocks_universe u
        LEFT JOIN stock_industry si
            ON si.symbol = u.symbol AND si.is_primary = 1
        LEFT JOIN industries i ON i.code = si.industry_code
        WHERE u.symbol = ?
        """,
        (symbol,),
    ).fetchone()
    return dict(row) if row else None


# ── public entry point ───────────────────────────────────────────


def expand(
    industry_impacts: Iterable[IndustryImpact],
    stock_impacts: Iterable[StockImpact],
    *,
    conn: sqlite3.Connection | None = None,
    limit_per_industry: int = 100,
    min_composite: float = 0.05,
) -> NewsImpactResult:
    """Fan industry impacts out to stocks, merge directly-targeted stocks, rank.

    Parameters
    ----------
    industry_impacts : list from `aggregate.aggregate(...).industries`
    stock_impacts    : list from `aggregate.aggregate(...).stocks` (direct-name targets)
    limit_per_industry : cap on candidates per industry to avoid runaway lists
    min_composite : drop results scoring under this threshold (cleans noise)
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    industry_impacts = list(industry_impacts)
    stock_impacts = list(stock_impacts)

    # Map symbol → accumulating candidate (we may surface the same stock from
    # multiple industries / direct hits and want one row per symbol).
    candidates: dict[str, StockResult] = {}

    try:
        # 1. Fan out per industry
        for ii in industry_impacts:
            members = _stocks_in_industry(conn, ii.industry_code)
            for row in members[:limit_per_industry]:
                tier = row["tier"]
                tier_w = TIER_WEIGHT.get(tier, 0.0)
                # Per-row composite score for THIS industry contribution
                row_score = abs(ii.polarity) * ii.strength * float(row["weight"]) * tier_w

                existing = candidates.get(row["symbol"])
                if existing is None:
                    candidates[row["symbol"]] = StockResult(
                        symbol=row["symbol"],
                        name=row["name"],
                        tier=tier,
                        sector=row["sector"],
                        industry_code=ii.industry_code,
                        polarity=ii.polarity,
                        strength=ii.strength * float(row["weight"]),
                        composite_score=row_score,
                        contributing_keywords=list(ii.contributing_keywords),
                        contributing_industries=[ii.industry_code],
                        direct_target=False,
                    )
                else:
                    # Multiple industries surface the same stock → take the
                    # stronger one; merge keyword lists & industries.
                    if row_score > existing.composite_score:
                        existing.composite_score = row_score
                        existing.polarity = ii.polarity
                        existing.strength = ii.strength * float(row["weight"])
                        existing.industry_code = ii.industry_code
                    existing.contributing_industries.append(ii.industry_code)
                    existing.contributing_keywords = sorted(
                        set(existing.contributing_keywords) | set(ii.contributing_keywords)
                    )

        # 2. Direct-named stocks (from keyword_impact.target_stock)
        for si in stock_impacts:
            meta = _stock_lookup(conn, si.symbol)
            if meta is None:
                # Direct target points to a stock not in our universe — skip.
                continue
            tier = meta["tier"]
            tier_w = TIER_WEIGHT.get(tier, 0.0)
            row_score = abs(si.polarity) * si.strength * tier_w

            existing = candidates.get(si.symbol)
            if existing is None or row_score > existing.composite_score:
                candidates[si.symbol] = StockResult(
                    symbol=si.symbol,
                    name=meta["name"],
                    tier=tier,
                    sector=meta["sector"],
                    industry_code=meta["industry_code"],
                    polarity=si.polarity,
                    strength=si.strength,
                    composite_score=row_score,
                    contributing_keywords=list(si.contributing_keywords),
                    contributing_industries=existing.contributing_industries if existing else [],
                    direct_target=True,
                )
            else:
                existing.contributing_keywords = sorted(
                    set(existing.contributing_keywords) | set(si.contributing_keywords)
                )
                existing.direct_target = True

    finally:
        if own_conn:
            conn.close()

    # 3. Filter, sort, return
    results = [
        s for s in candidates.values()
        if s.composite_score >= min_composite
    ]
    # Order: direct-targets first (most explicit signal), then composite desc
    results.sort(key=lambda s: (-int(s.direct_target), -s.composite_score))

    return NewsImpactResult(
        stocks=results,
        industries=industry_impacts,
        matched_keywords=[],
        matched_countries=[],
        matched_symbols=[],
        negated_keywords=[],
    )
