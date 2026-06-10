import json
from api.services import analyst_archive_service as arch
from src.utils.db import get_connection, init_db


def test_archive_writes_full_board(monkeypatch):
    init_db()
    monkeypatch.setattr(arch, "_universe", lambda: ["SYN_A1", "SYN_A2"])
    monkeypatch.setattr(arch, "_assemble_full",
                        lambda syms, d, **k: {s: {"momentum": {"trailing_return": 1.0},
                                                  "options_flow": 0.3} for s in syms})
    arch.archive_signals_for_date("2026-02-05")
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, signals_json FROM signal_archive WHERE as_of_date='2026-02-05'"
        ).fetchall()
        conn.execute("DELETE FROM signal_archive WHERE as_of_date='2026-02-05'")
        conn.commit()
    finally:
        conn.close()
    assert {r["symbol"] for r in rows} == {"SYN_A1", "SYN_A2"}
    assert "options_flow" in json.loads(rows[0]["signals_json"])   # full live board stored


def test_archive_is_idempotent(monkeypatch):
    init_db()
    monkeypatch.setattr(arch, "_universe", lambda: ["SYN_A1"])
    monkeypatch.setattr(arch, "_assemble_full",
                        lambda syms, d, **k: {s: {"momentum": None} for s in syms})
    arch.archive_signals_for_date("2026-02-05")
    arch.archive_signals_for_date("2026-02-05")  # second run must not duplicate / error
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM signal_archive WHERE as_of_date='2026-02-05' AND symbol='SYN_A1'"
        ).fetchone()["c"]
        conn.execute("DELETE FROM signal_archive WHERE as_of_date='2026-02-05'")
        conn.commit()
    finally:
        conn.close()
    assert n == 1   # INSERT OR REPLACE on (as_of_date, symbol) PK
