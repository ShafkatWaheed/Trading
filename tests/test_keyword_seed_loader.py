"""Tests for the keyword_impact CSV seed loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.keyword_seed_loader import (
    DEFAULT_SEED_PATH,
    SEED_NOTES_PREFIX,
    keyword_impact_counts,
    load_keyword_impact,
    parse_seed_csv,
)
from src.utils.db import get_connection, init_db


# ── CSV parsing ────────────────────────────────────────────────────


def test_seed_csv_exists():
    assert DEFAULT_SEED_PATH.exists(), f"missing seed file: {DEFAULT_SEED_PATH}"


def test_parse_seed_csv_returns_rows():
    rows = parse_seed_csv()
    assert len(rows) >= 100, f"expected ≥100 keyword rows, got {len(rows)}"


def test_parse_normalises_keyword_to_lowercase():
    rows = parse_seed_csv()
    for r in rows:
        assert r["keyword"] == r["keyword"].lower(), f"keyword not lowercased: {r['keyword']!r}"


def test_every_row_has_industry_or_target_stock():
    rows = parse_seed_csv()
    for r in rows:
        assert (r["industry_code"] is not None) or (r["target_stock"] is not None), \
            f"row missing both industry and target_stock: {r}"


def test_polarity_within_range():
    rows = parse_seed_csv()
    for r in rows:
        assert -1.0 <= r["polarity"] <= 1.0, \
            f"polarity out of range: {r['keyword']} = {r['polarity']}"


def test_weight_within_range():
    rows = parse_seed_csv()
    for r in rows:
        assert 0.0 <= r["weight"] <= 1.0, \
            f"weight out of range: {r['keyword']} = {r['weight']}"


def test_seed_covers_required_domains():
    rows = parse_seed_csv()
    domains = {r["domain"] for r in rows if r["domain"]}
    required = {
        "ai", "oil", "war", "tariff", "rates", "fda", "court",
        "glp1", "crypto", "climate", "mining", "demo", "strike",
    }
    missing = required - domains
    assert not missing, f"seed missing required domains: {missing}"


def test_critical_keywords_present():
    rows = parse_seed_csv()
    keywords = {r["keyword"] for r in rows}
    must_have = {
        "ai", "gpu", "data center",
        "oil", "gas", "fertilizer",
        "war", "missile", "defense",
        "tariff", "trade war",
        "rate cut", "rate hike",
        "fda approves", "fda rejects",
        "antitrust",
        "glp-1", "weight loss",
        "hurricane", "wildfire",
        "copper", "uranium", "gold",
    }
    missing = must_have - keywords
    assert not missing, f"seed missing critical keywords: {missing}"


# ── Loader behaviour ───────────────────────────────────────────────


def test_load_keyword_impact_inserts_rows():
    init_db()
    counts = load_keyword_impact()
    assert counts["inserted"] >= 100
    assert counts["skipped"] == 0


def test_load_keyword_impact_idempotent():
    """Running twice replaces seed rows but does not duplicate them."""
    init_db()
    first = load_keyword_impact()
    second = load_keyword_impact()
    # Second run deletes the previous seed-tagged rows then re-inserts.
    assert second["deleted"] == first["inserted"]
    assert second["inserted"] == first["inserted"]


def test_loaded_rows_are_tagged_with_seed_prefix():
    init_db()
    load_keyword_impact()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT keyword, notes FROM keyword_impact WHERE notes LIKE '{SEED_NOTES_PREFIX}%'"
        ).fetchall()
        assert len(rows) >= 100
        for r in rows:
            assert r["notes"].startswith(SEED_NOTES_PREFIX)
    finally:
        conn.close()


def test_load_does_not_touch_non_seed_rows():
    """Manually-inserted rows (notes NOT starting with seed:hand) survive a re-load."""
    init_db()
    load_keyword_impact()
    conn = get_connection()
    try:
        # Insert a "manual" row outside the seed-loaded set.
        conn.execute(
            "INSERT INTO keyword_impact (keyword, industry_code, polarity, weight, domain, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("__test_manual__", "Semiconductors", 0.5, 0.5, "test", "manual_test_row"),
        )
        conn.commit()

        # Reload seed; manual row should still exist.
        load_keyword_impact()
        row = conn.execute(
            "SELECT * FROM keyword_impact WHERE keyword='__test_manual__'"
        ).fetchone()
        assert row is not None
        assert row["notes"] == "manual_test_row"

        # Cleanup
        conn.execute("DELETE FROM keyword_impact WHERE keyword='__test_manual__'")
        conn.commit()
    finally:
        conn.close()


def test_keyword_impact_counts_breakdown():
    init_db()
    load_keyword_impact()
    counts = keyword_impact_counts()
    assert counts["total"] >= 100
    # Each major domain should have at least 5 rows
    for domain in ("ai", "oil", "war", "tariff", "rates", "climate"):
        assert counts.get(domain, 0) >= 5, f"domain '{domain}' under-represented: {counts.get(domain, 0)}"


def test_orphan_rows_are_skipped(tmp_path):
    """A CSV row with no industry AND no target_stock should be skipped, not crash."""
    csv = tmp_path / "orphan.csv"
    csv.write_text(
        "keyword,industry_code,target_stock,polarity,weight,domain,notes\n"
        "valid_row,Semiconductors,,0.5,0.5,test,fine\n"
        "orphan_row,,,0.5,0.5,test,no industry no target\n"
    )
    rows = parse_seed_csv(csv)
    keywords = {r["keyword"] for r in rows}
    assert "valid_row" in keywords
    assert "orphan_row" not in keywords
