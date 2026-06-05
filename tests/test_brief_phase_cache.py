"""Tests for the brief pipeline phase-level checkpoint cache.

The cache lets a brief restart skip phases that already completed and only
re-run the one that failed. These tests confirm round-trip, TTL expiry,
symbol-scoped invalidation, and key stability across re-serialization.

All operations target the temp DB via the session-scoped `_isolated_test_db`
fixture in conftest.py — the production trading.db is untouched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.services import _phase_cache
from src.utils.db import get_connection, init_db


# Synthetic-only symbols per CLAUDE.md
_TEST_SYM = "TEST_FOO"
_OTHER_SYM = "SYN_BAR"


def _clean_test_rows() -> None:
    init_db()
    conn = get_connection()
    conn.execute(
        "DELETE FROM brief_phase_cache WHERE cache_key LIKE ?",
        (f"{_TEST_SYM}::%",),
    )
    conn.execute(
        "DELETE FROM brief_phase_cache WHERE cache_key LIKE ?",
        (f"{_OTHER_SYM}::%",),
    )
    conn.commit()
    conn.close()


def test_get_returns_none_on_miss():
    _clean_test_rows()
    assert _phase_cache.get(_TEST_SYM, "lens", {"v": 1, "x": 1}) is None


def test_put_then_get_round_trip():
    _clean_test_rows()
    payload = {"query": "AI infra capex", "convergence": [{"sector": "Tech"}]}
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1, "x": 1}, payload)

    got = _phase_cache.get(_TEST_SYM, "lens", {"v": 1, "x": 1})
    assert got == payload


def test_get_different_input_misses():
    """Cache key is content-addressed — changing input invalidates."""
    _clean_test_rows()
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1, "x": 1}, {"ok": True})

    assert _phase_cache.get(_TEST_SYM, "lens", {"v": 1, "x": 2}) is None
    # Different phase name with same input also misses
    assert _phase_cache.get(_TEST_SYM, "narrate", {"v": 1, "x": 1}) is None


def test_key_stable_across_dict_key_order():
    """sort_keys=True in the hasher means dict ordering doesn't affect the key."""
    _clean_test_rows()
    _phase_cache.put(_TEST_SYM, "lens", {"a": 1, "b": 2}, {"v": "alpha"})

    # Same content, different insert order — should still hit.
    got = _phase_cache.get(_TEST_SYM, "lens", {"b": 2, "a": 1})
    assert got == {"v": "alpha"}


def test_put_overwrites_existing_entry():
    _clean_test_rows()
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1}, {"version": "old"})
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1}, {"version": "new"})

    assert _phase_cache.get(_TEST_SYM, "lens", {"v": 1}) == {"version": "new"}


def test_ttl_expiry_filters_old_entries():
    """An entry with created_at older than ttl_hours should be treated as missing."""
    _clean_test_rows()
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1}, {"ok": True})

    # Manually backdate the row to simulate an old entry.
    init_db()
    conn = get_connection()
    old_iso = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).isoformat()
    conn.execute(
        "UPDATE brief_phase_cache SET created_at = ? WHERE cache_key LIKE ?",
        (old_iso, f"{_TEST_SYM}::lens::%"),
    )
    conn.commit()
    conn.close()

    # Default TTL is 6h — should miss.
    assert _phase_cache.get(_TEST_SYM, "lens", {"v": 1}) is None

    # With a 72h TTL the same row should hit.
    assert _phase_cache.get(_TEST_SYM, "lens", {"v": 1}, ttl_hours=72) == {"ok": True}


def test_invalidate_only_clears_named_symbol():
    """invalidate(symbol) must scope strictly to that symbol's prefix."""
    _clean_test_rows()
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1}, {"sym": "test"})
    _phase_cache.put(_TEST_SYM, "narrate", {"v": 1}, {"sym": "test"})
    _phase_cache.put(_OTHER_SYM, "lens", {"v": 1}, {"sym": "other"})

    n = _phase_cache.invalidate(_TEST_SYM)
    assert n == 2

    # TEST_SYM rows gone, OTHER_SYM row untouched
    assert _phase_cache.get(_TEST_SYM, "lens", {"v": 1}) is None
    assert _phase_cache.get(_TEST_SYM, "narrate", {"v": 1}) is None
    assert _phase_cache.get(_OTHER_SYM, "lens", {"v": 1}) == {"sym": "other"}


def test_invalidate_no_match_returns_zero():
    _clean_test_rows()
    assert _phase_cache.invalidate("SYN_NEVER_INSERTED") == 0


def test_symbol_namespace_is_case_insensitive():
    """Keys are uppercased so 'test_foo' and 'TEST_FOO' collide (by design)."""
    _clean_test_rows()
    _phase_cache.put(_TEST_SYM.lower(), "lens", {"v": 1}, {"ok": True})
    assert _phase_cache.get(_TEST_SYM.upper(), "lens", {"v": 1}) == {"ok": True}


def test_make_key_format():
    """Defensive: format change would silently invalidate every prior entry."""
    key = _phase_cache.make_key(_TEST_SYM, "lens", {"v": 1})
    assert key.startswith(f"{_TEST_SYM.upper()}::lens::")
    # Hash component is the last segment and is 16 hex chars
    suffix = key.rsplit("::", 1)[-1]
    assert len(suffix) == 16
    assert all(c in "0123456789abcdef" for c in suffix)


def test_non_serializable_payload_does_not_raise():
    """put() must swallow serialization failures (datetime / Decimal etc.).

    The lens/narrate payloads contain JSON-safe dicts but the safety net
    matters in case a future phase passes something exotic.
    """
    _clean_test_rows()

    class _NotSerializable:
        pass

    # Should not raise. Cache becomes a no-op for this entry.
    _phase_cache.put(_TEST_SYM, "weird", {"v": 1}, {"obj": _NotSerializable()})
    # And the next get is a miss (because the put was skipped or the row is
    # decodable-as-string but unequal). Either is acceptable; we just want no
    # exception to propagate.
    _phase_cache.get(_TEST_SYM, "weird", {"v": 1})  # no raise


def test_datetime_payload_round_trip():
    """default=str on serialization means datetime payloads round-trip as
    strings — that's fine because phases only persist JSON-shaped output."""
    _clean_test_rows()
    payload = {"as_of": datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)}
    _phase_cache.put(_TEST_SYM, "lens", {"v": 1}, payload)
    got = _phase_cache.get(_TEST_SYM, "lens", {"v": 1})
    assert isinstance(got, dict)
    assert "as_of" in got
    assert "2026-06-05" in got["as_of"]
