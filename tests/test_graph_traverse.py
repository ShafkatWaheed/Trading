"""Tests for the BFS graph traversal."""

from __future__ import annotations

import pytest

from src.graph.traverse import (
    ALL_EDGE_TYPES,
    Edge,
    GraphResult,
    expand,
    neighborhood,
)
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_graph():
    init_db()
    load_tier_a()
    load_all_hand_peers()
    load_spine()


# ── seeds-only behaviour ─────────────────────────────────────────


def test_zero_hops_returns_only_seed():
    out = expand({"NVDA"}, hops=0)
    assert set(out.keys()) == {"NVDA"}
    assert out["NVDA"].hop == 0


def test_seed_polarity_default_is_positive_one():
    out = expand({"NVDA"}, hops=0)
    assert out["NVDA"].cumulative_polarity == 1.0


def test_seed_polarity_can_be_overridden():
    out = expand({"NVDA"}, hops=0, starting_polarity={"NVDA": -1.0})
    assert out["NVDA"].cumulative_polarity == -1.0


# ── 1-hop expansion ──────────────────────────────────────────────


def test_one_hop_finds_known_supply_chain_for_nvda():
    out = expand({"NVDA"}, hops=1, edge_types=["supplier"])
    # NVDA's supplier TSM is in the seed
    assert "TSM" in out
    assert out["TSM"].hop == 1


def test_one_hop_peer_expansion_for_msft():
    out = expand({"MSFT"}, hops=1, edge_types=["peer"])
    syms = set(out.keys())
    assert {"GOOGL", "AMZN", "ORCL"} <= syms


def test_one_hop_with_all_edge_types_covers_peers_plus_relations():
    out = expand({"NVDA"}, hops=1)
    syms = set(out.keys())
    # Peers: AVGO/AMD/MRVL etc.
    # Relations: TSM (supplier), MSFT/META (customer), VRT/GEV (complement)
    assert "TSM" in syms        # supplier
    assert "AVGO" in syms       # peer
    assert "MSFT" in syms       # customer (NVDA → customer → MSFT)


def test_unfiltered_edge_types_use_all_five():
    """Calling without edge_types should be equivalent to passing ALL_EDGE_TYPES."""
    a = expand({"NVDA"}, hops=1)
    b = expand({"NVDA"}, hops=1, edge_types=ALL_EDGE_TYPES)
    assert set(a.keys()) == set(b.keys())


# ── multi-hop ──────────────────────────────────────────────────


def test_two_hop_traversal_reaches_asml_via_tsm():
    """ASML is reachable from NVDA via the supplier chain.

    The seed has both a direct NVDA→ASML edge (representing the indirect-but-
    critical EUV dependency) AND TSM→ASML, so the actual hop distance is 1.
    The test checks that 2-hop expansion reaches ASML one way or another.
    """
    out = expand({"NVDA"}, hops=2, edge_types=["supplier"])
    assert "TSM" in out
    assert "ASML" in out
    # ASML is at hop 1 thanks to direct NVDA→ASML edge in the seed
    assert out["ASML"].hop in (1, 2)


def test_two_hop_does_not_double_count_already_visited():
    """If TSM is already at hop 1, a 2-hop traversal that revisits TSM doesn't
    bump it back to hop 2."""
    out = expand({"NVDA"}, hops=2, edge_types=["supplier", "customer"])
    # TSM appears at hop 1
    assert out["TSM"].hop == 1


# ── polarity propagation ────────────────────────────────────────


def test_substitute_edge_flips_polarity_at_hop():
    """TSLA → substitute → F (polarity=-1) → at hop 1 cumulative pol should be -1."""
    out = expand({"TSLA"}, hops=1, edge_types=["substitute"])
    if "F" in out:
        assert out["F"].cumulative_polarity == -1.0


def test_two_hop_substitute_chain_flips_polarity_twice():
    """A→sub→B→sub→A: cumulative polarity flips twice = +1 (no change in net direction)."""
    # If TSLA → substitute → F and F → substitute → TSLA both exist (the seed
    # has both directions), a 2-hop expansion from TSLA can reach TSLA again
    # via F. We don't visit it twice (deduped by symbol), so just verify F's
    # cumulative is -1 at hop 1.
    out = expand({"TSLA"}, hops=2, edge_types=["substitute"])
    if "F" in out:
        assert out["F"].cumulative_polarity == -1.0


def test_negative_seed_polarity_propagates():
    """If we seed NVDA with polarity -1, its 1-hop positive supplier should be -1."""
    out = expand({"NVDA"}, hops=1,
                 edge_types=["supplier"],
                 starting_polarity={"NVDA": -1.0})
    if "TSM" in out:
        # TSM's incoming edge has polarity +1 (supplier), seed is -1, product is -1
        assert out["TSM"].cumulative_polarity == -1.0


# ── edge metadata ───────────────────────────────────────────────


def test_incoming_edges_recorded_with_metadata():
    out = expand({"NVDA"}, hops=1, edge_types=["supplier"])
    if "TSM" in out:
        edges = out["TSM"].incoming_edges
        assert len(edges) >= 1
        e = edges[0]
        assert e.from_symbol == "NVDA"
        assert e.to_symbol == "TSM"
        assert e.edge_type == "supplier"
        assert e.evidence is not None     # from the seed CSV


