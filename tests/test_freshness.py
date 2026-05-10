"""Tests for the 5-layer edge-freshness system (Phase 7B)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import freshness_service
from src.freshness.correlation_drift import (
    DEFAULT_DRIFT_THRESHOLD,
    detect_drift,
    average_correlation,
)
from src.freshness.decay import (
    DEFAULT_HALF_LIFE_DAYS,
    effective_confidence,
    is_stale,
)
from src.freshness.filing_trigger import detect_new_filings
from src.freshness.hash_diff import business_summary_hash, detect_hash_change
from src.freshness.news_drift import detect_news_drift
from src.freshness.orchestrator import (
    acknowledge,
    flag_stale_via_decay,
    queue_for_review,
    run_layer_2_hash_diff,
    run_layer_3_filing_trigger,
)
from src.news.aggregate import KeywordImpactRow
from src.utils.db import get_connection, init_db


# ── Layer 1: decay ────────────────────────────────────────────────


def test_effective_confidence_decays_to_half_at_half_life():
    """At exactly one half-life, confidence should be 0.5 × base."""
    base = 1.0
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)
    half_life = 540
    as_of = now - timedelta(days=half_life)
    out = effective_confidence(base, as_of, half_life_days=half_life, now=now)
    assert abs(out - 0.5) < 0.001


def test_effective_confidence_freshly_extracted_is_full():
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)
    out = effective_confidence(1.0, now, now=now)
    assert abs(out - 1.0) < 0.001


def test_effective_confidence_handles_iso_string():
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)
    iso = (now - timedelta(days=270)).isoformat()
    out = effective_confidence(1.0, iso, now=now)
    # 270 days = half a half-life → 1 / sqrt(2) ≈ 0.707
    assert 0.65 < out < 0.75


def test_effective_confidence_returns_zero_for_none():
    assert effective_confidence(1.0, None) == 0.0


def test_effective_confidence_returns_zero_for_invalid_timestamp():
    assert effective_confidence(1.0, "not a date") == 0.0


def test_is_stale_true_after_threshold_passed():
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)
    old = now - timedelta(days=600)         # > one half-life ago
    assert is_stale(old, now=now)


def test_is_stale_false_for_fresh_edge():
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)
    fresh = now - timedelta(days=30)
    assert not is_stale(fresh, now=now)


# ── Layer 2: hash diff ────────────────────────────────────────────


def test_business_summary_hash_is_stable_for_same_text():
    a = business_summary_hash("Acme Corp makes widgets.")
    b = business_summary_hash("Acme Corp makes widgets.")
    assert a == b


def test_business_summary_hash_normalises_whitespace():
    a = business_summary_hash("Acme Corp makes widgets.")
    b = business_summary_hash("  Acme   Corp\nmakes\t\twidgets.  ")
    assert a == b


def test_business_summary_hash_changes_when_text_changes():
    a = business_summary_hash("Acme Corp makes widgets.")
    b = business_summary_hash("Acme Corp makes gadgets.")
    assert a != b


def test_detect_hash_change_first_run_is_not_a_change():
    """The first call sets the baseline; it shouldn't report a change."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_HASH'")
        conn.commit()
    finally:
        conn.close()

    out = detect_hash_change("SYN_HASH", fetch_fn=lambda s: "Initial summary")
    assert out["changed"] is False
    assert out["previous_hash"] is None
    assert out["current_hash"] is not None


def test_detect_hash_change_subsequent_change_detected():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_HASH2'")
        conn.commit()
    finally:
        conn.close()

    detect_hash_change("SYN_HASH2", fetch_fn=lambda s: "Original text")
    out = detect_hash_change("SYN_HASH2", fetch_fn=lambda s: "Different text now")
    assert out["changed"] is True
    assert out["previous_hash"] != out["current_hash"]


def test_detect_hash_change_handles_no_summary():
    out = detect_hash_change("SYN_HASH3", fetch_fn=lambda s: None)
    assert out["error"] == "no_summary"


# ── Layer 3: filing trigger ──────────────────────────────────────


