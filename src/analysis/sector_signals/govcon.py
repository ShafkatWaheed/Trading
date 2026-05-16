"""Backlog card mapper — turns raw USAspending awards into StockInformation.

Per CLAUDE.md: analysis layer. Pure functions, no I/O. Inputs are
already-fetched data (caller handles caching).

Money values use Decimal (CLAUDE.md rule — NEVER float for money).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from src.analysis.sector_signals._shared import Fact, StockInformation


def _format_dollars(total: Decimal) -> str:
    """Format a Decimal dollar amount with B/M/K suffix."""
    abs_total = abs(total)
    if abs_total >= Decimal("1000000000"):
        return f"${total / Decimal('1000000000'):.1f}B"
    if abs_total >= Decimal("1000000"):
        return f"${total / Decimal('1000000'):.1f}M"
    if abs_total >= Decimal("1000"):
        return f"${total / Decimal('1000'):.1f}K"
    return f"${total:.0f}"


def _to_decimal(value) -> Decimal:
    """Safely coerce an award_amount value to Decimal."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def contracts_to_information(
    *,
    ticker: str,
    contracts: list[dict],
    as_of: str,
) -> StockInformation:
    """Build a StockInformation card body from a list of raw award dicts.

    Each dict has: award_id, recipient_name, award_amount, award_type,
    action_date, awarding_agency.
    """
    n = len(contracts)
    if n == 0:
        return StockInformation(
            ticker=ticker, topic="gov_backlog",
            headline="No recent government contract activity",
            facts=[], narrative=None, implications=[],
            related_catalysts=[], confidence="low",
            as_of=as_of, sources_used=["usaspending"],
            severity="low",
        )

    total: Decimal = sum(
        (_to_decimal(c.get("award_amount", 0)) for c in contracts),
        start=Decimal("0"),
    )

    # Aggregate dollars per awarding agency
    by_agency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for c in contracts:
        agency = (c.get("awarding_agency") or "?").strip() or "?"
        by_agency[agency] += _to_decimal(c.get("award_amount", 0))
    top_agencies = sorted(by_agency.items(), key=lambda kv: kv[1], reverse=True)[:3]

    # Top 3 individual contracts by amount
    top_contracts = sorted(
        contracts,
        key=lambda c: _to_decimal(c.get("award_amount", 0)),
        reverse=True,
    )[:3]

    headline = f"{n} contracts awarded — total {_format_dollars(total)}"

    facts: list[Fact] = []
    for agency, amount in top_agencies:
        facts.append(Fact(
            text=f"{agency}: {_format_dollars(amount)}",
            as_of=as_of, source="usaspending",
            source_url="https://www.usaspending.gov/", confidence=1.0,
        ))
    for c in top_contracts:
        award_id = c.get("award_id", "") or ""
        agency = c.get("awarding_agency", "") or ""
        action_date = c.get("action_date", "") or ""
        amount = _to_decimal(c.get("award_amount", 0))
        facts.append(Fact(
            text=f"{action_date}  {award_id}  {_format_dollars(amount)} from {agency}",
            as_of=as_of, source="usaspending",
            source_url="https://www.usaspending.gov/",
            confidence=1.0,
        ))

    return StockInformation(
        ticker=ticker, topic="gov_backlog",
        headline=headline, facts=facts,
        narrative=None, implications=[],
        related_catalysts=[], confidence="high",
        as_of=as_of, sources_used=["usaspending"],
        severity="low",
    )
