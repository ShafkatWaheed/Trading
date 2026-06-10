"""ask_claude must pipe the prompt via stdin, not as an argv element.

Linux caps a single argument at MAX_ARG_STRLEN (128 KiB); a large prompt
(e.g. a full-universe table) passed as argv raises OSError and the call
silently returns None. Passing it on stdin avoids that limit. This test
locks in the stdin behavior without touching the network.
"""
from src.utils import claude_cli


def test_ask_claude_passes_prompt_via_stdin_not_argv(monkeypatch):
    captured = {}

    class _Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["input"] = kw.get("input")
        return _Proc()

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)

    big = "HUGE PROMPT " * 20000  # ~240 KB — would blow MAX_ARG_STRLEN as argv
    out = claude_cli.ask_claude(big, model="opus", timeout=5)

    assert out == "ok"
    # The prompt goes on stdin...
    assert captured["input"] == big
    # ...and NEVER appears as a command-line argument.
    assert not any("HUGE PROMPT" in str(a) for a in captured["cmd"])
    # model/tool flags still passed.
    assert "--model" in captured["cmd"] and "opus" in captured["cmd"]
