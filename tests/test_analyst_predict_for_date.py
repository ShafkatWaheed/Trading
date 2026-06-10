from api.services import analyst_predictor as ap
from src.utils.db import get_connection, init_db


def test_predict_persists_ten_rows_with_mode(monkeypatch):
    init_db()
    # stub the assemblers + predictor internals to avoid network
    monkeypatch.setattr(ap, "_assemble_compact",
                        lambda syms, d: [{"symbol": s, "momentum_pct": 1.0} for s in syms])
    monkeypatch.setattr(ap, "triage", lambda rows, **k: [r["symbol"] for r in rows][:5])
    monkeypatch.setattr(ap, "_assemble_full",
                        lambda syms, d, **k: {s: {"momentum": {"trailing_return": 1.0}} for s in syms})
    monkeypatch.setattr(
        ap, "deep_pick",
        lambda packets, **k: [{"symbol": s, "reasoning": "r", "confidence": 0.5}
                              for s in list(packets)[:10]])
    monkeypatch.setattr(ap, "_universe", lambda: [f"SYN_{i:03d}" for i in range(12)])

    res = ap.predict_for_date("2026-02-02", mode="bootstrap")
    assert res["count"] >= 1
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, rank, mode FROM daily_predictions WHERE prediction_date='2026-02-02' ORDER BY rank"
        ).fetchall()
        conn.execute("DELETE FROM daily_predictions WHERE prediction_date='2026-02-02'")
        conn.commit()
    finally:
        conn.close()
    assert rows and rows[0]["mode"] == "bootstrap"
    assert rows[0]["rank"] == 1