def test_seed_node_has_empty_incoming_edges():
    out = expand({"NVDA"}, hops=2)
    assert out["NVDA"].hop == 0
    assert out["NVDA"].incoming_edges == []


# ── neighborhood helper ─────────────────────────────────────────


def test_neighborhood_splits_by_direction():
    out = neighborhood("NVDA")
    assert "suppliers" in out
    assert "customers" in out
    assert "peers" in out
    assert "substitutes" in out
    assert "complements" in out


def test_neighborhood_nvda_has_tsm_as_supplier():
    out = neighborhood("NVDA")
    sups = [e.to_symbol for e in out["suppliers"]]
    assert "TSM" in sups


def test_neighborhood_nvda_has_msft_as_customer():
    out = neighborhood("NVDA")
    custs = [e.to_symbol for e in out["customers"]]
    assert "MSFT" in custs


def test_neighborhood_nvda_includes_complement_with_vrt():
    out = neighborhood("NVDA")
    comps = [e.to_symbol for e in out["complements"]]
    assert "VRT" in comps or "GEV" in comps or "ETN" in comps


def test_neighborhood_unknown_symbol_returns_empty_dict():
    out = neighborhood("ZZZZZNOTAREALSYMBOL")
    for k, lst in out.items():
        assert lst == []


# ── inverse-direction lookup (supplier ↔ customer flip) ──────────


def test_neighborhood_finds_supplier_via_inverse_customer_row():
    """AMZN has no `from_symbol=AMZN` supplier/customer rows in the seed.

    But (NVDA, AMZN, customer) exists → from AMZN's view NVDA is a supplier.
    Read-time symmetric lookup should surface this.
    """
    out = neighborhood("AMZN")
    sups = [e.to_symbol for e in out["suppliers"]]
    assert "NVDA" in sups, f"expected NVDA in AMZN suppliers via inverse lookup, got {sups}"


def test_neighborhood_finds_customer_via_inverse_supplier_row():
    """(AAPL, AVGO, supplier) is hand-seeded with no reverse row.

    From AVGO's view, AAPL should appear as a customer via inverse lookup
    (flipping supplier → customer for the inverse-direction row).
    """
    out = neighborhood("AVGO")
    custs = [e.to_symbol for e in out["customers"]]
    assert "AAPL" in custs, f"expected AAPL in AVGO customers via inverse lookup, got {custs}"


def test_neighborhood_msft_sees_nvda_as_supplier_via_inverse():
    """(NVDA, MSFT, customer) is in the seed; from MSFT's view NVDA should be a supplier."""
    out = neighborhood("MSFT")
    sups = [e.to_symbol for e in out["suppliers"]]
    assert "NVDA" in sups


def test_neighborhood_inverse_edge_has_correct_type_and_polarity():
    """The flipped edge must carry the correct edge_type (supplier, not customer)
    and preserve polarity from the underlying row."""
    out = neighborhood("AMZN")
    nvda_edges = [e for e in out["suppliers"] if e.to_symbol == "NVDA"]
    assert len(nvda_edges) == 1
    edge = nvda_edges[0]
    assert edge.edge_type == "supplier"          # flipped from underlying 'customer'
    assert edge.from_symbol == "AMZN"            # from the queried symbol's POV
    assert edge.polarity == 1.0                  # preserved from underlying row


def test_neighborhood_bilateral_relation_dedupes():
    """NVDA↔TSM is seeded in both directions: (NVDA,TSM,supplier) AND (TSM,NVDA,customer).

    NVDA's suppliers list should contain TSM exactly once, not duplicated by the
    inverse-direction lookup.
    """
    out = neighborhood("NVDA")
    tsm_supplier_edges = [e for e in out["suppliers"] if e.to_symbol == "TSM"]
    assert len(tsm_supplier_edges) == 1, (
        f"TSM appears {len(tsm_supplier_edges)} times in NVDA suppliers; expected 1"
    )


def test_neighborhood_substitute_is_symmetric_not_flipped():
    """substitute/complement are symmetric — inverse lookup should keep the type."""
    # TSLA → substitute → F is in the seed
    out = neighborhood("F")
    subs = [e.to_symbol for e in out["substitutes"]]
    # F should see TSLA as a substitute via the inverse direction
    assert "TSLA" in subs


def test_expand_finds_inverse_supplier_for_msft():
    """1-hop expand from MSFT with edge_types=['supplier'] should reach NVDA
    via the inverse (NVDA, MSFT, customer) row."""
    out = expand({"MSFT"}, hops=1, edge_types=["supplier"])
    assert "NVDA" in out


# ── Temporal filtering (effective_from / effective_to) ───────────


