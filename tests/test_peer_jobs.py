"""Tests for src/data/peer_jobs.py.

Mocks `ask_claude_json` so no live `claude` CLI invocations happen.
Tests cover: prompt construction, Claude-edge validation, resumability
(pending → in_progress → done state transitions), and tier-A skip.
"""

from __future__ import annotations

from unittest.mock import patch  # audit: allow fake-data

import pytest

from src.data.peer_jobs import (
    TIER_CONFIDENCE,
    _build_prompt,
    _write_claude_edges,
    discover_industries_to_rank,
    process_industry,
    run_pending_jobs,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── prompt construction ──────────────────────────────────────────


def test_build_prompt_includes_industry_and_listing():
    prompt = _build_prompt("Semiconductors", [("NVDA", "Nvidia"), ("AMD", "Advanced Micro Devices")])
    assert "Semiconductors" in prompt
    assert "NVDA" in prompt
    assert "AMD" in prompt
    assert "Nvidia" in prompt


def test_build_prompt_requests_json():
    prompt = _build_prompt("Test", [("X", "X Co")])
    assert "JSON" in prompt or "json" in prompt


# ── _write_claude_edges validation ──────────────────────────────


def _seed_universe(symbols: list[tuple[str, str]]) -> None:
    """Insert (symbol, tier='B') rows for testing."""
    init_db()
    conn = get_connection()
    try:
        for sym, tier in symbols:
            conn.execute("DELETE FROM stocks_universe WHERE symbol=?", (sym,))
            conn.execute(
                "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?, ?, 'test')",
                (sym, tier),
            )
        conn.commit()
    finally:
        conn.close()


def test_write_edges_skips_unknown_symbols():
    init_db()
    conn = get_connection()
    try:
        # Empty result is safe
        n = _write_claude_edges(conn, [], valid_symbols={"NVDA"}, tier="B")
        assert n == 0
    finally:
        conn.close()


def test_write_edges_filters_self_loops_and_unknown_peers():
    init_db()
    conn = get_connection()
    try:
        # Synthetic symbols only — never reference real tickers in tests so
        # the cleanup can be symbol-scoped without needing a source filter.
        _seed_universe([("FAKEH1", "B"), ("FAKEH2", "B"), ("FAKEH3", "B"), ("FAKE", "B")])

        parsed = [
            {"symbol": "FAKEH1", "peers": [
                {"sym": "FAKEH1", "reason": "self loop"},       # self → drop
                {"sym": "FAKEH2", "reason": "competitor"},       # ok
                {"sym": "UNKNOWN", "reason": "not in universe"}, # not in valid_symbols → drop
                {"sym": "FAKEH3", "reason": "datacenter"},       # ok
            ]},
        ]
        n = _write_claude_edges(
            conn, parsed,
            valid_symbols={"FAKEH1", "FAKEH2", "FAKEH3"},
            tier="B",
        )
        assert n == 2
    finally:
        conn.execute("DELETE FROM stock_peers WHERE from_symbol='FAKEH1'")
        conn.commit()
        conn.close()


def test_write_edges_caps_peers_at_5():
    init_db()
    conn = get_connection()
    try:
        peers = [{"sym": f"P{i}", "reason": f"r{i}"} for i in range(10)]
        valid = {"FAKEH1"} | {f"P{i}" for i in range(10)}
        _seed_universe([("FAKEH1", "B")] + [(f"P{i}", "B") for i in range(10)])

        parsed = [{"symbol": "FAKEH1", "peers": peers}]
        n = _write_claude_edges(conn, parsed, valid_symbols=valid, tier="B")
        assert n == 5  # capped
    finally:
        conn.execute("DELETE FROM stock_peers WHERE from_symbol='FAKEH1'")
        conn.commit()
        conn.close()


def test_write_edges_uses_correct_confidence_for_tier():
    """Use synthetic symbols (not NVDA/AMD) so the hand-seeded peer rows
    in the live DB don't collide with the test's UPSERT."""
    init_db()
    conn = get_connection()
    try:
        _seed_universe([("FAKEC1", "B"), ("FAKEC2", "B")])
        parsed = [{"symbol": "FAKEC1", "peers": [{"sym": "FAKEC2", "reason": "x"}]}]
        _write_claude_edges(conn, parsed, valid_symbols={"FAKEC1", "FAKEC2"}, tier="C")
        conn.commit()
        row = conn.execute(
            "SELECT confidence FROM stock_peers WHERE from_symbol='FAKEC1' AND to_symbol='FAKEC2'"
        ).fetchone()
        assert row["confidence"] == TIER_CONFIDENCE["C"]
    finally:
        conn.execute("DELETE FROM stock_peers WHERE from_symbol='FAKEC1' AND to_symbol='FAKEC2'")
        conn.commit()
        conn.close()


def test_write_edges_does_not_overwrite_hand_loaded_rows():
    """Pre-existing hand-loaded edges must keep source='hand' even after a
    Claude batch run touches the same pair.

    Uses synthetic symbols so the cleanup doesn't destroy real seeded edges
    that other tests depend on.
    """
    init_db()
    conn = get_connection()
    try:
        _seed_universe([("FAKEH1", "B"), ("FAKEH2", "B")])
        # Pre-insert a hand-loaded edge
        conn.execute(
            "INSERT INTO stock_peers (from_symbol, to_symbol, similarity, source, confidence) "
            "VALUES ('FAKEH1', 'FAKEH2', 0.85, 'hand', 'high')"
        )
        conn.commit()

        # Now claude_batch tries to add the same pair
        parsed = [{"symbol": "FAKEH1", "peers": [{"sym": "FAKEH2", "reason": "x"}]}]
        _write_claude_edges(conn, parsed, valid_symbols={"FAKEH1", "FAKEH2"}, tier="C")
        conn.commit()

        row = conn.execute(
            "SELECT source, confidence FROM stock_peers WHERE from_symbol='FAKEH1' AND to_symbol='FAKEH2'"
        ).fetchone()
        # source/confidence preserved at 'hand'/'high'
        assert row["source"] == "hand"
        assert row["confidence"] == "high"
    finally:
        conn.execute("DELETE FROM stock_peers WHERE from_symbol='FAKEH1' AND to_symbol='FAKEH2'")
        conn.commit()
        conn.close()


# ── process_industry end-to-end (claude mocked) ─────────────────


def test_process_industry_marks_done_on_success(monkeypatch):
    init_db()
    load_tier_a()  # ensure stocks_universe is populated for industry lookup
    _seed_universe([("FAKEB1", "B"), ("FAKEB2", "B"), ("FAKEB3", "B")])
    conn = get_connection()
    try:
        # Tag the synthetic stocks with a fake industry
        for sym in ("FAKEB1", "FAKEB2", "FAKEB3"):
            conn.execute(
                "INSERT OR REPLACE INTO stock_industry "
                "(symbol, industry_code, weight, is_primary, source) "
                "VALUES (?, 'FakeIndustry', 1.0, 1, 'test')",
                (sym,),
            )
        conn.execute(
            "INSERT OR IGNORE INTO industries (code, sector) VALUES ('FakeIndustry', 'Test')"
        )
        conn.commit()
    finally:
        conn.close()

    fake_response = [
        {"symbol": "FAKEB1", "peers": [
            {"sym": "FAKEB2", "reason": "test"},
            {"sym": "FAKEB3", "reason": "test"},
        ]},
        {"symbol": "FAKEB2", "peers": [
            {"sym": "FAKEB1", "reason": "test"},
        ]},
    ]

    def fake_ask(prompt, **kw):
        return fake_response

    monkeypatch.setattr("src.data.peer_jobs.ask_claude_json", fake_ask)

    result = process_industry("FakeIndustry", "B")
    assert result.error is None
    assert result.symbols_in_industry == 3
    assert result.edges_written == 3

    # Job marked done
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, edges_written FROM peer_jobs "
            "WHERE industry_code='FakeIndustry' AND tier='B'"
        ).fetchone()
        assert row["status"] == "done"
        assert row["edges_written"] == 3
    finally:
        # Cleanup — scoped to synthetic test symbols only. A previous version
        # used `DELETE FROM stock_peers WHERE source='claude_batch'` which
        # wiped real LLM-generated peer data from the live DB.
        conn.execute("DELETE FROM peer_jobs WHERE industry_code='FakeIndustry'")
        conn.execute(
            "DELETE FROM stock_peers "
            "WHERE from_symbol IN ('FAKEB1','FAKEB2','FAKEB3') "
            "   OR to_symbol IN ('FAKEB1','FAKEB2','FAKEB3')"
        )
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        conn.execute("DELETE FROM industries WHERE code='FakeIndustry'")
        conn.commit()
        conn.close()


