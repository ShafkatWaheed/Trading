"""Two-stage predictor with an injected fake Claude (no network)."""
from api.services import analyst_predictor as ap


def _compact(n):
    return [{"symbol": f"SYN_{i:03d}", "name": f"Co {i}", "sector": "Tech",
             "momentum_pct": float(n - i)} for i in range(n)]


class _FakeClaude:
    def __init__(self, triage, picks):
        self._triage, self._picks = triage, picks
        self.calls = []

    def __call__(self, prompt, *, model, timeout, retries=0, allowed_tools=""):
        self.calls.append(("triage" if "shortlist" in prompt else "pick", allowed_tools))
        return self._triage if "shortlist" in prompt else self._picks


def test_triage_returns_shortlist_symbols():
    fake = _FakeClaude({"shortlist": ["SYN_000", "SYN_001"]}, None)
    out = ap.triage(_compact(40), playbook="PB", claude=fake)
    assert out == ["SYN_000", "SYN_001"]


def test_deep_pick_returns_ten_with_reasoning():
    picks = {"picks": [{"symbol": f"SYN_{i:03d}", "reasoning": "r", "confidence": 0.6}
                       for i in range(10)]}
    fake = _FakeClaude(None, picks)
    out = ap.deep_pick({f"SYN_{i:03d}": {"momentum": 1} for i in range(10)},
                       playbook="PB", allow_live_search=False, claude=fake)
    assert len(out) == 10
    assert all("reasoning" in p and "confidence" in p for p in out)
    # bootstrap => no web tools requested
    assert fake.calls[-1][1] == ""


def test_deep_pick_falls_back_to_momentum_on_claude_failure():
    fake = _FakeClaude(None, None)   # returns None => failure
    packets = {f"SYN_{i:03d}": {"momentum": {"trailing_return": float(10 - i)}}
               for i in range(12)}
    out = ap.deep_pick(packets, playbook="PB", allow_live_search=False, claude=fake)
    assert len(out) == 10
    assert out[0]["symbol"] == "SYN_000"   # highest momentum first
    assert out[0]["reasoning"].startswith("fallback")
