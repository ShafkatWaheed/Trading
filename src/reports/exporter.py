"""Export reports to PDF, HTML, JSON."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.models.report import Report
from src.utils.config import REPORT_OUTPUT_DIR


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def export_json(report: Report) -> Path:
    output_dir = Path(REPORT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{report.symbol}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}.json"
    path = output_dir / filename

    data = {
        "symbol": report.symbol,
        "name": report.name,
        "generated_at": report.generated_at.isoformat(),
        "verdict": report.verdict.value,
        "confidence": report.confidence,
        "risk_rating": report.risk_rating.value,
        "current_price": str(report.current_price),
        "sentiment_score": str(report.sentiment_score),
        "reasoning": report.reasoning,
        "risks": report.risks,
        "sections": [
            {"title": s.title, "content": s.content, "data": s.data}
            for s in report.sections
        ],
        "disclaimer": report.DISCLAIMER,
    }

    path.write_text(json.dumps(data, indent=2, cls=DecimalEncoder))
    return path


def export_html(report: Report) -> Path:
    output_dir = Path(REPORT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{report.symbol}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}.html"
    path = output_dir / filename

    html = _render_html(report)
    path.write_text(html)
    return path


def export_pdf(report: Report) -> Path:
    """Export report as PDF via WeasyPrint."""
    output_dir = Path(REPORT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{report.symbol}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}.pdf"
    path = output_dir / filename

    html = _render_html(report)
    from weasyprint import HTML
    HTML(string=html).write_pdf(str(path))
    return path


# --- Verdict helpers ---

def _verdict_class(verdict_value: str) -> str:
    v = verdict_value.lower()
    if "strong buy" in v:
        return "strong-buy"
    if "buy" in v:
        return "buy"
    if "strong sell" in v:
        return "strong-sell"
    if "sell" in v:
        return "sell"
    return "hold"


def _signal_badge(value: str) -> str:
    """Return a colored badge for bullish/bearish/neutral signals."""
    v = str(value).lower()
    if any(w in v for w in ("bullish", "buy", "strong buy", "positive", "uptrend", "increasing")):
        return f'<span class="badge bullish">{value}</span>'
    if any(w in v for w in ("bearish", "sell", "strong sell", "negative", "downtrend", "decreasing")):
        return f'<span class="badge bearish">{value}</span>'
    return f'<span class="badge neutral">{value}</span>'


def _format_value(key: str, val) -> str:
    """Format a data value for display."""
    if isinstance(val, list):
        if not val:
            return "—"
        return "<br>".join(f"• {v}" for v in val)
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if val is None or str(val) == "None":
        return "—"

    s = str(val)
    k = key.lower()

    # Color-code signal-like values
    if k in ("signal", "sentiment", "trend", "overall_signal", "insider_signal",
             "institutional_signal", "volume_trend", "alignment", "valuation", "net_sentiment"):
        return _signal_badge(s)

    # Format percentages
    if k.endswith("_percent") or k in ("change_percent",):
        try:
            return f"{float(s):.2f}%"
        except (ValueError, TypeError):
            return s

    # Format large numbers
    if k in ("market_cap", "volume", "avg_volume"):
        try:
            n = float(s)
            if n >= 1e12:
                return f"${n/1e12:.2f}T"
            if n >= 1e9:
                return f"${n/1e9:.2f}B"
            if n >= 1e6:
                return f"${n/1e6:.1f}M"
            return f"{n:,.0f}"
        except (ValueError, TypeError):
            return s

    return s


def _render_html(report: Report) -> str:
    verdict_cls = _verdict_class(report.verdict.value)

    # Build sections HTML
    sections_html = ""
    for section in report.sections:
        data_rows = ""
        for key, val in section.data.items():
            display_key = key.replace("_", " ").title()
            display_val = _format_value(key, val)
            data_rows += f'<tr><td class="key">{display_key}</td><td>{display_val}</td></tr>\n'

        # Section icon
        icon = _section_icon(section.title)

        sections_html += f"""
        <div class="section">
            <h2>{icon} {section.title}</h2>
            <p class="section-content">{section.content}</p>
            {f'<table>{data_rows}</table>' if data_rows else ''}
        </div>
        """

    # Risks
    risks_html = ""
    if report.risks:
        risk_items = "".join(f"<li>{r}</li>" for r in report.risks)
        risks_html = f"""
        <div class="section risks-section">
            <h2>Identified Risks</h2>
            <ul class="risk-list">{risk_items}</ul>
        </div>
        """

    # Reasoning
    reasoning_items = "".join(f"<li>{r}</li>" for r in report.reasoning)

    # Score bar
    score_bar = _render_score_bar(report)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{report.symbol} Analysis Report</title>
    <style>
        :root {{
            --green: #16a34a; --green-bg: #dcfce7; --green-border: #86efac;
            --red: #dc2626; --red-bg: #fee2e2; --red-border: #fca5a5;
            --yellow: #ca8a04; --yellow-bg: #fef9c3; --yellow-border: #fde047;
            --blue: #2563eb; --blue-bg: #dbeafe;
            --gray: #6b7280; --gray-bg: #f3f4f6; --gray-border: #d1d5db;
            --dark: #111827; --body-bg: #f8fafc;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px; margin: 0 auto; padding: 24px;
            color: var(--dark); background: var(--body-bg);
            line-height: 1.5; font-size: 14px;
        }}
        @media print {{ body {{ background: white; padding: 0; }} }}

        /* Header */
        .header {{
            background: white; border-radius: 12px; padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
        }}
        .header h1 {{ font-size: 28px; color: var(--dark); margin-bottom: 4px; }}
        .header .subtitle {{ color: var(--gray); font-size: 14px; }}

        /* Verdict card */
        .verdict-card {{
            border-radius: 12px; padding: 20px; text-align: center;
            margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .verdict-card.strong-buy, .verdict-card.buy {{ background: var(--green-bg); border: 2px solid var(--green-border); }}
        .verdict-card.strong-sell, .verdict-card.sell {{ background: var(--red-bg); border: 2px solid var(--red-border); }}
        .verdict-card.hold {{ background: var(--yellow-bg); border: 2px solid var(--yellow-border); }}
        .verdict-label {{ font-size: 32px; font-weight: 800; }}
        .verdict-card.strong-buy .verdict-label, .verdict-card.buy .verdict-label {{ color: var(--green); }}
        .verdict-card.strong-sell .verdict-label, .verdict-card.sell .verdict-label {{ color: var(--red); }}
        .verdict-card.hold .verdict-label {{ color: var(--yellow); }}
        .verdict-meta {{ font-size: 14px; color: var(--gray); margin-top: 8px; }}
        .verdict-meta strong {{ color: var(--dark); }}

        /* Score bar */
        .score-bar-container {{ margin: 12px auto 0; max-width: 400px; }}
        .score-bar {{ height: 8px; background: var(--gray-bg); border-radius: 4px; position: relative; }}
        .score-indicator {{ width: 12px; height: 12px; border-radius: 50%; position: absolute;
            top: -2px; border: 2px solid white; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }}
        .score-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--gray); margin-top: 4px; }}

        /* Reasoning */
        .reasoning {{
            background: white; border-radius: 12px; padding: 20px;
            margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .reasoning h2 {{ font-size: 16px; margin-bottom: 10px; color: var(--dark); }}
        .reasoning ul {{ list-style: none; padding: 0; }}
        .reasoning li {{ padding: 6px 0; border-bottom: 1px solid var(--gray-bg); font-size: 13px; }}
        .reasoning li:last-child {{ border: none; }}

        /* Sections */
        .section {{
            background: white; border-radius: 12px; padding: 20px;
            margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .section h2 {{ font-size: 16px; color: var(--blue); margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--gray-bg); }}
        .section-content {{ color: var(--gray); margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px 12px; border-bottom: 1px solid var(--gray-bg); font-size: 13px; vertical-align: top; }}
        td.key {{ font-weight: 600; color: var(--dark); width: 40%; white-space: nowrap; }}

        /* Badges */
        .badge {{
            display: inline-block; padding: 2px 10px; border-radius: 12px;
            font-size: 12px; font-weight: 600; text-transform: capitalize;
        }}
        .badge.bullish {{ background: var(--green-bg); color: var(--green); }}
        .badge.bearish {{ background: var(--red-bg); color: var(--red); }}
        .badge.neutral {{ background: var(--gray-bg); color: var(--gray); }}

        /* Risks */
        .risks-section {{ border-left: 4px solid var(--red); }}
        .risk-list {{ padding-left: 20px; }}
        .risk-list li {{ padding: 4px 0; color: var(--red); font-size: 13px; }}

        /* Disclaimer */
        .disclaimer {{
            text-align: center; color: var(--gray); font-size: 11px;
            padding: 16px; margin-top: 8px;
        }}

        /* Grid for verdict meta */
        .meta-grid {{ display: flex; justify-content: center; gap: 24px; margin-top: 12px; }}
        .meta-item {{ text-align: center; }}
        .meta-item .label {{ font-size: 11px; color: var(--gray); text-transform: uppercase; letter-spacing: 0.5px; }}
        .meta-item .value {{ font-size: 18px; font-weight: 700; color: var(--dark); }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{report.symbol} — {report.name}</h1>
        <div class="subtitle">
            Generated {report.generated_at.strftime('%B %d, %Y at %H:%M UTC')}
        </div>
    </div>

    <div class="verdict-card {verdict_cls}">
        <div class="verdict-label">{report.verdict.value}</div>
        <div class="meta-grid">
            <div class="meta-item">
                <div class="label">Price</div>
                <div class="value">${report.current_price}</div>
            </div>
            <div class="meta-item">
                <div class="label">Confidence</div>
                <div class="value">{report.confidence}</div>
            </div>
            <div class="meta-item">
                <div class="label">Risk</div>
                <div class="value">{report.risk_rating.value}/5</div>
            </div>
            <div class="meta-item">
                <div class="label">Sentiment</div>
                <div class="value">{report.sentiment_score}</div>
            </div>
        </div>
        {score_bar}
    </div>

    <div class="reasoning">
        <h2>Analysis Reasoning</h2>
        <ul>{reasoning_items}</ul>
    </div>

    {sections_html}

    {risks_html}

    <div class="disclaimer">{report.DISCLAIMER}</div>
</body>
</html>"""