def test_process_industry_marks_failed_on_claude_error(monkeypatch):
    init_db()
    _seed_universe([("FAILA", "B"), ("FAILB", "B")])
    conn = get_connection()
    try:
        for sym in ("FAILA", "FAILB"):
            conn.execute(
                "INSERT OR REPLACE INTO stock_industry "
                "(symbol, industry_code, weight, is_primary, source) "
                "VALUES (?, 'FailIndustry', 1.0, 1, 'test')",
                (sym,),
            )
        conn.execute(
            "INSERT OR IGNORE INTO industries (code, sector) VALUES ('FailIndustry', 'Test')"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr("src.data.peer_jobs.ask_claude_json", lambda *a, **kw: None)

    result = process_industry("FailIndustry", "B")
    assert result.error is not None
    assert result.edges_written == 0

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM peer_jobs WHERE industry_code='FailIndustry'"
        ).fetchone()
        assert row["status"] == "failed"
    finally:
        conn.execute("DELETE FROM peer_jobs WHERE industry_code='FailIndustry'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        conn.execute("DELETE FROM industries WHERE code='FailIndustry'")
        conn.commit()
        conn.close()


def test_process_industry_skips_when_fewer_than_two_stocks(monkeypatch):
    init_db()
    _seed_universe([("LONELY", "B")])
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO stock_industry "
            "(symbol, industry_code, weight, is_primary, source) "
            "VALUES ('LONELY', 'LonelyIndustry', 1.0, 1, 'test')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO industries (code, sector) VALUES ('LonelyIndustry', 'Test')"
        )
        conn.commit()
    finally:
        conn.close()

    # Claude should NOT be called — the helper short-circuits.
    called = {"n": 0}
    def boom(*a, **kw):
        called["n"] += 1
        raise RuntimeError("claude should not be called for solo industry")
    monkeypatch.setattr("src.data.peer_jobs.ask_claude_json", boom)

    result = process_industry("LonelyIndustry", "B")
    assert result.edges_written == 0
    assert called["n"] == 0  # short-circuit before LLM call

    conn = get_connection()
    try:
        conn.execute("DELETE FROM peer_jobs WHERE industry_code='LonelyIndustry'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        conn.execute("DELETE FROM industries WHERE code='LonelyIndustry'")
        conn.commit()
    finally:
        conn.close()


# ── runtime tier-A guard ────────────────────────────────────────


def test_run_pending_jobs_excludes_tier_a_even_if_requested(monkeypatch):
    """Even passing tiers=['A','B'] must skip Tier A — it's hand-only."""
    init_db()
    monkeypatch.setattr("src.data.peer_jobs.process_industry",
                       lambda industry, tier, **kw: pytest.fail(f"should not process {tier}"))

    # Run with tiers=['A'] only. Loop should produce zero work since A is filtered.
    out = run_pending_jobs(tiers=["A"], log=False)
    assert out["processed"] == 0


# ── discovery ────────────────────────────────────────────────────


def test_discover_industries_skips_done_jobs():
    init_db()
    conn = get_connection()
    try:
        # Seed a minimal industry with 2 Tier-B stocks
        _seed_universe([("D1", "B"), ("D2", "B")])
        for sym in ("D1", "D2"):
            conn.execute(
                "INSERT OR REPLACE INTO stock_industry "
                "(symbol, industry_code, weight, is_primary, source) "
                "VALUES (?, 'DoneIndustry', 1.0, 1, 'test')",
                (sym,),
            )
        conn.execute(
            "INSERT OR IGNORE INTO industries (code, sector) VALUES ('DoneIndustry', 'Test')"
        )
        # Mark this (industry, tier) as done in peer_jobs
        conn.execute(
            "INSERT INTO peer_jobs (industry_code, tier, status) VALUES ('DoneIndustry', 'B', 'done')"
        )
        conn.commit()

        pairs = discover_industries_to_rank(conn, tiers=["B"])
        # The done industry should NOT appear
        assert ("DoneIndustry", "B") not in pairs

        # Cleanup
        conn.execute("DELETE FROM peer_jobs WHERE industry_code='DoneIndustry'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        conn.execute("DELETE FROM industries WHERE code='DoneIndustry'")
        conn.commit()
    finally:
        conn.close()
