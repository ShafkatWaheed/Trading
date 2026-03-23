"""Alert detection: compare new report vs previous to detect signal changes."""

import json
from dataclasses import dataclass

from src.utils.db import get_latest_report_for_symbol, save_alert


@dataclass
class Alert:
    symbol: str
    alert_type: str
    message: str
    old_value: str
    new_value: str
    severity: str  # info, warning, critical


def detect_alerts(symbol: str, new_report_content: str) -> list[Alert]:
    """Compare new report against last saved report for the same symbol."""
    prev = get_latest_report_for_symbol(symbol)
    if not prev:
        return []

    try:
        old = json.loads(prev["content"])
    except (json.JSONDecodeError, KeyError):
        return []

    try:
        new = json.loads(new_report_content)
    except (json.JSONDecodeError, TypeError):
        return []

    alerts: list[Alert] = []

    # 1. Verdict changed
    old_verdict = old.get("verdict", "")
    new_verdict = new.get("verdict", "")
    if old_verdict and new_verdict and old_verdict != new_verdict:
        severity = "critical" if _is_direction_flip(old_verdict, new_verdict) else "warning"
        alerts.append(Alert(
            symbol=symbol, alert_type="verdict_change",
            message=f"Verdict changed: {old_verdict} -> {new_verdict}",
            old_value=old_verdict, new_value=new_verdict, severity=severity,
        ))

    # 2. Risk rating increased by 2+
    old_risk = old.get("risk_rating", 0)
    new_risk = new.get("risk_rating", 0)
    if isinstance(old_risk, (int, float)) and isinstance(new_risk, (int, float)):
        if new_risk - old_risk >= 2:
            alerts.append(Alert(
                symbol=symbol, alert_type="risk_increase",
                message=f"Risk rating jumped: {old_risk}/5 -> {new_risk}/5",
                old_value=str(old_risk), new_value=str(new_risk), severity="critical",
            ))

    # 3. Check sections for specific signal changes
    old_sections = {s["title"]: s for s in old.get("sections", [])}
    new_sections = {s["title"]: s for s in new.get("sections", [])}

    # Smart Money: cluster buy detected
    smart_old = old_sections.get("Smart Money (Insider + Institutional)", {}).get("data", {})
    smart_new = new_sections.get("Smart Money (Insider + Institutional)", {}).get("data", {})
    if smart_new.get("cluster_buy") and not smart_old.get("cluster_buy"):
        alerts.append(Alert(
            symbol=symbol, alert_type="cluster_buy",
            message="Insider cluster buy detected — 2+ insiders buying within 7 days",
            old_value="no", new_value="yes", severity="critical",
        ))

    # Macro regime changed
    macro_old = old_sections.get("Macro Environment", {}).get("data", {})
    macro_new = new_sections.get("Macro Environment", {}).get("data", {})
    old_regime = macro_old.get("regime", "")
    new_regime = macro_new.get("regime", "")
    if old_regime and new_regime and old_regime != new_regime:
        severity = "critical" if new_regime == "recession_warning" else "warning"
        alerts.append(Alert(
            symbol=symbol, alert_type="regime_change",
            message=f"Macro regime changed: {old_regime} -> {new_regime}",
            old_value=old_regime, new_value=new_regime, severity=severity,
        ))

    # Technical signal flip
    tech_old = old_sections.get("Technical Analysis", {}).get("data", {})
    tech_new = new_sections.get("Technical Analysis", {}).get("data", {})
    old_signal = tech_old.get("signal", "")
    new_signal = tech_new.get("signal", "")
    if old_signal and new_signal and old_signal != new_signal:
        if _is_direction_flip(old_signal, new_signal):
            alerts.append(Alert(
                symbol=symbol, alert_type="technical_flip",
                message=f"Technical signal flipped: {old_signal} -> {new_signal}",
                old_value=old_signal, new_value=new_signal, severity="warning",
            ))

    # Sentiment flip
    old_sent = old.get("sentiment_score", "0")
    new_sent = new.get("sentiment_score", "0")
    try:
        old_s = float(old_sent)
        new_s = float(new_sent)
        if (old_s > 0.3 and new_s < -0.3) or (old_s < -0.3 and new_s > 0.3):
            alerts.append(Alert(
                symbol=symbol, alert_type="sentiment_flip",
                message=f"Sentiment flipped: {old_s:.2f} -> {new_s:.2f}",
                old_value=str(old_s), new_value=str(new_s), severity="warning",
            ))
    except (ValueError, TypeError):
        pass

    # Save all alerts to DB
    for a in alerts:
        save_alert(a.symbol, a.alert_type, a.message, a.old_value, a.new_value, a.severity)

    return alerts


def _is_direction_flip(old: str, new: str) -> bool:
    """Check if a signal flipped from buy-side to sell-side or vice versa."""
    buy_words = {"buy", "strong buy", "bullish"}
    sell_words = {"sell", "strong sell", "bearish"}
    o = old.lower()
    n = new.lower()
    return (o in buy_words and n in sell_words) or (o in sell_words and n in buy_words)
