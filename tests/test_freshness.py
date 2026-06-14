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


def test_detect_new_filings_first_run_returns_only_default_watched():
    """Default watched set is narrow: 10-K + material 8-K. Routine quarterly
    filings (10-Q, DEF 14A) and noisy 8-K items (7.01 Reg FD, 8.01 Other) are
    intentionally ignored — they flood the queue without changing the graph."""
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
            {"form": "DEF 14A", "filed_at": "2026-03-20"},
            {"form": "S-1", "filed_at": "2026-03-01"},
            {"form": "8-K", "filed_at": "2026-03-10", "items": "1.01,2.03"},  # material
            {"form": "8-K", "filed_at": "2026-03-12", "items": "7.01"},        # Reg FD — noise
        ]

    out = detect_new_filings("SYN_FILING", fetch_fn=fake_filings)
    forms = {f["form"] for f in out["new_filings"]}
    # Only 10-K + the material 8-K survive
    assert forms == {"10-K", "8-K"}
    assert len(out["new_filings"]) == 2

    # The material 8-K kept its items
    material_8k = next(f for f in out["new_filings"] if f["form"] == "8-K")
    assert "1.01" in (material_8k.get("items") or "")


def test_detect_new_filings_can_be_widened_via_watched_param():
    """Callers can opt back into noisy forms by passing an explicit `watched` set."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_FILING_WIDE'")
        conn.commit()
    finally:
        conn.close()

    def fake_filings(sym):
        return [
            {"form": "10-K", "filed_at": "2026-04-01"},
            {"form": "10-Q", "filed_at": "2026-02-15"},
        ]

    out = detect_new_filings(
        "SYN_FILING_WIDE",
        fetch_fn=fake_filings,
        watched=frozenset({"10-K", "10-Q"}),
    )
    forms = {f["form"] for f in out["new_filings"]}
    assert forms == {"10-K", "10-Q"}


def test_detect_new_filings_skips_8k_without_material_items():
    """8-K filings with only noisy items (7.01 Reg FD, 8.01 Other) are skipped."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_8K_NOISE'")
        conn.commit()
    finally:
        conn.close()

    def fake_filings(sym):
        return [
            {"form": "8-K", "filed_at": "2026-03-10", "items": "7.01"},
            {"form": "8-K", "filed_at": "2026-03-11", "items": "8.01"},
            {"form": "8-K", "filed_at": "2026-03-12", "items": ""},
            {"form": "8-K", "filed_at": "2026-03-13"},   # no items at all
        ]

    out = detect_new_filings("SYN_8K_NOISE", fetch_fn=fake_filings)
    assert out["new_filings"] == []


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
    """With a successful extractor, queue entry clears and state goes 'fresh'."""
    init_db()
    queue_for_review("SYN_Q2", reason="test")

    def stub_extractor(symbol):
        return {"symbol": symbol, "edges_written": 1}

    out = acknowledge("SYN_Q2", action="re_extract", extractor_fn=stub_extractor)
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


def test_acknowledge_re_extract_invokes_extractor():
    """re_extract must call the 10-K extractor, not just bump state."""
    init_db()
    queue_for_review("SYN_RE_INVOKE", reason="test")

    calls: list[str] = []
    def fake_extractor(symbol):
        calls.append(symbol)
        return {"symbol": symbol, "edges_written": 3}

    out = acknowledge("SYN_RE_INVOKE", action="re_extract", extractor_fn=fake_extractor)
    assert out["ok"] is True
    assert calls == ["SYN_RE_INVOKE"]
    assert out.get("edges_written") == 3

    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_RE_INVOKE'")
        conn.commit()
    finally:
        conn.close()


def test_acknowledge_re_extract_keeps_queue_entry_on_extractor_error():
    """If the extractor fails, the symbol must REMAIN in needs_review for retry."""
    init_db()
    queue_for_review("SYN_RE_FAIL", reason="test")

    def failing_extractor(symbol):
        return {"symbol": symbol, "edges_written": 0, "error": "no_item_1a"}

    out = acknowledge("SYN_RE_FAIL", action="re_extract", extractor_fn=failing_extractor)
    assert out["ok"] is False
    assert "no_item_1a" in (out.get("error") or "")

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, trigger_reason FROM edge_freshness WHERE symbol='SYN_RE_FAIL'"
        ).fetchone()
        # Still flagged for review so the user can retry
        assert row["status"] == "needs_review"
        assert row["trigger_reason"] == "test"
    finally:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_RE_FAIL'")
        conn.commit()
        conn.close()


def test_acknowledge_skip_30d_does_not_invoke_extractor():
    """skip_30d and pin_current must NOT call the extractor — only re_extract does."""
    init_db()
    queue_for_review("SYN_SKIP", reason="test")

    calls: list[str] = []
    def fake_extractor(symbol):
        calls.append(symbol)
        return {"edges_written": 0}

    acknowledge("SYN_SKIP", action="skip_30d", extractor_fn=fake_extractor)
    acknowledge("SYN_SKIP", action="pin_current", extractor_fn=fake_extractor)
    assert calls == []

    conn = get_connection()
    try:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_SKIP'")
        conn.commit()
    finally:
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


def test_freshness_acknowledge_endpoint(client, monkeypatch):
    """End-to-end: HTTP POST → service → orchestrator → (mocked) extractor.

    The real 10-K extractor would hit SEC EDGAR + Claude for SYN_API_ACK, which
    has no filing. Stub it here so the test isolates the request → state path.
    """
    init_db()
    queue_for_review("SYN_API_ACK", reason="api_test")

    def stub_process(symbol, **kwargs):
        return {"symbol": symbol, "edges_written": 0}

    monkeypatch.setattr("src.data.sec_10k_extractor.process_symbol", stub_process)

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


