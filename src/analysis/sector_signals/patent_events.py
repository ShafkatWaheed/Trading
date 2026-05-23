"""Consolidated Patent Events mapper (Wave 2, Phase 2).

Per CLAUDE.md: analysis layer. Pure function, no I/O, no imports from
`src/data` or `src/utils` at runtime — input dataclass types are only
referenced under TYPE_CHECKING. The mapper duck-types attribute access
on `LicenseDeal` and `LitigationEvent` instances.

Combines four upstream signals into a single StockInformation:
  1) FDA Orange Book patents (patent-cliff timing)
  2) ITC §337 investigations (exclusion-order risk)
  3) SEC 8-K Item 1.01 license deals (IP monetization / partnerships)
  4) SEC 8-K Item 8.01 IP litigation events (verdicts, settlements)

Severity (highest wins):
  HIGH: patent cliff within 12 months
        OR active §337 as respondent
        OR Item 8.01 verdict/judgment against the company
  MED:  patent cliff within 12–24 months
        OR active §337 (complainant or unknown role)
        OR Item 1.01 license deal
        OR Item 8.01 settlement / dismissal / non-verdict event
  LOW:  no near-term cliff, no active §337, no recent material IP events
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from src.analysis.sector_signals._shared import Fact, StockInformation

if TYPE_CHECKING:
    # Type-only imports — not imported at runtime. The mapper uses duck-typed
    # attribute access on these objects so the analysis layer never depends
    # on src/utils at runtime.
    from src.utils.sec_8k_parser import LicenseDeal, LitigationEvent  # noqa: F401


# ---- helpers ---------------------------------------------------------------

# Orange Book ships expire dates in "Mon DD, YYYY" form (e.g. "May 23, 2027").
_OB_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d")


def _parse_ob_date(s: str) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in _OB_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _today_utc() -> date:
    return datetime.now(tz=timezone.utc).date()


def _is_active_337(status: str) -> bool:
    """A §337 status is treated as active unless explicitly terminated/closed."""
    if not status:
        # Missing status is ambiguous — treat as active to avoid
        # under-reporting respondent risk.
        return True
    lo = status.strip().lower()
    return not any(
        kw in lo for kw in ("terminated", "closed", "dismissed", "concluded")
    )


# ---- main entry point ------------------------------------------------------

def patent_events_to_information(
    *,
    ticker: str,
    as_of: str,
    orange_book_patents: list[dict] | None = None,
    itc_investigations: list[dict] | None = None,
    license_deals: list[Any] | None = None,
    litigation_events: list[Any] | None = None,
) -> StockInformation:
    """Build a StockInformation summarizing patent events from 4 sources.

    All four input lists are optional/may be empty. Empty everywhere →
    severity=low, confidence=low, facts=[].

    Severity rules (highest wins):
      - HIGH: patent cliff within 12 months OR active §337 as respondent
              OR Item 8.01 verdict-against-company
      - MED:  patent cliff 12-24 months OR active §337 (any role)
              OR Item 1.01 license deal OR Item 8.01 settlement
      - LOW:  no near-term cliff, no active §337, no recent material IP events

    Facts ordered most-actionable first (cliff-soonest → litigation → licenses).
    """
    orange_book_patents = orange_book_patents or []
    itc_investigations = itc_investigations or []
    license_deals = license_deals or []
    litigation_events = litigation_events or []

    any_data = bool(
        orange_book_patents or itc_investigations
        or license_deals or litigation_events
    )

    if not any_data:
        return StockInformation(
            ticker=ticker, topic="patent_events",
            headline="No material patent events",
            facts=[], narrative=None, implications=[],
            related_catalysts=[], confidence="low",
            as_of=as_of, sources_used=[],
            severity="low",
        )

    today = _today_utc()
    sources_used: list[str] = []
    implications: list[str] = []
    related_catalysts: list[str] = []

    severities: list[str] = []  # collect all per-source severity contributions

    # ---- 1) Orange Book patent cliff ---------------------------------------
    cliff_facts: list[Fact] = []
    # Group by trade_name; track soonest-expiring per drug
    drug_to_soonest: dict[str, tuple[date, dict]] = {}
    for row in orange_book_patents:
        exp_raw = row.get("patent_expire_date", "") or ""
        exp = _parse_ob_date(exp_raw)
        if exp is None:
            continue
        drug = (row.get("trade_name") or row.get("application_number") or "").strip()
        if not drug:
            continue
        cur = drug_to_soonest.get(drug)
        if cur is None or exp < cur[0]:
            drug_to_soonest[drug] = (exp, row)

    # Sort drugs by soonest expiry first (most-actionable first)
    sorted_drugs = sorted(drug_to_soonest.items(), key=lambda kv: kv[1][0])

    n_cliff_12mo = 0
    n_cliff_24mo = 0
    has_cliff_12 = False
    has_cliff_24 = False
    for drug, (exp, row) in sorted_drugs:
        days = (exp - today).days
        if days < 0:
            # Already expired — skip (no upcoming cliff)
            continue
        if days <= 365:
            has_cliff_12 = True
            n_cliff_12mo += 1
        elif days <= 730:
            has_cliff_24 = True
            n_cliff_24mo += 1

    for drug, (exp, row) in sorted_drugs:
        days = (exp - today).days
        if days < 0 or days > 730:
            continue
        app_no = row.get("application_number", "") or ""
        pat_no = row.get("patent_number", "") or ""
        use_code = row.get("use_code", "") or ""
        text = (
            f"{drug} (NDA {app_no}, US{pat_no}) — patent expires "
            f"{exp.isoformat()} ({days}d)"
            + (f" · use code {use_code}" if use_code else "")
        )
        cliff_facts.append(Fact(
            text=text,
            as_of=as_of,
            source="fda_orange_book",
            source_url=(
                f"https://www.accessdata.fda.gov/scripts/cder/ob/results_product.cfm"
                f"?Appl_No={app_no}" if app_no else
                "https://www.accessdata.fda.gov/scripts/cder/ob/"
            ),
            confidence=1.0,
        ))
        related_catalysts.append(f"{drug} patent expiry {exp.isoformat()}")

    if orange_book_patents:
        sources_used.append("fda_orange_book")
    if has_cliff_12:
        severities.append("high")
        implications.append("patent cliff near-term (<12mo)")
    elif has_cliff_24:
        severities.append("med")
        implications.append("patent cliff 12-24 months")

    # ---- 2) ITC §337 investigations ----------------------------------------
    itc_facts: list[Fact] = []
    active_respondent = False
    n_active_337 = 0
    seen_invs: set[str] = set()
    for row in itc_investigations:
        inv_no = (row.get("investigation_number") or "").strip()
        role = (row.get("party_role") or "").strip().lower()
        status = (row.get("status") or "").strip()
        title = (row.get("title") or "").strip()
        if _is_active_337(status):
            if inv_no and inv_no not in seen_invs:
                n_active_337 += 1
                seen_invs.add(inv_no)
            if role == "respondent":
                active_respondent = True
        itc_facts.append(Fact(
            text=f"§337 {inv_no} [{role or 'unknown'}] {status} — {title[:80]}",
            as_of=as_of,
            source="itc_edis",
            source_url="https://edis.usitc.gov/",
            confidence=1.0,
        ))

    if itc_investigations:
        sources_used.append("itc_edis")
    if active_respondent:
        severities.append("high")
        implications.append("active §337 respondent (exclusion-order risk)")
    elif n_active_337 > 0:
        severities.append("med")
        implications.append("active §337 investigation")

    # ---- 3) License deals (8-K Item 1.01) ----------------------------------
    license_facts: list[Fact] = []
    n_licenses = 0
    for ld in license_deals:
        deal_type = getattr(ld, "deal_type", "") or ""
        counterparty = getattr(ld, "counterparty", "") or ""
        summary = getattr(ld, "summary", "") or ""
        n_licenses += 1
        license_facts.append(Fact(
            text=f"{deal_type}: {counterparty} — {summary[:120]}",
            as_of=as_of,
            source="sec_8k",
            source_url=None,
            confidence=0.9,
        ))

    # ---- 4) Litigation events (8-K Item 8.01) ------------------------------
    lit_facts: list[Fact] = []
    has_verdict_against = False
    has_other_lit = False
    for le in litigation_events:
        kind = (getattr(le, "event_kind", "") or "").lower()
        direction = (getattr(le, "direction", "") or "").lower()
        summary = getattr(le, "summary", "") or ""
        if direction == "against_company" and kind in ("verdict", "judgment"):
            has_verdict_against = True
        else:
            has_other_lit = True
        lit_facts.append(Fact(
            text=f"{kind}: {direction} — {summary[:120]}",
            as_of=as_of,
            source="sec_8k",
            source_url=None,
            confidence=0.9,
        ))

    if license_deals or litigation_events:
        if "sec_8k" not in sources_used:
            sources_used.append("sec_8k")

    if has_verdict_against:
        severities.append("high")
        implications.append("adverse IP verdict/judgment")
    if has_other_lit:
        severities.append("med")
        implications.append("IP litigation event reported")
    if n_licenses > 0:
        severities.append("med")
        implications.append(f"{n_licenses} material IP license deal(s)")

    # ---- Severity rollup ---------------------------------------------------
    if "high" in severities:
        severity = "high"
    elif "med" in severities:
        severity = "med"
    else:
        severity = "low"

    # ---- Headline ----------------------------------------------------------
    parts: list[str] = []
    if has_cliff_12 or has_cliff_24:
        n = n_cliff_12mo if has_cliff_12 else n_cliff_24mo
        window = "12mo" if has_cliff_12 else "24mo"
        parts.append(f"Patent cliff: {n} NDAs lose exclusivity in {window}")
    if n_active_337 > 0:
        suffix = " (respondent)" if active_respondent else ""
        parts.append(f"{n_active_337} active §337{suffix}")
    if n_licenses > 0:
        parts.append(f"{n_licenses} IP license deal{'s' if n_licenses != 1 else ''}")
    if has_verdict_against:
        parts.append("adverse IP verdict")
    elif has_other_lit:
        parts.append("IP litigation event")

    if not parts:
        headline = "No material patent events"
    else:
        headline = " · ".join(parts)

    # ---- Facts ordering: cliff (soonest first) → litigation → licenses ----
    facts: list[Fact] = []
    facts.extend(cliff_facts)
    facts.extend(lit_facts)
    facts.extend(itc_facts)
    facts.extend(license_facts)

    confidence = "high" if any_data else "low"

    return StockInformation(
        ticker=ticker,
        topic="patent_events",
        headline=headline,
        facts=facts,
        narrative=None,
        implications=implications,
        related_catalysts=related_catalysts,
        confidence=confidence,
        as_of=as_of,
        sources_used=sources_used,
        severity=severity,
    )
