"""Shared wrapper around the Claude CLI subprocess pattern.

The project uses the Claude Code CLI (authenticated via the user's
subscription) instead of the Anthropic API. This was the pattern at
[api/services/ai_analyst_service.py:51](api/services/ai_analyst_service.py#L51);
this module factors it out so every consumer (peer_jobs, causal_extractor,
sec_10k_extractor, etc.) shares the same plumbing.

API
---

ask_claude(prompt, model='haiku', timeout=60) -> str | None
    Single-shot text invocation. Returns stdout (stripped) on success, None on any error.

ask_claude_json(prompt, *, model='haiku', retries=2) -> dict | list | None
    Wraps ask_claude with JSON-extraction + retry. Tolerates models that
    wrap their JSON in markdown fences ```json``` or include a preface.
    Returns the parsed structure on success, None after all retries.
"""

from __future__ import annotations

import json
import os
import re
import subprocess


CLAUDE_BIN = "claude"


def ask_claude(
    prompt: str,
    *,
    model: str = "haiku",
    timeout: int = 60,
    allowed_tools: str = "",
) -> str | None:
    """Invoke `claude -p prompt --model <model>` and return stdout.

    Returns None on subprocess failure (non-zero exit, timeout, missing CLI).
    `allowed_tools=""` locks the call to text-only — no shell, web, or file
    side effects allowed during the model's response.
    """
    env = os.environ.copy()
    # Avoid recursion when this runs INSIDE another Claude Code session.
    env.pop("CLAUDECODE", None)
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", model, "--allowedTools", allowed_tools],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


# ── JSON extraction helpers ────────────────────────────────────────


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json_block(text: str) -> str | None:
    """Pull the JSON payload out of a possibly-wrapped model response.

    Handles three common shapes:
      1. Plain JSON object/array
      2. ```json …``` markdown fence
      3. Preface text + JSON (uses outermost {…} or […])
    Returns the JSON substring, or None if none found.
    """
    if not text:
        return None
    text = text.strip()

    # 1. Direct
    if text.startswith("{") or text.startswith("["):
        return text

    # 2. Fenced
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()

    # 3. First {…} or […] in the text
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        i = text.find(open_ch)
        j = text.rfind(close_ch)
        if i != -1 and j != -1 and j > i:
            return text[i:j + 1]

    return None


def ask_claude_json(
    prompt: str,
    *,
    model: str = "haiku",
    timeout: int = 60,
    retries: int = 2,
) -> dict | list | None:
    """Invoke Claude expecting a JSON response. Parses + validates.

    Strategy: call `ask_claude`, attempt JSON extraction, parse. If parsing
    fails, retry up to `retries` more times with a stricter prompt suffix.

    Returns the parsed dict/list, or None after all retries.
    """
    suffix = "\n\nRespond ONLY with valid JSON. No prose, no markdown fences, no commentary."

    for attempt in range(retries + 1):
        # Add the strict-JSON suffix on retry attempts to nudge a clean response.
        full_prompt = prompt if attempt == 0 else (prompt + suffix)
        raw = ask_claude(full_prompt, model=model, timeout=timeout)
        if not raw:
            continue
        block = _extract_json_block(raw)
        if not block:
            continue
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue
    return None