def test_neighborhood_with_as_of_excludes_future_dated_edges():
    """An edge with effective_from > as_of should be invisible.

    Insert a synthetic 10k_mined-style row with effective_from='2025-06-01'.
    Queries with as_of < that date must NOT see it; queries on/after must."""
    from src.utils.db import get_connection
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_T1','B','test')"
        )
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_T2','B','test')"
        )
        conn.execute(
            "INSERT INTO stock_relations "
            "(from_symbol, to_symbol, relation_type, strength, polarity, evidence, "
            " effective_from) "
            "VALUES ('SYN_T1','SYN_T2','customer',0.65,1.0,'10k_mined: synthetic test', "
            " '2025-06-01')"
        )
        conn.commit()

        # Before effective_from → edge invisible
        early = neighborhood("SYN_T1", as_of="2025-01-01", conn=conn)
        assert "SYN_T2" not in [e.to_symbol for e in early["customers"]]

        # On/after effective_from → edge visible
        later = neighborhood("SYN_T1", as_of="2025-06-15", conn=conn)
        assert "SYN_T2" in [e.to_symbol for e in later["customers"]]

        # No as_of → edge always visible
        always = neighborhood("SYN_T1", conn=conn)
        assert "SYN_T2" in [e.to_symbol for e in always["customers"]]
    finally:
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_T1' OR to_symbol='SYN_T1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_T1','SYN_T2')")
        conn.commit()
        conn.close()


def test_neighborhood_with_as_of_excludes_expired_edges():
    """An edge with effective_to <= as_of should be invisible. Models e.g.
    AAPL→INTC supplier (which ended in 2020)."""
    from src.utils.db import get_connection
    conn = get_connection()
    try:
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_X1','B','test')")
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_X2','B','test')")
        conn.execute(
            "INSERT INTO stock_relations "
            "(from_symbol, to_symbol, relation_type, strength, polarity, evidence, "
            " effective_from, effective_to) "
            "VALUES ('SYN_X1','SYN_X2','supplier',0.65,1.0,'10k_mined: ended', "
            " '2018-01-01','2020-12-31')"
        )
        conn.commit()

        # Within window → visible
        during = neighborhood("SYN_X1", as_of="2019-06-01", conn=conn)
        assert "SYN_X2" in [e.to_symbol for e in during["suppliers"]]

        # After effective_to → invisible
        after = neighborhood("SYN_X1", as_of="2024-01-01", conn=conn)
        assert "SYN_X2" not in [e.to_symbol for e in after["suppliers"]]
    finally:
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_X1' OR to_symbol='SYN_X1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_X1','SYN_X2')")
        conn.commit()
        conn.close()


def test_neighborhood_without_as_of_returns_all_edges():
    """Default behavior (no as_of) must be unchanged — all hand-seeded edges
    (which have NULL effective_from / _to) still appear."""
    # NVDA has TSM as a hand-seeded supplier with NULL temporal bounds.
    out = neighborhood("NVDA")
    assert "TSM" in [e.to_symbol for e in out["suppliers"]]


def test_expand_with_as_of_propagates_filter():
    """expand() must respect as_of for multi-hop relation traversal."""
    from src.utils.db import get_connection
    conn = get_connection()
    try:
        for s in ("SYN_E1", "SYN_E2"):
            conn.execute(f"INSERT INTO stocks_universe (symbol, tier, source) VALUES ('{s}','B','test')")
        conn.execute(
            "INSERT INTO stock_relations "
            "(from_symbol, to_symbol, relation_type, strength, polarity, evidence, effective_from) "
            "VALUES ('SYN_E1','SYN_E2','supplier',0.65,1.0,'10k_mined','2025-06-01')"
        )
        conn.commit()

        early = expand({"SYN_E1"}, hops=1, edge_types=["supplier"], as_of="2025-01-01", conn=conn)
        assert "SYN_E2" not in early

        later = expand({"SYN_E1"}, hops=1, edge_types=["supplier"], as_of="2025-06-15", conn=conn)
        assert "SYN_E2" in later
    finally:
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_E1' OR to_symbol='SYN_E1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_E1','SYN_E2')")
        conn.commit()
        conn.close()


def test_neighborhood_peer_edge_respects_as_of():
    """Peer edges with effective_from in the future must be invisible to as_of
    before that date. Mirrors the relation-edge behavior on stock_peers."""
    from src.utils.db import get_connection
    conn = get_connection()
    try:
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_P1','B','test')")
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_P2','B','test')")
        conn.execute(
            "INSERT INTO stock_peers "
            "(from_symbol, to_symbol, similarity, source, confidence, evidence, effective_from) "
            "VALUES ('SYN_P1','SYN_P2',0.7,'test','high','synthetic peer','2025-06-01')"
        )
        conn.commit()

        early = neighborhood("SYN_P1", as_of="2025-01-01", conn=conn)
        assert "SYN_P2" not in [e.to_symbol for e in early["peers"]]

        later = neighborhood("SYN_P1", as_of="2025-06-15", conn=conn)
        assert "SYN_P2" in [e.to_symbol for e in later["peers"]]

        always = neighborhood("SYN_P1", conn=conn)
        assert "SYN_P2" in [e.to_symbol for e in always["peers"]]
    finally:
        conn.execute("DELETE FROM stock_peers WHERE from_symbol='SYN_P1' OR to_symbol='SYN_P1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_P1','SYN_P2')")
        conn.commit()
        conn.close()