def test_detect_new_filings_first_run_returns_all_watched():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_FILING'")
        conn.commit()
    finally:
        conn.close()

    def fake_filings(sym):
        return [
            {"form": "10-K", "filed_at": "2026-04-01"},
            {"form": "10-Q", "filed_at": "2026-02-15"},
            {"form": "S-1", "filed_at": "2026-03-01"},   # NOT in watched set
        ]

    out = detect_new_filings("SYN_FILING", fetch_fn=fake_filings)
    forms = {f["form"] for f in out["new_filings"]}
    # Only watched forms surface
    assert forms == {"10-K", "10-Q"}


def test_detect_new_filings_subsequent_call_has_no_new_unless_filings_post_check():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_FILING2'")
        conn.commit()
    finally:
        conn.close()

    def fake_filings(sym):
        return [{"form": "10-K", "filed_at": "2026-04-01"}]

    detect_new_filings("SYN_FILING2", fetch_fn=fake_filings)
    out = detect_new_filings("SYN_FILING2", fetch_fn=fake_filings)
    # Same filings, second call → no new filings (last_filing_check is now > all)
    assert out["new_filings"] == []


def test_detect_new_filings_handles_empty():
    out = detect_new_filings("SYN_FILING3", fetch_fn=lambda s: [])
    assert out["error"] == "no_filings"


# ── Layer 4: correlation drift ───────────────────────────────────


def test_average_correlation_empty_peers_returns_none():
    assert average_correlation([1, 2, 3], []) is None


def test_average_correlation_perfect_positive():
    target = [1, 2, 3, 4, 5]
    peers = [[1, 2, 3, 4, 5], [2, 4, 6, 8, 10]]   # both perfectly correlated
    out = average_correlation(target, peers)
    assert abs(out - 1.0) < 0.01


def test_detect_drift_no_change_returns_drifted_false():
    """Baseline corr ≈ recent corr → no drift."""
    target = [1, 2, 3, 4, 5, 4, 3, 2, 1, 2]
    peers = [[2, 4, 6, 8, 10, 8, 6, 4, 2, 4], [1.5, 3, 4.5, 6, 7.5, 6, 4.5, 3, 1.5, 3]]
    out = detect_drift(
        "X",
        baseline_target=target, baseline_peers=peers,
        recent_target=target, recent_peers=peers,
    )
    assert out.drifted is False


def test_detect_drift_drop_above_threshold_flags():
    """Baseline strongly correlated, recent uncorrelated → drift > threshold."""
    correlated = [1, 2, 3, 4, 5, 4, 3, 2, 1, 2]
    uncorrelated_peer = [1, -1, 1, -1, 1, -1, 1, -1, 1, -1]

    out = detect_drift(
        "PLTR",
        baseline_target=correlated,
        baseline_peers=[correlated],            # perfect correlation = 1.0
        recent_target=correlated,
        recent_peers=[uncorrelated_peer],       # ~0 correlation
    )
    assert out.drift is not None
    assert out.drift > DEFAULT_DRIFT_THRESHOLD
    assert out.drifted is True


# ── Layer 5: news drift ──────────────────────────────────────────


def test_detect_news_drift_no_articles_returns_no_drift():
    out = detect_news_drift(
        "NVDA",
        headlines=[],
        impact_rows=[],
        keyword_set=set(),
        universe=set(),
        current_industry_domains={"ai"},
    )
    assert out.drifted is False
    assert out.dominant_domain is None


def test_detect_news_drift_dominant_domain_aligned_does_not_drift():
    rows = [
        KeywordImpactRow("ai", "Semiconductors", None, 1.0, 0.9, "ai"),
    ]
    out = detect_news_drift(
        "NVDA",
        headlines=["AI booms again", "AI capex accelerates", "AI demand soars"],
        impact_rows=rows,
        keyword_set={"ai"},
        universe={"NVDA"},
        current_industry_domains={"ai"},
    )
    assert out.dominant_domain == "ai"
    assert out.drifted is False


def test_detect_news_drift_dominant_domain_misaligned_flags():
    """Stock tagged as 'oil', but recent news is dominated by 'ai' domain → drift."""
    rows = [
        KeywordImpactRow("ai", "Semiconductors", None, 1.0, 0.9, "ai"),
    ]
    out = detect_news_drift(
        "PLTR",
        headlines=["AI booms again", "AI capex accelerates", "AI demand soars"],
        impact_rows=rows,
        keyword_set={"ai"},
        universe={"PLTR"},
        current_industry_domains={"defense"},
    )
    assert out.dominant_domain == "ai"
    assert out.drifted is True


