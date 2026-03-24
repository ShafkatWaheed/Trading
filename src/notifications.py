"""Push notification service for alerts — Slack, Discord, Email."""

import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

from src.utils.config import (
    SLACK_WEBHOOK_URL, DISCORD_WEBHOOK_URL,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL,
)


def send_alert(symbol: str, alert_type: str, message: str, severity: str) -> list[str]:
    """Send alert to all configured channels. Returns list of channels notified."""
    sent: list[str] = []

    if SLACK_WEBHOOK_URL:
        if _send_slack(symbol, alert_type, message, severity):
            sent.append("slack")

    if DISCORD_WEBHOOK_URL:
        if _send_discord(symbol, alert_type, message, severity):
            sent.append("discord")

    if ALERT_EMAIL and SMTP_HOST:
        if _send_email(symbol, alert_type, message, severity):
            sent.append("email")

    return sent


def _send_slack(symbol: str, alert_type: str, message: str, severity: str) -> bool:
    try:
        icon = ":red_circle:" if severity == "critical" else ":warning:" if severity == "warning" else ":information_source:"
        payload = {
            "text": f"{icon} *{symbol}* — {alert_type}\n{message}",
            "username": "Trading Alerts",
            "icon_emoji": ":chart_with_upwards_trend:",
        }
        resp = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def _send_discord(symbol: str, alert_type: str, message: str, severity: str) -> bool:
    try:
        color = 0xFF0000 if severity == "critical" else 0xFFAA00 if severity == "warning" else 0x3B82F6
        payload = {
            "embeds": [{
                "title": f"{symbol} — {alert_type}",
                "description": message,
                "color": color,
                "footer": {"text": "Trading Analysis Platform"},
            }]
        }
        resp = httpx.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception:
        return False


def _send_email(symbol: str, alert_type: str, message: str, severity: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL
        msg["Subject"] = f"[{severity.upper()}] {symbol} — {alert_type}"

        body = f"""
Trading Alert

Symbol: {symbol}
Type: {alert_type}
Severity: {severity.upper()}

{message}

---
Trading Analysis Platform
        """
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception:
        return False
