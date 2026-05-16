"""Executive Changes card mapper — turns recent 8-Ks into StockInformation.

Per CLAUDE.md: analysis layer. Pure functions, no I/O. Inputs are
already-fetched 8-K filings (caller handles fetching and caching).

8-K Item 5.02 discloses departures, appointments, and compensatory
arrangements of directors and principal officers. A CFO/CEO departure
is materially adverse and gets `severity="high"`. Other departures get
`severity="med"`. Appointment-only or empty windows are low severity.
"""
from __future__ import annotations

from src.analysis.sector_signals._shared import Fact, StockInformation
from src.utils.sec_8k_parser import parse_8k_item_502


_HIGH_SEVERITY_ROLES = (
    "cfo",
    "chief financial officer",
    "ceo",
    "chief executive officer",
)


def _is_high_severity_role(role: str) -> bool:
    """True if the role string contains CEO or CFO (case-insensitive)."""
    if not role:
        return False
    lo = role.lower()
    return any(r in lo for r in _HIGH_SEVERITY_ROLES)


def exec_changes_to_information(
    *,
    ticker: str,
    filings_8k: list[dict],
    as_of: str,
) -> StockInformation:
    """Build a StockInformation card body from recent 8-K filings.

    Each filing dict has at least `raw_text` and `filing_date` (as
    produced by `fetch_recent_8ks`). The mapper parses Item 5.02 events
    from every filing and aggregates them.

    Severity:
      - "high" if any departure event has a CEO/CFO role
      - "med"  if there is any departure (non-CEO/CFO)
      - "low"  if only appointments or no events
    """
    departures: list[tuple[dict, object]] = []
    appointments: list[tuple[dict, object]] = []
    for filing in filings_8k or []:
        raw_text = filing.get("raw_text", "") or ""
        if not raw_text:
            continue
        for event in parse_8k_item_502(raw_text):
            if event.event_type == "departure":
                departures.append((filing, event))
            elif event.event_type == "appointment":
                appointments.append((filing, event))

    n_dep = len(departures)
    n_app = len(appointments)

    if n_dep == 0 and n_app == 0:
        return StockInformation(
            ticker=ticker,
            topic="exec_changes",
            headline="0 departures, 0 appointments in last 180 days",
            facts=[],
            narrative=None,
            implications=[],
            related_catalysts=[],
            confidence="low",
            as_of=as_of,
            sources_used=["sec_8k"],
            severity="low",
        )

    has_high = any(_is_high_severity_role(ev.role) for _f, ev in departures)
    if has_high:
        severity = "high"
    elif n_dep > 0:
        severity = "med"
    else:
        severity = "low"

    headline = f"{n_dep} departures, {n_app} appointments in last 180 days"

    # Top 5 events (departures first so CEO/CFO surface earliest)
    combined = departures + appointments
    facts: list[Fact] = []
    for filing, event in combined[:5]:
        filing_date = filing.get("filing_date", "") or ""
        primary_url = filing.get("primary_document_url") or None
        facts.append(Fact(
            text=(
                f"{filing_date}  [{event.event_type}]  "
                f"{event.role}  {event.person_name}"
            ),
            as_of=as_of,
            source="sec_8k",
            source_url=primary_url,
            confidence=1.0,
        ))

    return StockInformation(
        ticker=ticker,
        topic="exec_changes",
        headline=headline,
        facts=facts,
        narrative=None,
        implications=[],
        related_catalysts=[],
        confidence="high",
        as_of=as_of,
        sources_used=["sec_8k"],
        severity=severity,
    )
