"""Plain-language earnings report explainer.

User pastes raw earnings text (release, transcript, press blurb); Claude returns
a structured breakdown: summary, what beat, what missed, forward guidance,
and whether the investment case changes.
"""
from __future__ import annotations

from src.utils.claude_cli import ask_claude_json

_MAX_INPUT_CHARS = 12_000


def explain_earnings(symbol: str, text: str) -> dict:
    symbol = (symbol or "").upper().strip()
    body = (text or "").strip()
    if not body:
        return {"symbol": symbol, "error": "Empty report text."}
    if len(body) > _MAX_INPUT_CHARS:
        body = body[:_MAX_INPUT_CHARS] + "\n...[truncated]"

    prompt = (
        f"You are a senior equity analyst. Read this earnings report for {symbol or 'the company'} "
        f"and produce a JSON object with EXACTLY these keys:\n"
        f"  summary           : 2-3 sentence plain-language overview\n"
        f"  beats             : array of 1-5 short bullets — what BEAT expectations\n"
        f"  misses            : array of 0-5 short bullets — what MISSED expectations\n"
        f"  guidance          : 1-2 sentences — what management said about the future\n"
        f"  case_change       : ONE of \"strengthens\" / \"weakens\" / \"unchanged\"\n"
        f"  case_change_reason: 1 sentence explaining the case_change verdict\n"
        f"\n"
        f"Reply with JSON ONLY — no markdown fences, no commentary.\n"
        f"\n"
        f"=== REPORT ===\n{body}\n=== END ===\n"
    )

    parsed = ask_claude_json(prompt, model="haiku", timeout=60, retries=2)
    if not isinstance(parsed, dict):
        return {
            "symbol": symbol,
            "error": "Could not parse Claude response.",
        }

    def _str_list(v) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()][:5]
        return []

    return {
        "symbol": symbol,
        "summary": str(parsed.get("summary") or "").strip(),
        "beats": _str_list(parsed.get("beats")),
        "misses": _str_list(parsed.get("misses")),
        "guidance": str(parsed.get("guidance") or "").strip(),
        "case_change": str(parsed.get("case_change") or "unchanged").lower().strip(),
        "case_change_reason": str(parsed.get("case_change_reason") or "").strip(),
        "input_chars": len(body),
    }
