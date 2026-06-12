from api.services import analyst_pit_service as pit


def test_full_packet_omits_live_only_signals_in_bootstrap():
    # allow_live_search=False (bootstrap) => packet must NOT contain options/premarket/reddit
    pkt = pit.assemble_full(["SYN_PIT"], "2026-02-01", allow_live_search=False)
    one = pkt.get("SYN_PIT", {})
    assert "options_flow" not in one
    assert "premarket" not in one
    assert "reddit" not in one
    # but it DOES carry the reconstructable block keys
    assert set(one.keys()) <= {
        "momentum", "sector_flow", "macro", "congress", "insider",
        "institutions", "news", "earnings", "fundamentals", "short_interest",
    }


def test_full_packet_includes_live_only_when_allowed():
    pkt = pit.assemble_full(["SYN_PIT"], "2026-02-01", allow_live_search=True)
    one = pkt.get("SYN_PIT", {})
    # live mode MAY include options/premarket/reddit keys (values can be None)
    assert "options_flow" in one


def test_assemble_full_parallel_builds_all_and_computes_macro_once(monkeypatch):
    """The shortlist packets are built concurrently and macro (universe-wide) is
    computed ONCE, not per symbol. Stubs avoid network so it's fast + deterministic."""
    import api.services.analyst_pit_service as pit
    macro_calls = []
    monkeypatch.setattr(pit, "_macro_block", lambda d: (macro_calls.append(d) or {"vix": 20}))
    for fn in ("_momentum_block", "_sector_block", "_insider_block", "_news_block",
               "_earnings_block", "_fundamentals_block", "_short_interest_block"):
        monkeypatch.setattr(pit, fn, lambda *a, **k: {"ok": 1})
    monkeypatch.setattr(pit, "congress_flags_as_of", lambda syms, d: {})
    monkeypatch.setattr(pit, "institution_breadth_as_of", lambda syms, d: {})
    syms = [f"SYN_{i:02d}" for i in range(20)]
    out = pit.assemble_full(syms, "2026-02-01", allow_live_search=False)
    assert set(out) == set(syms)                       # every symbol built
    assert len(macro_calls) == 1                        # macro hoisted (once, not 20x)
    assert all(out[s]["macro"] == {"vix": 20} for s in syms)
    assert "options_flow" not in out["SYN_00"]          # live-only still gated off
