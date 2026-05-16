"""Litigation card mapper — turns raw ITC §337 investigation rows into StockInformation.

Per CLAUDE.md: analysis layer. Pure functions, no I/O. Inputs are
already-fetched data (caller handles caching).

§337 investigations are filed at the U.S. International Trade Commission
and most often allege patent infringement by importers. Being a
respondent is materially adverse — an active investigation can lead to
an exclusion order banning the import/sale of the accused products.
Being a complainant is offensive/protective and typically benign.
"""
from __future__ import annotations

from src.analysis.sector_signals._shared import Fact, StockInformation


def _is_active(status: str) -> bool:
    """A status is treated as 'active' unless explicitly terminated/closed."""
    if not status:
        # Missing status is ambiguous — treat as active to avoid
        # under-reporting respondent risk.
        return True
    lo = status.strip().lower()
    return not any(
        kw in lo for kw in ("terminated", "closed", "dismissed", "concluded")
    )


def itc_investigations_to_information(
    *,
    ticker: str,
    investigations: list[dict],
    as_of: str,
) -> StockInformation:
    """Build a StockInformation card body from a list of raw ITC §337 rows.

    Each dict has: investigation_number, title, party_name, party_role,
    status, filing_date.

    Severity:
      - "high" if ANY active investigation has party_role="respondent"
        (defensive position — exclusion-order risk)
      - "low" if no investigations
      - "med" otherwise (complainant-only or only inactive respondent rows)
    """
    n = len(investigations)
    if n == 0:
        return StockInformation(
            ticker=ticker, topic="litigation",
            headline="No active §337 investigations",
            facts=[], narrative=None, implications=[],
            related_catalysts=[], confidence="low",
            as_of=as_of, sources_used=["itc_edis"],
            severity="low",
        )

    # Count unique investigations per role (an investigation can appear in
    # multiple rows — one per party — so dedupe by investigation_number).
    respondent_invs: set[str] = set()
    complainant_invs: set[str] = set()
    has_active_respondent = False
    for row in investigations:
        inv_no = row.get("investigation_number", "") or ""
        role = row.get("party_role", "") or ""
        status = row.get("status", "") or ""
        if role == "respondent":
            respondent_invs.add(inv_no)
            if _is_active(status):
                has_active_respondent = True
        elif role == "complainant":
            complainant_invs.add(inv_no)
    total_invs = respondent_invs | complainant_invs
    # Rows with unknown role still surface in the count of investigations
    # so the headline matches what the user can see in facts.
    for row in investigations:
        inv_no = row.get("investigation_number", "") or ""
        if inv_no:
            total_invs.add(inv_no)

    n_total = len(total_invs)
    n_resp = len(respondent_invs)
    n_comp = len(complainant_invs)

    headline = (
        f"{n_total} active §337 investigations "
        f"({n_resp} as respondent, {n_comp} as complainant)"
    )

    if has_active_respondent:
        severity = "high"
    else:
        severity = "med"

    facts: list[Fact] = []
    for row in investigations[:5]:
        title = row.get("title", "") or ""
        status = row.get("status", "") or ""
        role = row.get("party_role", "") or "unknown"
        inv_no = row.get("investigation_number", "") or ""
        facts.append(Fact(
            text=f"{inv_no}  [{role}]  {status}  {title[:80]}",
            as_of=as_of, source="itc_edis",
            source_url="https://edis.usitc.gov/",
            confidence=1.0,
        ))

    return StockInformation(
        ticker=ticker, topic="litigation",
        headline=headline, facts=facts,
        narrative=None, implications=[],
        related_catalysts=[], confidence="high",
        as_of=as_of, sources_used=["itc_edis"],
        severity=severity,
    )
