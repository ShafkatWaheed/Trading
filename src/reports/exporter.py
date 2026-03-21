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


def _render_html(report: Report) -> str:
    sections_html = ""
    for section in report.sections:
        data_rows = ""
        for key, val in section.data.items():
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            data_rows += f"<tr><td><strong>{key}</strong></td><td>{val}</td></tr>\n"

        sections_html += f"""
        <div class="section">
            <h2>{section.title}</h2>
            <p>{section.content}</p>
            <table>{data_rows}</table>
        </div>
        """

    risks_html = "".join(f"<li>{r}</li>" for r in report.risks)
    reasoning_html = "".join(f"<li>{r}</li>" for r in report.reasoning)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{report.symbol} Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #1a1a1a; }}
        h1 {{ border-bottom: 3px solid #2563eb; padding-bottom: 10px; }}
        h2 {{ color: #2563eb; margin-top: 30px; }}
        .verdict {{ font-size: 24px; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; }}
        .verdict.buy {{ background: #dcfce7; color: #166534; }}
        .verdict.sell {{ background: #fee2e2; color: #991b1b; }}
        .verdict.hold {{ background: #fef9c3; color: #854d0e; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        td {{ padding: 8px; border-bottom: 1px solid #e5e7eb; }}
        .meta {{ color: #6b7280; font-size: 14px; }}
        .disclaimer {{ background: #f3f4f6; padding: 10px; border-radius: 4px; font-size: 12px; color: #6b7280; margin-top: 30px; }}
        .risks {{ background: #fef2f2; padding: 15px; border-radius: 8px; }}
    </style>
</head>
<body>
    <h1>{report.symbol} — {report.name}</h1>
    <p class="meta">Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')} | Price: ${report.current_price}</p>

    <div class="verdict {'buy' if 'Buy' in report.verdict.value else 'sell' if 'Sell' in report.verdict.value else 'hold'}">
        <strong>{report.verdict.value}</strong> — Confidence: {report.confidence} | Risk: {report.risk_rating.value}/5
    </div>

    <h2>Reasoning</h2>
    <ul>{reasoning_html}</ul>

    {sections_html}

    <div class="risks">
        <h2>Key Risks</h2>
        <ul>{risks_html}</ul>
    </div>

    <div class="disclaimer">{report.DISCLAIMER}</div>
</body>
</html>"""