# ── Layer 4 wiring (correlation drift → orchestrator) ────────────


def test_run_layer_4_flags_drifted_symbol():
    """Inject a returns fetcher where target's correlation with its peers has
    collapsed. Layer 4 should queue the symbol with reason='peer_decoupling'."""
    from src.freshness.orchestrator import run_layer_4_correlation_drift

    init_db()
    conn = get_connection()
    try:
        # Synthetic universe + a peer relationship: TARGET ↔ PEER1, PEER2
        for s in ("SYN_L4T", "SYN_L4P1", "SYN_L4P2"):
            conn.execute(f"INSERT INTO stocks_universe (symbol, tier, source) VALUES ('{s}','B','test')")
        for p in ("SYN_L4P1", "SYN_L4P2"):
            conn.execute(
                "INSERT INTO stock_peers (from_symbol, to_symbol, similarity, source, confidence) "
                "VALUES (?, ?, 0.8, 'test', 'high')",
                ("SYN_L4T", p),
            )
        conn.commit()

        # Baseline window (252+90=342 days): all 3 stocks move together (corr ~1.0).
        # Recent window (90 days): target decouples (random noise vs steady peers).
        def fake_fetch(sym, days):
            if days >= 300:
                # Long baseline: smooth uptrend for everyone
                return [0.01 * (i % 5 - 2) for i in range(days)]
            # Recent: target is noise, peers are the same smooth pattern
            base = [0.01 * (i % 5 - 2) for i in range(days)]
            if sym == "SYN_L4T":
                # Phase-shifted to break correlation
                return [-x for x in base]
            return base

        out = run_layer_4_correlation_drift(
            ["SYN_L4T"], returns_fetch_fn=fake_fetch, log=False,
        )
        # Drifted: 1 flagged
        assert out["flagged"] >= 1

        # edge_freshness should now have the symbol flagged with peer_decoupling
        row = conn.execute(
            "SELECT status, trigger_reason FROM edge_freshness WHERE symbol='SYN_L4T'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "needs_review"
        assert row["trigger_reason"] == "peer_decoupling"
    finally:
        conn.execute("DELETE FROM edge_freshness WHERE symbol='SYN_L4T'")
        conn.execute("DELETE FROM stock_peers WHERE from_symbol='SYN_L4T'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_L4T','SYN_L4P1','SYN_L4P2')")
        conn.commit()
        conn.close()


def test_run_layer_4_skips_symbol_without_peers():
    """Layer 4 has no signal for stocks with no tagged peers — should skip cleanly."""
    from src.freshness.orchestrator import run_layer_4_correlation_drift

    init_db()
    conn = get_connection()
    try:
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_L4ORPHAN','B','test')")
        conn.commit()

        out = run_layer_4_correlation_drift(
            ["SYN_L4ORPHAN"], returns_fetch_fn=lambda s, d: [], log=False,
        )
        assert out["flagged"] == 0
        assert out["skipped"] >= 1
    finally:
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_L4ORPHAN'")
        conn.commit()
        conn.close()


def test_run_orchestrator_with_layer_4_opt_in():
    """layer4 not in default layers; explicit opt-in invokes the wrapper."""
    from src.freshness.orchestrator import run_orchestrator

    init_db()
    # No symbols → all layers report 0/0; layer4 just needs to appear in output.
    out = run_orchestrator(
        [], layers=("layer4",),
        returns_fetch_fn=lambda s, d: [],
        log=False,
    )
    assert "layer4" in out
    assert out["layer4"]["flagged"] == 0


# ── Layer 5 wiring (news drift → orchestrator) ───────────────────


def test_run_layer_5_skips_when_no_news():
    """No headlines for a symbol → skipped, not flagged."""
    from src.freshness.orchestrator import run_layer_5_news_drift

    init_db()
    out = run_layer_5_news_drift(
        ["SYN_L5A"],
        headlines_fetch_fn=lambda s: [],
        industry_domains_fn=lambda s: {"ai"},
        log=False,
    )
    assert out["flagged"] == 0
    assert out["skipped"] >= 1


def test_run_orchestrator_with_layer_5_opt_in_is_noop_without_news():
    """layer5 should be safe to enable even without news data — it skips
    every symbol rather than crashing."""
    from src.freshness.orchestrator import run_orchestrator

    init_db()
    out = run_orchestrator(
        ["SYN_L5B"], layers=("layer5",),
        headlines_fetch_fn=None,            # default no-op
        industry_domains_fn=None,           # default no-op
        log=False,
    )
    assert "layer5" in out
    assert out["layer5"]["flagged"] == 0


def test_market_pulse_freshness_uses_recorded_marker():
    """check_market_pulse() reports 'never recorded' with no marker, and fresh
    once get_pulse() has written a market:pulse:* marker."""
    from api.services import feature_freshness as ff
    from src.utils.db import cache_set, get_connection, init_db
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'market:pulse:%'")
        conn.commit()
    finally:
        conn.close()

    r = ff.check_market_pulse()
    assert r["stale"] is True and "never recorded" in (r["reason"] or "")

    cache_set("market:pulse:freshness", {"recorded_at": "now"}, ttl_minutes=24 * 60)
    r2 = ff.check_market_pulse()
    assert r2["stale"] is False
    assert r2["last_updated"] is not None and r2["reason"] is None

    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'market:pulse:%'")
        conn.commit()
    finally:
        conn.close()
