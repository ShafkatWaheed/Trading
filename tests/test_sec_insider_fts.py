"""SEC EDGAR insider full-text search must send enddt (custom range needs both
dates, else SEC returns HTTP 500). No network — _sec_get is monkeypatched."""
from __future__ import annotations

import datetime

from src.data.sec_edgar import SECEdgarProvider


class _Resp:
    def json(self):
        return {"hits": {"hits": []}}


def test_insider_fts_sends_both_startdt_and_enddt(monkeypatch):
    p = SECEdgarProvider()
    captured = {}

    def fake_get(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _Resp()

    monkeypatch.setattr(p, "_sec_get", fake_get)
    # empty hits would trigger the yfinance fallback — stub it so no network.
    monkeypatch.setattr(p, "_fetch_insider_via_yfinance", lambda s, d: [])

    p._fetch_insider_trades("PEP", 90)

    par = captured["params"]
    assert par["dateRange"] == "custom"
    assert par.get("startdt") and par.get("enddt"), "custom range needs BOTH dates"
    # both must be valid YYYY-MM-DD and startdt <= enddt
    s = datetime.datetime.strptime(par["startdt"], "%Y-%m-%d")
    e = datetime.datetime.strptime(par["enddt"], "%Y-%m-%d")
    assert s <= e
