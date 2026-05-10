"""Layer 5: news-tag distribution drift detector.

Counts which keyword *domains* recent news articles for a stock fall into
(via the existing keyword_impact + tokenize layer) and compares to the
distribution of the stock's own theme tags. A mismatch indicates the
narrative around the stock has shifted (PLTR → AI; SOFI → consumer banking).

Pure function on a list of headlines + the stock's current theme tags.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.news.aggregate import KeywordImpactRow, aggregate
from src.news.tokenize import extract_matches


# Threshold: when the dominant news-domain represents > X fraction of recent
# articles AND the stock's industry doesn't align with that domain → drift.
DEFAULT_DOMINANT_THRESHOLD: float = 0.40


@dataclass(frozen=True)
class NewsDriftResult:
    symbol: str
    dominant_domain: str | None
    dominant_share: float
    aligns_with_tags: bool
    drifted: bool
    domain_distribution: dict[str, int]


def detect_news_drift(
    symbol: str,
    headlines: list[str],
    *,
    impact_rows: list[KeywordImpactRow],
    keyword_set: set[str],
    universe: set[str],
    current_industry_domains: set[str],
    threshold: float = DEFAULT_DOMINANT_THRESHOLD,
) -> NewsDriftResult:
    """Counts news-domain hits per article; flags if dominant domain doesn't
    align with the stock's current theme/industry domains.

    Args:
        symbol: ticker
        headlines: list of recent news article headlines (already filtered to
            articles mentioning this symbol)
        impact_rows: keyword_impact table rows
        keyword_set: lowercase keyword strings in keyword_impact
        universe: set of known stock symbols (for NER)
        current_industry_domains: domains the stock's industry currently maps to
            (e.g. for NVDA: {'ai'}; for XOM: {'oil'})
        threshold: fraction at which a single domain is "dominant"

    Returns NewsDriftResult.
    """
    domain_counts: Counter = Counter()
    for headline in headlines:
        matches = extract_matches(headline, keywords=keyword_set, universe=universe)
        agg = aggregate(matches, impact_rows)
        # Each matched industry brings its domain — count once per domain per article
        seen_in_this_headline: set[str] = set()
        for industry in agg.industries:
            for d in industry.contributing_domains:
                if d not in seen_in_this_headline:
                    domain_counts[d] += 1
                    seen_in_this_headline.add(d)

    total_articles = len(headlines)
    if total_articles == 0:
        return NewsDriftResult(
            symbol=symbol,
            dominant_domain=None,
            dominant_share=0.0,
            aligns_with_tags=True,
            drifted=False,
            domain_distribution=dict(domain_counts),
        )

    if not domain_counts:
        return NewsDriftResult(
            symbol=symbol,
            dominant_domain=None,
            dominant_share=0.0,
            aligns_with_tags=True,
            drifted=False,
            domain_distribution={},
        )

    dominant_domain, dominant_count = domain_counts.most_common(1)[0]
    dominant_share = dominant_count / total_articles

    aligns = dominant_domain in current_industry_domains
    drifted = dominant_share >= threshold and not aligns

    return NewsDriftResult(
        symbol=symbol,
        dominant_domain=dominant_domain,
        dominant_share=dominant_share,
        aligns_with_tags=aligns,
        drifted=drifted,
        domain_distribution=dict(domain_counts),
    )
