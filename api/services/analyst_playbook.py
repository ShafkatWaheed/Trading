"""The AI analyst's accumulated playbook (separate from momentum skills.md).

Read into both Claude stages each day; rewritten weekly from graded outcomes.
Atomic writes; a rewrite that doesn't return the version tag is rejected so a
malformed Claude response can never corrupt the playbook.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.utils.claude_cli import ask_claude

_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "predictions" / "analyst_playbook.md"
_VERSION_TAG = "<!-- analyst-playbook-v1 -->"
_TEMPLATE = f"""{_VERSION_TAG}
# AI Analyst Playbook

Accumulated, graded observations about what precedes a top-15% gainer.
Rewritten weekly from real outcomes. Empty until the first rewrite.
"""


def _ensure() -> Path:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _PATH.exists():
        _PATH.write_text(_TEMPLATE, encoding="utf-8")
    return _PATH


def read() -> str:
    """Current playbook text. Auto-creates from the template on first read."""
    _ensure()
    try:
        return _PATH.read_text(encoding="utf-8")
    except Exception:
        return _TEMPLATE


def write(content: str) -> None:
    """Atomically replace the playbook (temp file + os.replace)."""
    _ensure()
    fd, tmp = tempfile.mkstemp(dir=str(_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, _PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def rewrite(*, history, accuracy, claude=None) -> dict:
    """Ask Opus to rewrite the playbook from graded history. Atomic; rejects a
    response missing the version tag (leaves the playbook unchanged). Returns
    {"updated": bool, ...}."""
    # 600s: rewriting from a full window (dozens of graded picks) is a heavy
    # Opus generation that overruns the old 240s cap and returns empty.
    claude = claude or (lambda prompt: ask_claude(prompt, model="opus", timeout=600))
    if not history:
        return {"updated": False, "reason": "no_history"}
    prompt = _build_prompt(read(), history, accuracy)
    new = (claude(prompt) or "").strip()
    if not new:
        # Empty = subprocess timeout / non-zero exit, NOT a malformed response.
        return {"updated": False, "reason": "empty_response_or_timeout"}
    if _VERSION_TAG not in new:
        return {"updated": False, "reason": "missing_version_tag"}
    write(new[new.find(_VERSION_TAG):])   # trim any preamble before the tag
    return {"updated": True, "bytes": len(new)}


def _build_prompt(current: str, history, accuracy) -> str:
    """Compose the rewrite prompt: current playbook + graded history + accuracy,
    instructing Opus to return the FULL markdown starting with the version tag."""
    import json
    return (
        "You maintain an AI stock-analyst PLAYBOOK (markdown). Rewrite it IN FULL "
        "from the graded outcomes below — keep durable lessons, add new ones, drop "
        "disproven ones. Be concrete about which signal combinations preceded "
        "top-15% gainers.\n\n"
        f"Your response MUST begin with this exact line:\n{_VERSION_TAG}\n\n"
        f"CURRENT PLAYBOOK:\n{current}\n\n"
        f"ROLLING ACCURACY:\n{json.dumps(accuracy, default=str)}\n\n"
        f"GRADED HISTORY (recent predictions + outcomes):\n{json.dumps(history, default=str)}\n"
    )
