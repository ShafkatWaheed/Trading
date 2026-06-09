"""Daily digest — morning summary of today's predictions + brief.

Sent each morning at 7:00 ET. Two delivery channels:

1. File (always on)
     data/digests/YYYY-MM-DD.md
   Useful for grep-able history, RSS feeders, or wiring into anything
   else you want.

2. Email (opt-in via env vars)
     SMTP_HOST + SMTP_USER + SMTP_PASSWORD + DIGEST_TO_EMAIL
   If any of these are missing, email delivery is silently skipped and
   the file-only path runs.

Content:
  - Top 5 of today's predictions (symbol + reasoning)
  - Active strategy name + last hit rate
  - Brief headline (if already generated for today)
  - Yesterday's prediction results (which hit, which missed)

The scheduler entry in api/main.py runs this at 7:00 ET. The route
below lets you trigger it manually.
"""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DIGEST_DIR = _PROJECT_ROOT / "data" / "digests"


def _ensure_digest_dir() -> Path:
    _DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    return _DIGEST_DIR


def _today_iso() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _yesterday_iso() -> str:
    return (datetime.now(tz=timezone.utc).date() - timedelta(days=1)).isoformat()


def _section_predictions() -> str:
    """Top 5 of today's predictions with reasoning."""
    try:
        from api.services import predictions_service
        today = predictions_service.get_predictions_today()
    except Exception as e:
        return f"## Today's Predictions\n_Predictions service unavailable: {e}_\n"

    picks = (today.get("picks") or [])[:5]
    if not picks:
        return "## Today's Predictions\n_No predictions generated yet._\n"

    lines = [
        f"## Today's Predictions",
        f"_Strategy: **{today.get('strategy_name', '—')}** "
        f"(v{today.get('strategy_version', '—')})_",
        "",
    ]
    for p in picks:
        sym = p.get("symbol", "?")
        reasoning = p.get("reasoning", "")
        lines.append(f"- **#{p.get('rank', '?')} ${sym}** — {reasoning}")
    return "\n".join(lines) + "\n"


def _section_yesterday_results() -> str:
    """How yesterday's picks actually did."""
    try:
        from api.services import predictions_service
        y = predictions_service.get_predictions_with_actuals(_yesterday_iso())
    except Exception:
        return ""

    picks = y.get("picks") or []
    if not picks or not y.get("actuals_present"):
        return ""

    lines = [
        f"## Yesterday's Results ({y.get('date', '—')})",
        "",
    ]
    hits = 0
    for p in picks:
        sym = p.get("symbol", "?")
        change = p.get("actual_change_pct")
        rank = p.get("universe_rank")
        size = p.get("universe_size")
        if rank is not None and rank <= 25:
            hits += 1
        change_s = f"{change:+.2f}%" if change is not None else "—"
        rank_s = f"#{rank}/{size}" if rank is not None else "—"
        lines.append(f"- **${sym}** — close {change_s}, universe rank {rank_s}")
    lines.append("")
    lines.append(f"**Hit rate (top 25): {hits}/{len(picks)}**")
    return "\n".join(lines) + "\n"


def _section_accuracy() -> str:
    """Rolling 30-day accuracy."""
    try:
        from api.services import predictions_service
        acc = predictions_service.get_accuracy_window(window_days=30, hit_threshold=25)
    except Exception:
        return ""

    if not acc or acc.get("predictions_total", 0) == 0:
        return ""
    return (
        f"## Rolling Accuracy\n"
        f"30-day hit rate: **{acc['hit_rate']*100:.1f}%** "
        f"({acc['hits']}/{acc['predictions_total']} picks landed in top 25, "
        f"across {acc['days_evaluated']} days)\n"
    )


def _section_brief_headline() -> str:
    """Brief headline if today's brief is already cached."""
    try:
        from src.utils.db import cache_get
        brief = cache_get("brief:v8:div=0")
        if brief and brief.get("market_story", {}).get("headline"):
            headline = brief["market_story"]["headline"]
            regime = brief.get("regime", "—")
            return f"## Brief Headline\n**{headline}**\n\n_Regime: {regime}_\n"
    except Exception:
        pass
    return ""


def build_digest() -> dict:
    """Compose the morning digest markdown.

    Returns {date, content, sections: [list of section names included]}.
    """
    sections = []
    parts = []

    pred = _section_predictions()
    parts.append(pred)
    sections.append("predictions")

    brief = _section_brief_headline()
    if brief:
        parts.append(brief)
        sections.append("brief")

    yest = _section_yesterday_results()
    if yest:
        parts.append(yest)
        sections.append("yesterday")

    acc = _section_accuracy()
    if acc:
        parts.append(acc)
        sections.append("accuracy")

    today = _today_iso()
    header = f"# Daily Digest — {today}\n\n"
    content = header + "\n---\n\n".join(parts)
    return {"date": today, "content": content, "sections": sections}


def write_digest_file(digest: dict) -> Path:
    """Persist today's digest to data/digests/YYYY-MM-DD.md."""
    _ensure_digest_dir()
    path = _DIGEST_DIR / f"{digest['date']}.md"
    path.write_text(digest["content"], encoding="utf-8")
    return path


def send_digest_email(digest: dict) -> dict:
    """Best-effort email delivery. Silent skip when SMTP env vars missing.

    Env vars (all required for delivery):
      SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD,
      DIGEST_TO_EMAIL, DIGEST_FROM_EMAIL (defaults to SMTP_USER)
    """
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to_addr = os.environ.get("DIGEST_TO_EMAIL")
    if not (host and user and password and to_addr):
        return {"sent": False, "reason": "smtp_not_configured"}

    port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("DIGEST_FROM_EMAIL", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Trading digest — {digest['date']}"
    msg["From"] = from_addr
    msg["To"] = to_addr
    # Plain markdown body — most email clients render it acceptably.
    msg.attach(MIMEText(digest["content"], "plain"))

    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, password)
            s.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception as e:
        logger.warning("daily_digest: SMTP delivery failed: %r", e)
        return {"sent": False, "reason": f"smtp_error: {type(e).__name__}"}
    return {"sent": True, "to": to_addr}


def send_daily_digest() -> dict:
    """Build + write + (optionally) email the morning digest.

    Returns a single status dict combining all three.
    """
    digest = build_digest()
    path = write_digest_file(digest)
    email_result = send_digest_email(digest)
    return {
        "date":         digest["date"],
        "sections":     digest["sections"],
        "file":         str(path),
        "email":        email_result,
        "bytes":        len(digest["content"].encode("utf-8")),
    }
