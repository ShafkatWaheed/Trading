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