# ── Orchestrator + queue ─────────────────────────────────────────


def test_queue_for_review_creates_or_updates_row():
    init_db()
    queue_for_review("SYN_Q1", reason="test_reason")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, trigger_reason FROM edge_freshness WHERE symbol='SYN_Q1'"
        ).fetchone()
        assert row["status"] == "needs_review"
        assert row["trigger_reason"] == "test_reason"
    finally:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_Q1'")
        conn.commit()
        conn.close()


def test_acknowledge_re_extract_clears_queue():
    init_db()
    queue_for_review("SYN_Q2", reason="test")
    out = acknowledge("SYN_Q2", action="re_extract")
    assert out["ok"] is True
    assert out["new_status"] == "fresh"

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, trigger_reason FROM edge_freshness WHERE symbol='SYN_Q2'"
        ).fetchone()
        assert row["status"] == "fresh"
        assert row["trigger_reason"] is None
    finally:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_Q2'")
        conn.commit()
        conn.close()


def test_acknowledge_unknown_action_returns_error():
    init_db()
    queue_for_review("SYN_Q3", reason="test")
    out = acknowledge("SYN_Q3", action="bogus_action")
    assert out["ok"] is False
    assert "unknown action" in out["error"]
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_Q3'")
        conn.commit()
    finally:
        conn.close()


def test_run_layer_2_flags_changed_summaries():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol IN ('SYN_L2A', 'SYN_L2B')")
        conn.commit()
    finally:
        conn.close()

    # First call: establish baseline (no flags)
    fetch_v1 = lambda s: f"version 1 of {s}"
    run_layer_2_hash_diff(["SYN_L2A", "SYN_L2B"], fetch_fn=fetch_v1, log=False)

    # Second call with new content: flag both
    fetch_v2 = lambda s: f"VERSION 2 of {s}"
    out = run_layer_2_hash_diff(["SYN_L2A", "SYN_L2B"], fetch_fn=fetch_v2, log=False)
    assert out["flagged"] == 2

    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol IN ('SYN_L2A', 'SYN_L2B')")
        conn.commit()
    finally:
        conn.close()


def test_flag_stale_via_decay_flags_old_extractions():
    """Insert a row with last_extracted_at far in the past; decay sweep flags it."""
    init_db()
    long_ago = (datetime.now(timezone.utc) - timedelta(days=1000)).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_OLD'")
        conn.execute(
            "INSERT INTO edge_freshness (symbol, last_extracted_at, status) "
            "VALUES ('SYN_OLD', ?, 'fresh')",
            (long_ago,),
        )
        conn.commit()
    finally:
        conn.close()

    out = flag_stale_via_decay(log=False)
    assert out["flagged"] >= 1

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, trigger_reason FROM edge_freshness WHERE symbol='SYN_OLD'"
        ).fetchone()
        assert row["status"] == "needs_review"
        assert row["trigger_reason"] == "decay"
    finally:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_OLD'")
        conn.commit()
        conn.close()


# ── /freshness API endpoints ─────────────────────────────────────


@pytest.fixture
def client():
    return TestClient(app)


def test_freshness_queue_endpoint_returns_flagged_only(client):
    init_db()
    queue_for_review("SYN_API_FLAG", reason="api_test")
    r = client.get("/freshness/queue")
    assert r.status_code == 200
    payload = r.json()
    syms = {row["symbol"] for row in payload["queue"]}
    assert "SYN_API_FLAG" in syms

    # Cleanup
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_API_FLAG'")
        conn.commit()
    finally:
        conn.close()


def test_freshness_acknowledge_endpoint(client):
    init_db()
    queue_for_review("SYN_API_ACK", reason="api_test")
    r = client.post(
        "/freshness/acknowledge",
        json={"symbol": "SYN_API_ACK", "action": "re_extract"},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True

    # Verify the queue row is now 'fresh', not 'needs_review'
    queue_resp = client.get("/freshness/queue").json()
    syms = {row["symbol"] for row in queue_resp["queue"]}
    assert "SYN_API_ACK" not in syms

    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_API_ACK'")
        conn.commit()
    finally:
        conn.close()
