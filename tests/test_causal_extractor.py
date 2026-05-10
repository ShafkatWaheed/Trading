"""Tests for src/data/causal_extractor.py — Phase 6 LLM-driven exposure mining.

Both yfinance summary fetch and the Claude CLI are mocked via injection.
"""

from __future__ import annotations

import pytest

from src.data.causal_extractor import (
    _build_prompt,
    _write_extracted_exposures,
    process_symbol,
)
from src.data.commodity_seed_loader import load_commodities
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_phase6():
    init_db()
    load_tier_a()
    load_commodities()


# ── prompt construction ──────────────────────────────────────────


def test_prompt_includes_symbol_and_summary():
    prompt = _build_prompt("NVDA", "NVIDIA Corp", "We make GPUs.", ["copper", "rare_earths"])
    assert "NVDA" in prompt
    assert "NVIDIA" in prompt
    assert "GPUs" in prompt


def test_prompt_lists_commodity_catalogue():
    prompt = _build_prompt("XOM", "Exxon", "Oil major.", ["crude_oil", "natural_gas", "gasoline"])
    assert "crude_oil" in prompt
    assert "natural_gas" in prompt


def test_prompt_truncates_long_summary():
    long_summary = "A" * 10_000
    prompt = _build_prompt("X", "X Co", long_summary, ["copper"])
    # Summary truncated to 3500 chars + frame
    assert prompt.count("A") < 5_000


def test_prompt_handles_empty_summary():
    prompt = _build_prompt("X", "X Co", "", ["copper"])
    assert "no business description" in prompt.lower()


# ── _write_extracted_exposures ───────────────────────────────────


def test_writes_input_and_output_exposures():
    init_db()
    conn = get_connection()
    try:
        # Use synthetic source stock to avoid colliding with the hand seed
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_C1'")
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_C1'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_C1', 'B', 'test')"
        )
        conn.commit()

        parsed = {
            "commodity_inputs": [
                {"commodity": "crude_oil", "polarity": -1, "elasticity": 0.6, "evidence": "fuel"},
            ],
            "commodity_outputs": [
                {"commodity": "gasoline", "polarity": 1, "elasticity": 0.5, "evidence": "refined"},
            ],
        }
        valid = {"crude_oil", "gasoline"}
        n = _write_extracted_exposures(conn, symbol="SYN_C1", parsed=parsed, valid_codes=valid)
        conn.commit()
        assert n == 2

        rows = conn.execute(
            "SELECT role, polarity, elasticity, source FROM stock_commodity_exposure "
            "WHERE symbol='SYN_C1' ORDER BY role"
        ).fetchall()
        roles = {r["role"] for r in rows}
        assert roles == {"input", "output"}
        for r in rows:
            assert r["source"] == "claude"
    finally:
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_C1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_C1'")
        conn.commit()
        conn.close()


def test_skips_unknown_commodity_codes():
    init_db()
    conn = get_connection()
    try:
        parsed = {
            "commodity_inputs": [
                {"commodity": "totally_made_up", "polarity": -1, "elasticity": 0.5, "evidence": "x"},
            ],
            "commodity_outputs": [],
        }
        n = _write_extracted_exposures(
            conn, symbol="ANY", parsed=parsed, valid_codes={"crude_oil"}
        )
        assert n == 0
    finally:
        conn.close()


def test_skips_low_elasticity():
    init_db()
    conn = get_connection()
    try:
        parsed = {
            "commodity_inputs": [
                {"commodity": "crude_oil", "polarity": -1, "elasticity": 0.05, "evidence": "trivial"},
            ],
            "commodity_outputs": [],
        }
        n = _write_extracted_exposures(
            conn, symbol="ANY", parsed=parsed, valid_codes={"crude_oil"}
        )
        assert n == 0
    finally:
        conn.close()


def test_does_not_overwrite_hand_loaded_exposures():
    """Hand-loaded XOM crude_oil output must NOT get clobbered by Claude."""
    from src.data.commodity_seed_loader import load_exposures
    init_db()
    load_tier_a()
    load_commodities()
    load_exposures()

    conn = get_connection()
    try:
        before = conn.execute(
            "SELECT polarity, elasticity, source, evidence "
            "FROM stock_commodity_exposure WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert before is not None
        assert before["source"] == "hand"

        # Now Claude tries to write a different value for the same row
        parsed = {
            "commodity_inputs": [],
            "commodity_outputs": [
                {"commodity": "crude_oil", "polarity": 1, "elasticity": 0.30, "evidence": "claude says modest"},
            ],
        }
        _write_extracted_exposures(
            conn, symbol="XOM", parsed=parsed,
            valid_codes={"crude_oil"},
        )
        conn.commit()

        after = conn.execute(
            "SELECT polarity, elasticity, source, evidence "
            "FROM stock_commodity_exposure WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        # Hand source preserved
        assert after["source"] == "hand"
        # Hand elasticity preserved (should be 0.85, not 0.30)
        assert after["elasticity"] >= 0.7
    finally:
        conn.close()


# ── process_symbol end-to-end (mocked) ───────────────────────────


def test_process_symbol_marks_done_on_success():
    init_db()
    load_tier_a()
    load_commodities()

    def fake_fetch(sym):
        return ("Fake Co", "We make industrial machinery from steel and copper.")

    def fake_extract(prompt, **kw):
        return {
            "commodity_inputs": [
                {"commodity": "steel", "polarity": -1, "elasticity": 0.40, "evidence": "frame"},
                {"commodity": "copper", "polarity": -1, "elasticity": 0.20, "evidence": "wiring"},
            ],
            "commodity_outputs": [],
        }

    # Use a synthetic Tier-B stock so we don't collide with hand seed
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_PROC'")
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_PROC'")
        conn.execute("DELETE FROM causal_jobs WHERE symbol='SYN_PROC'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_PROC', 'B', 'test')"
        )
        conn.commit()
    finally:
        conn.close()

    out = process_symbol("SYN_PROC", fetch_summary_fn=fake_fetch, extract_fn=fake_extract)
    assert out["error"] is None
    assert out["edges_written"] == 2

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, edges_written FROM causal_jobs WHERE symbol='SYN_PROC'"
        ).fetchone()
        assert row["status"] == "done"
        assert row["edges_written"] == 2
    finally:
        conn.execute("DELETE FROM causal_jobs WHERE symbol='SYN_PROC'")
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_PROC'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_PROC'")
        conn.commit()
        conn.close()


def test_process_symbol_marks_failed_when_summary_missing():
    init_db()

    def fake_fetch(sym):
        return (None, None)

    out = process_symbol("MSFT", fetch_summary_fn=fake_fetch)
    assert out["error"] == "no_summary"

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM causal_jobs WHERE symbol='MSFT'"
        ).fetchone()
        assert row["status"] == "failed"
    finally:
        conn.execute("DELETE FROM causal_jobs WHERE symbol='MSFT'")
        conn.commit()
        conn.close()


def test_process_symbol_marks_failed_when_extract_returns_none():
    init_db()

    def fake_fetch(sym):
        return ("Fake", "Some business summary.")

    def fake_extract(prompt, **kw):
        return None

    out = process_symbol("AMZN", fetch_summary_fn=fake_fetch, extract_fn=fake_extract)
    assert out["error"] == "extraction_failed"

    conn = get_connection()
    try:
        row = conn.execute("SELECT status FROM causal_jobs WHERE symbol='AMZN'").fetchone()
        assert row["status"] == "failed"
    finally:
        conn.execute("DELETE FROM causal_jobs WHERE symbol='AMZN'")
        conn.commit()
        conn.close()
