"""Innovation card mapper — turns raw USPTO patents/trademarks into StockInformation.

Per CLAUDE.md: analysis layer. Pure functions, no I/O. Inputs are
already-fetched data (caller handles caching).
"""
from __future__ import annotations

from collections import Counter

from src.analysis.sector_signals._shared import Fact, StockInformation


def patents_to_information(
    *,
    ticker: str,
    patents: list[dict],
    as_of: str,
) -> StockInformation:
    """Build a StockInformation card body from a list of raw patent dicts.

    Each dict has: patent_id, title, date, cpc_class, assignee.
    """
    n = len(patents)
    if n == 0:
        return StockInformation(
            ticker=ticker, topic="innovation",
            headline="No recent patent activity",
            facts=[], narrative=None, implications=[],
            related_catalysts=[], confidence="low",
            as_of=as_of, sources_used=["uspto_patentsview"],
            severity="low",
        )

    cpc_counts = Counter(p.get("cpc_class", "") or "?" for p in patents).most_common(3)
    top_cpc = cpc_counts[0][0] if cpc_counts else "?"

    headline = f"{n} patents granted in window — heaviest in CPC {top_cpc}"

    facts: list[Fact] = []
    for cpc, count in cpc_counts:
        facts.append(Fact(
            text=f"{count} patents in CPC class {cpc}",
            as_of=as_of, source="uspto_patentsview",
            source_url="https://search.patentsview.org/", confidence=1.0,
        ))
    # Top 3 patents as sample facts
    for p in patents[:3]:
        facts.append(Fact(
            text=f"{p['date']}  {p['title'][:80]}",
            as_of=as_of, source="uspto_patentsview",
            source_url=f"https://patents.google.com/patent/US{p['patent_id']}",
            confidence=1.0,
        ))

    return StockInformation(
        ticker=ticker, topic="innovation",
        headline=headline, facts=facts,
        narrative=None, implications=[],
        related_catalysts=[], confidence="high",
        as_of=as_of, sources_used=["uspto_patentsview"],
        severity="low",
    )
