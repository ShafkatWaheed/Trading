"""Alerts service: read, mark seen, summary, and Wave 2 type wrappers.

The base alerting primitive is src.utils.db.save_alert(); the Wave 2
wrappers below provide typed, well-formatted alert creators per type.
"""
from __future__ import annotations

from src.utils.db import init_db, get_alerts, get_connection, save_alert


def list_alerts(symbol: str | None = None, limit: int = 50) -> list[dict]:
    init_db()
    rows = get_alerts(symbol=symbol, limit=limit)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "symbol": r.get("symbol", ""),
            "alert_type": r.get("alert_type", ""),
            "message": r.get("message", ""),
            "old_value": r.get("old_value"),
            "new_value": r.get("new_value"),
            "severity": r.get("severity", "info"),
            "created_at": str(r.get("created_at", "")),
        })
    return out


def get_summary() -> dict:
    """Quick badge counts for the nav."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS critical, "
            "SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) AS warning, "
            "SUM(CASE WHEN created_at > datetime('now', '-24 hours') THEN 1 ELSE 0 END) AS last_24h "
            "FROM alerts"
        ).fetchone()
        return {
            "total": int((row["total"] or 0) if row else 0),
            "critical": int((row["critical"] or 0) if row else 0),
            "warning": int((row["warning"] or 0) if row else 0),
            "last_24h": int((row["last_24h"] or 0) if row else 0),
        }
    finally:
        conn.close()


def clear_all() -> dict:
    """Wipe all alerts."""
    init_db()
    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        conn.execute("DELETE FROM alerts")
        conn.commit()
        return {"ok": True, "deleted": int(before)}
    finally:
        conn.close()


# -- Wave 2: sector-influence alert types ----------------------------------


def create_fda_decision_alert(
    *,
    ticker: str,
    application_number: str,
    submission_status: str,
    action_date: str,
) -> int:
    """FDA decision (approval, CRL, AdCom, PDUFA) -> alerts table."""
    severity = "warning"  # FDA decisions move stocks; never 'info'
    if submission_status.lower() in {"approved", "complete response"}:
        severity = "high"  # binary catalyst
    message = (
        f"{ticker}: FDA action on {application_number} - "
        f"{submission_status} on {action_date}"
    )
    return save_alert(
        symbol=ticker,
        alert_type="fda_decision",
        message=message,
        severity=severity,
    )


def create_itc_filing_alert(
    *,
    ticker: str,
    investigation_number: str,
    party_role: str,
    title: str,
) -> int:
    """ITC Section 337 investigation filing -> alerts table.

    Respondent role = potential import ban (high severity).
    Complainant role = offensive (warning severity).
    """
    severity = "high" if party_role.lower() == "respondent" else "warning"
    message = (
        f"{ticker}: ITC Section 337 investigation {investigation_number} "
        f"as {party_role}. Subject: {title[:120]}"
    )
    return save_alert(
        symbol=ticker,
        alert_type="itc_337_filing",
        message=message,
        severity=severity,
    )


def create_exec_departure_alert(
    *,
    ticker: str,
    person_name: str,
    role: str,
    filing_date: str,
) -> int:
    """Executive departure from 8-K Item 5.02 -> alerts table.

    CEO/CFO departures = high severity. Other roles = warning.
    """
    role_upper = role.upper()
    is_cxo = any(
        k in role_upper
        for k in ("CFO", "CEO", "CHIEF FINANCIAL", "CHIEF EXECUTIVE")
    )
    severity = "high" if is_cxo else "warning"
    # Append a short-form C-suite tag for readability/searchability.
    role_short = role
    if "CHIEF FINANCIAL OFFICER" in role_upper:
        role_short = role + " (CFO)"
    elif "CHIEF EXECUTIVE OFFICER" in role_upper:
        role_short = role + " (CEO)"
    message = (
        f"{ticker}: {person_name} departing as {role_short} "
        f"(filed {filing_date})"
    )
    return save_alert(
        symbol=ticker,
        alert_type="exec_departure",
        message=message,
        severity=severity,
    )


def create_contract_award_alert(
    *,
    ticker: str,
    award_id: str,
    award_amount: float,
    awarding_agency: str,
    action_date: str,
) -> int:
    """Large government contract award -> alerts table.

    Small awards = info, >= $1B = warning.
    """
    severity = "warning" if award_amount >= 1_000_000_000 else "info"
    if award_amount >= 1_000_000_000:
        amt = f"${award_amount / 1_000_000_000:.2f}B"
    elif award_amount >= 1_000_000:
        amt = f"${award_amount / 1_000_000:.1f}M"
    else:
        amt = f"${award_amount:,.0f}"
    message = (
        f"{ticker}: {amt} contract award from {awarding_agency} "
        f"({award_id}, action {action_date})"
    )
    return save_alert(
        symbol=ticker,
        alert_type="contract_award",
        message=message,
        severity=severity,
    )
