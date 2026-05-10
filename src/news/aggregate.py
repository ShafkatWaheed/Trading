"""Aggregate keyword matches into per-industry / per-stock impact scores.

Pipeline:

    [TokenMatch, ...] + keyword_impact rows
        ─► group impact rows by (industry_code | target_stock)
        ─► merge polarities with diminishing-returns sum
        ─► apply negation flips per match
        ─► apply co-occurrence boosts (e.g. "tariff" + "China" → boost domestic-mfg)
        ─► return list of IndustryImpact + StockImpact

Diminishing-returns aggregation: when N independent keyword rows hit the same
industry with the same polarity, the merged score is `1 - prod(1 - w_i * |pol|)`.
This caps at 1.0 so noisy headlines don't blow scores up.

Polarity merge: rows with opposite polarities are merged with sign-aware
addition; the final polarity sign equals the dominant direction's net pull.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from src.news.tokenize import TokenMatch


# Co-occurrence rules: when keywords A and B both appear in the same headline,
# boost the impact for `boost_industry` by `boost`. Used sparingly — explicit
# rules only, no learned model in the prototype.
@dataclass(frozen=True)
class CoOccurrenceRule:
    requires: frozenset[str]              # all keywords in this set must fire
    boost_industry: str                   # the industry to boost
    boost: float                          # 0..1 added to the industry's strength
    polarity: float = 1.0                 # +1 = bullish boost, -1 = bearish


# Hand-curated rules. Extend as needed — minimal set for the prototype.
DEFAULT_CO_OCCURRENCE_RULES: tuple[CoOccurrenceRule, ...] = (
    CoOccurrenceRule(
        requires=frozenset({"tariff", "china"}),
        boost_industry="Steel",
        boost=0.10, polarity=+1.0,
    ),
    CoOccurrenceRule(
        requires=frozenset({"tariff", "china"}),
        boost_industry="Aluminum",
        boost=0.10, polarity=+1.0,
    ),
    CoOccurrenceRule(
        requires=frozenset({"oil", "iran"}),
        boost_industry="Aerospace & Defense",
        boost=0.10, polarity=+1.0,
    ),
    CoOccurrenceRule(
        requires=frozenset({"gas", "europe"}),
        boost_industry="Agricultural Inputs",
        boost=0.15, polarity=+1.0,
    ),
    CoOccurrenceRule(
        requires=frozenset({"AI", "data center"}),
        boost_industry="Utilities—Regulated Electric",
        boost=0.10, polarity=+1.0,
    ),
)


@dataclass(frozen=True)
class KeywordImpactRow:
    """One row from the keyword_impact table — what a keyword does."""
    keyword: str
    industry_code: str | None
    target_stock: str | None
    polarity: float                # -1..1
    weight: float                  # 0..1
    domain: str | None = None


@dataclass
class IndustryImpact:
    """Aggregated effect on one industry from all keyword matches."""
    industry_code: str
    polarity: float                # -1..1, sign = dominant direction
    strength: float                # 0..1, magnitude of conviction
    contributing_keywords: list[str] = field(default_factory=list)
    contributing_domains: list[str] = field(default_factory=list)


@dataclass
class StockImpact:
    """Aggregated effect on a directly-named stock (target_stock matches)."""
    symbol: str
    polarity: float
    strength: float
    contributing_keywords: list[str] = field(default_factory=list)


@dataclass
class AggregateResult:
    industries: list[IndustryImpact]
    stocks: list[StockImpact]
    matched_keywords: list[str]            # for the "why" trace
    matched_countries: list[str]
    matched_symbols: list[str]
    negated_keywords: list[str]            # which matches got polarity-flipped


# ── core merge logic ─────────────────────────────────────────────


def _diminishing_sum(weights: Iterable[float]) -> float:
    """1 - prod(1 - w_i). Combines independent evidence; caps at 1.0."""
    survival = 1.0
    for w in weights:
        survival *= max(0.0, 1.0 - max(0.0, min(1.0, w)))
    return 1.0 - survival


def _merge_directional(
    contributions: list[tuple[float, float]],   # list of (polarity, weight)
) -> tuple[float, float]:
    """Combine multiple (polarity, weight) hits into a single (polarity, strength).

    Approach: split into +/- buckets, diminishing-sum each bucket independently,
    then take net polarity = (pos_strength - neg_strength), strength = max bucket.
    """
    pos_w = [abs(pol) * w for pol, w in contributions if pol > 0]
    neg_w = [abs(pol) * w for pol, w in contributions if pol < 0]
    pos_strength = _diminishing_sum(pos_w)
    neg_strength = _diminishing_sum(neg_w)
    if pos_strength == 0.0 and neg_strength == 0.0:
        return 0.0, 0.0
    net = pos_strength - neg_strength
    # Final polarity: sign of net, magnitude clamped to [0,1]
    direction = 1.0 if net >= 0 else -1.0
    strength = max(pos_strength, neg_strength)
    return direction, strength


# ── public entry point ──────────────────────────────────────────


def aggregate(
    matches: Iterable[TokenMatch],
    impact_rows: Iterable[KeywordImpactRow],
    *,
    co_occurrence_rules: Iterable[CoOccurrenceRule] = DEFAULT_CO_OCCURRENCE_RULES,
) -> AggregateResult:
    """Aggregate token matches against the keyword_impact dictionary.

    Parameters
    ----------
    matches : output of `extract_matches(...)`. May be empty.
    impact_rows : every row in `keyword_impact` that's relevant to the matched
        keywords. The caller filters this set; the aggregator simply fans them
        out by `(industry_code | target_stock)`.
    co_occurrence_rules : additional boosts when N keywords co-fire.
    """
    matches = list(matches)
    impact_rows = list(impact_rows)

    # Index for fast lookup
    by_keyword: dict[str, list[KeywordImpactRow]] = {}
    for row in impact_rows:
        by_keyword.setdefault(row.keyword.lower(), []).append(row)

    # Track which keywords/symbols/countries fired
    fired_keywords: set[str] = set()
    fired_countries: set[str] = set()
    fired_symbols: set[str] = set()
    negated_keywords: set[str] = set()

    # Per-industry / per-stock contribution lists: (polarity, weight)
    industry_contribs: dict[str, list[tuple[float, float]]] = {}
    industry_keywords: dict[str, set[str]] = {}
    industry_domains: dict[str, set[str]] = {}
    stock_contribs: dict[str, list[tuple[float, float]]] = {}
    stock_keywords: dict[str, set[str]] = {}

    # 1. Process every keyword match
    for m in matches:
        if m.kind == "keyword":
            fired_keywords.add(m.text)
            if m.negated:
                negated_keywords.add(m.text)
            for row in by_keyword.get(m.text, []):
                effective_polarity = -row.polarity if m.negated else row.polarity
                if row.industry_code:
                    industry_contribs.setdefault(row.industry_code, []).append(
                        (effective_polarity, row.weight)
                    )
                    industry_keywords.setdefault(row.industry_code, set()).add(m.text)
                    if row.domain:
                        industry_domains.setdefault(row.industry_code, set()).add(row.domain)
                if row.target_stock:
                    stock_contribs.setdefault(row.target_stock, []).append(
                        (effective_polarity, row.weight)
                    )
                    stock_keywords.setdefault(row.target_stock, set()).add(m.text)
        elif m.kind == "country":
            fired_countries.add(m.text)
        elif m.kind == "symbol":
            fired_symbols.add(m.text)

    # 2. Apply co-occurrence boosts. Treat country names as eligible "keywords"
    # for the rule-firing set (so "tariff" + "china" can fire a country-aware rule).
    eligible = fired_keywords | fired_countries | {s.lower() for s in fired_symbols}
    for rule in co_occurrence_rules:
        if rule.requires.issubset({k.lower() for k in eligible}):
            industry_contribs.setdefault(rule.boost_industry, []).append(
                (rule.polarity, rule.boost)
            )
            industry_keywords.setdefault(rule.boost_industry, set()).update(rule.requires)
            industry_domains.setdefault(rule.boost_industry, set()).add("co_occurrence")

    # 3. Merge contributions into final scores
    industries = []
    for code, contribs in industry_contribs.items():
        polarity, strength = _merge_directional(contribs)
        if strength <= 0.0:
            continue
        industries.append(IndustryImpact(
            industry_code=code,
            polarity=polarity,
            strength=strength,
            contributing_keywords=sorted(industry_keywords.get(code, set())),
            contributing_domains=sorted(industry_domains.get(code, set())),
        ))

    stocks = []
    for sym, contribs in stock_contribs.items():
        polarity, strength = _merge_directional(contribs)
        if strength <= 0.0:
            continue
        stocks.append(StockImpact(
            symbol=sym,
            polarity=polarity,
            strength=strength,
            contributing_keywords=sorted(stock_keywords.get(sym, set())),
        ))

    # Sort by absolute strength desc (most-confident first)
    industries.sort(key=lambda i: -i.strength * abs(i.polarity))
    stocks.sort(key=lambda s: -s.strength * abs(s.polarity))

    return AggregateResult(
        industries=industries,
        stocks=stocks,
        matched_keywords=sorted(fired_keywords),
        matched_countries=sorted(fired_countries),
        matched_symbols=sorted(fired_symbols),
        negated_keywords=sorted(negated_keywords),
    )
