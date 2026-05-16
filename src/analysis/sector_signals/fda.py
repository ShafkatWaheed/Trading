"""FDA Catalysts card mapper — turns raw openFDA Drugs@FDA rows into StockInformation.

Per CLAUDE.md: analysis layer. Pure functions, no I/O. Inputs are
already-fetched data (caller handles caching).
"""
from __future__ import annotations

from collections import Counter

from src.analysis.sector_signals._shared import Fact, StockInformation


def fda_applications_to_information(
    *,
    ticker: str,
    applications: list[dict],
    as_of: str,
) -> StockInformation:
    """Build a StockInformation card body from raw openFDA application rows.

    Each row has: application_number, sponsor_name, submission_type,
    submission_status, action_date.
    """
    n = len(applications)
    if n == 0:
        return StockInformation(
            ticker=ticker, topic="fda_pipeline",
            headline="No recent FDA application activity",
            facts=[], narrative=None, implications=[],
            related_catalysts=[], confidence="low",
            as_of=as_of, sources_used=["openfda"],
            severity="low",
        )

    status_counts = Counter(
        (a.get("submission_status") or "?") for a in applications
    ).most_common(3)
    top_status = status_counts[0][0] if status_counts else "?"

    headline = f"{n} FDA submissions in window — most in status {top_status}"

    facts: list[Fact] = []
    for status, count in status_counts:
        facts.append(Fact(
            text=f"{count} submissions in status {status}",
            as_of=as_of, source="openfda",
            source_url="https://api.fda.gov/drug/drugsfda.json",
            confidence=1.0,
        ))
    # Top 3 applications as sample facts
    for a in applications[:3]:
        app_no = a.get("application_number", "")
        sub_type = a.get("submission_type", "") or ""
        sub_status = a.get("submission_status", "") or ""
        action_date = a.get("action_date", "") or ""
        facts.append(Fact(
            text=f"{action_date}  {app_no}  {sub_type}/{sub_status}",
            as_of=as_of, source="openfda",
            source_url=f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_no}",
            confidence=1.0,
        ))

    return StockInformation(
        ticker=ticker, topic="fda_pipeline",
        headline=headline, facts=facts,
        narrative=None, implications=[],
        related_catalysts=[], confidence="high",
        as_of=as_of, sources_used=["openfda"],
        severity="low",
    )
