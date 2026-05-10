"""Tests for src/utils/claude_cli.py.

Mocks `subprocess.run` so no live `claude` invocations happen during tests.
"""

from __future__ import annotations

from unittest.mock import patch  # audit: allow fake-data

import pytest

from src.utils.claude_cli import (
    _extract_json_block,
    ask_claude,
    ask_claude_json,
)


# ── _extract_json_block edge cases ────────────────────────────────


def test_extract_direct_json_object():
    assert _extract_json_block('{"a": 1}') == '{"a": 1}'


def test_extract_direct_json_array():
    assert _extract_json_block('[1, 2, 3]') == '[1, 2, 3]'


def test_extract_fenced_json():
    text = """Here you go:
```json
{"sym": "NVDA"}
```
"""
    out = _extract_json_block(text)
    assert out == '{"sym": "NVDA"}'


def test_extract_fenced_json_no_lang_marker():
    text = "```\n[1,2,3]\n```"
    assert _extract_json_block(text) == "[1,2,3]"


def test_extract_object_from_prefaced_text():
    text = 'Sure! Here is the JSON: {"ok": true} hope this helps'
    assert _extract_json_block(text) == '{"ok": true}'


def test_extract_returns_none_for_no_json():
    assert _extract_json_block("just some text") is None


def test_extract_returns_none_for_empty():
    assert _extract_json_block("") is None
    assert _extract_json_block(None) is None  # type: ignore[arg-type]


# ── ask_claude (subprocess mocked) ────────────────────────────────


class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_ask_claude_returns_stdout_on_success(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(0, stdout="  hello world  \n")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    out = ask_claude("test prompt")
    assert out == "hello world"


def test_ask_claude_returns_none_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(1, stdout="", stderr="error")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    assert ask_claude("test prompt") is None


def test_ask_claude_returns_none_on_empty_stdout(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(0, stdout="   \n  ")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    assert ask_claude("test prompt") is None


def test_ask_claude_returns_none_on_missing_binary(monkeypatch):
    def boom(cmd, **kw):
        raise FileNotFoundError("claude binary not found")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", boom)
    assert ask_claude("test prompt") is None


def test_ask_claude_returns_none_on_timeout(monkeypatch):
    import subprocess

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 60))

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", boom)
    assert ask_claude("test prompt") is None


def test_ask_claude_passes_model_arg(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _FakeProc(0, stdout="ok")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    ask_claude("hi", model="sonnet")
    assert "sonnet" in captured["cmd"]


# ── ask_claude_json ──────────────────────────────────────────────


def test_ask_claude_json_parses_clean_response(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(0, stdout='{"sym": "NVDA", "n": 5}')

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    out = ask_claude_json("prompt")
    assert out == {"sym": "NVDA", "n": 5}


def test_ask_claude_json_unwraps_markdown_fence(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(0, stdout='```json\n{"a": 1}\n```')

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    out = ask_claude_json("prompt")
    assert out == {"a": 1}


def test_ask_claude_json_retries_on_parse_failure(monkeypatch):
    """First call returns non-JSON; second call returns valid JSON."""
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeProc(0, stdout="this is not json at all")
        return _FakeProc(0, stdout='[1, 2, 3]')

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    out = ask_claude_json("prompt", retries=2)
    assert out == [1, 2, 3]
    assert calls["n"] == 2  # took two attempts


def test_ask_claude_json_returns_none_after_all_retries_fail(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(0, stdout="never going to be json")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    out = ask_claude_json("prompt", retries=1)
    assert out is None


def test_ask_claude_json_returns_none_on_subprocess_failure(monkeypatch):
    def fake_run(cmd, **kw):
        return _FakeProc(1, stderr="error")

    monkeypatch.setattr("src.utils.claude_cli.subprocess.run", fake_run)
    out = ask_claude_json("prompt")
    assert out is None
