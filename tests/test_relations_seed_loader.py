"""Tests for the supply-chain spine CSV loader."""

from __future__ import annotations

import pytest

from src.data.relations_seed_loader import (
    DEFAULT_SEED_PATH,
    SEED_EVIDENCE_PREFIX,
    VALID_RELATION_TYPES,
    load_spine,
    parse_relations_csv,
    relation_counts,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── CSV parsing ──────────────────────────────────────────────────


def test_seed_file_exists():
    assert DEFAULT_SEED_PATH.exists()


def test_parse_returns_rows():
    rows = parse_relations_csv()
    assert len(rows) >= 30, f"expected ≥30 spine rows, got {len(rows)}"


def test_parse_rejects_invalid_relation_types(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text(
        "from_symbol,to_symbol,relation_type,strength,polarity,evidence,notes\n"
        "AAA,BBB,supplier,0.5,1.0,fine,\n"
        "AAA,CCC,bogus_type,0.5,1.0,bad,\n"
    )
    rows = parse_relations_csv(csv)
    relations = {r["relation_type"] for r in rows}
    assert "supplier" in relations
    assert "bogus_type" not in relations


def test_parse_skips_self_edges():
    rows = parse_relations_csv()
    for r in rows:
        assert r["from_symbol"] != r["to_symbol"]


def test_parse_uppercases_symbols():
    rows = parse_relations_csv()
    for r in rows:
        assert r["from_symbol"] == r["from_symbol"].upper()
        assert r["to_symbol"] == r["to_symbol"].upper()


def test_strength_within_range():
    rows = parse_relations_csv()
    for r in rows:
        assert 0.0 <= r["strength"] <= 1.0


def test_polarity_within_range():
    rows = parse_relations_csv()
    for r in rows:
        assert -1.0 <= r["polarity"] <= 1.0


def test_critical_supply_chain_present():
    rows = parse_relations_csv()
    triples = {(r["from_symbol"], r["to_symbol"], r["relation_type"]) for r in rows}
    must_have = {
        ("NVDA", "TSM", "supplier"),
        ("AAPL", "TSM", "supplier"),
        ("TSM", "ASML", "supplier"),
        ("TSM", "NVDA", "customer"),
        ("ASML", "TSM", "customer"),
        ("LLY", "CVS", "customer"),
        ("SLB", "XOM", "customer"),  # SLB's customer is XOM
    }
    missing = must_have - triples
    assert not missing, f"seed missing critical supply-chain edges: {missing}"


def test_substitute_polarity_is_negative():
    """Substitute relations should have polarity -1.0 (zero-sum)."""
    rows = parse_relations_csv()
    for r in rows:
        if r["relation_type"] == "substitute":
            assert r["polarity"] == -1.0, f"substitute should be -1: {r}"


def test_relation_types_match_schema():
    rows = parse_relations_csv()
    for r in rows:
        assert r["relation_type"] in VALID_RELATION_TYPES


# ── loader behavior ─────────────────────────────────────────────


def test_load_inserts_rows():
    init_db()
    load_tier_a()
    counts = load_spine()
    assert counts["inserted"] >= 25, f"expected ≥25 spine edges loaded, got {counts}"


def test_load_writes_with_seed_evidence_prefix():
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT evidence FROM stock_relations WHERE evidence LIKE '{SEED_EVIDENCE_PREFIX}%' LIMIT 1"
        ).fetchall()
        assert rows, "no seed-tagged spine rows found"
        assert rows[0]["evidence"].startswith(SEED_EVIDENCE_PREFIX)
    finally:
        conn.close()


def test_load_idempotent_final_count():
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        n1 = conn.execute(
            f"SELECT COUNT(*) FROM stock_relations WHERE evidence LIKE '{SEED_EVIDENCE_PREFIX}%'"
        ).fetchone()[0]
    finally:
        conn.close()

    load_spine()
    conn = get_connection()
    try:
        n2 = conn.execute(
            f"SELECT COUNT(*) FROM stock_relations WHERE evidence LIKE '{SEED_EVIDENCE_PREFIX}%'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n1 == n2, f"loader not idempotent: {n1} → {n2}"


def test_load_skips_orphan_symbols():
    init_db()
    load_tier_a()
    counts = load_spine()
    # Some seed rows reference symbols that aren't in the Tier A spine yet
    # (e.g. SNPS as NVDA supplier but SNPS isn't in tier_a_seed). Loader should
    # report them as orphans, not crash.
    assert counts["skipped_orphan"] >= 0


def test_specific_edge_loaded_correctly():
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        assert row is not None, "NVDA-TSM supplier edge missing"
        assert row["strength"] >= 0.9
        assert row["polarity"] == 1.0
        assert "TSM" in (row["evidence"] or "") or "foundry" in (row["evidence"] or "").lower()
    finally:
        conn.close()


def test_substitute_edge_has_negative_polarity_in_db():
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT polarity FROM stock_relations WHERE relation_type='substitute'"
        ).fetchall()
        for r in rows:
            assert r["polarity"] < 0, f"substitute edge has wrong polarity: {r['polarity']}"
    finally:
        conn.close()


def test_relation_counts_diagnostic():
    init_db()
    load_tier_a()
    load_spine()
    counts = relation_counts()
    assert counts.get("supplier", 0) >= 5
    assert counts.get("customer", 0) >= 5
    assert counts["total"] >= 25