def _section_icon(title: str) -> str:
    icons = {
        "Company Overview": "&#x1F3E2;",
        "Technical Analysis": "&#x1F4C8;",
        "Fundamental Analysis": "&#x1F4CA;",
        "News Sentiment": "&#x1F4F0;",
        "Macro Environment": "&#x1F30D;",
        "Smart Money": "&#x1F4B0;",
        "Congressional Trades": "&#x1F3DB;",
        "Options Flow": "&#x1F3AF;",
        "Relative Value": "&#x2696;",
        "Signal Confluence": "&#x1F500;",
    }
    for key, icon in icons.items():
        if key.lower() in title.lower():
            return icon
    return "&#x1F4CB;"


def _render_score_bar(report: Report) -> str:
    """Render a visual score bar from Strong Sell to Strong Buy."""
    # Map verdict to position (0-100)
    positions = {
        "Strong Sell": 10, "Sell": 25, "Hold": 50, "Buy": 75, "Strong Buy": 90,
    }
    pos = positions.get(report.verdict.value, 50)

    colors = {
        "Strong Sell": "var(--red)", "Sell": "#ef4444",
        "Hold": "var(--yellow)", "Buy": "#22c55e", "Strong Buy": "var(--green)",
    }
    color = colors.get(report.verdict.value, "var(--gray)")

    return f"""
    <div class="score-bar-container">
        <div class="score-bar">
            <div class="score-indicator" style="left: {pos}%; background: {color};"></div>
        </div>
        <div class="score-labels">
            <span>Strong Sell</span><span>Sell</span><span>Hold</span><span>Buy</span><span>Strong Buy</span>
        </div>
    </div>
    """
