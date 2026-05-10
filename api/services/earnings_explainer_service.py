"""Plain-language earnings report explainer.

User pastes raw earnings text (release, transcript, press blurb); Claude returns
a structured breakdown: summary, what beat, what missed, forward guidance,
and whether the investment case changes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

_TIMEOUT_SECONDS = 60
_MAX_INPUT_CHARS = 12_000


def _ask_claude(prompt: str) -> str | None:
    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
            capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, env=env,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


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

    raw = _ask_claude(prompt)
    parsed = _extract_json(raw) if raw else None
    if not parsed:
        return {
            "symbol": symbol,
            "error": "Could not parse Claude response.",
            "raw": (raw or "")[:500],
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
