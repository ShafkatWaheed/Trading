"""Daily full-board signal archive — written every LIVE day so future
backtests read honest stored history instead of reconstructing it."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from api.services import analyst_pit_service, predictions_service
from src.utils.db import get_connection, init_db

_universe = predictions_service._load_universe_ab


def _assemble_full(symbols, as_of, **kw):
    return analyst_pit_service.assemble_full(symbols, as_of, allow_live_search=True)


def archive_signals_for_date(as_of: str) -> dict:
    """Store the full live signal board for every universe symbol on `as_of`.
    Idempotent per (date, symbol). Live-only signals (options/premarket/reddit)
    are included since this runs live."""
    init_db()
    packets = _assemble_full(_universe(), as_of)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        for sym, pkt in packets.items():
            conn.execute(
                "INSERT OR REPLACE INTO signal_archive (as_of_date, symbol, signals_json, captured_at) "
                "VALUES (?,?,?,?)",
                (as_of, sym, json.dumps(pkt, default=str), now),
            )
        conn.commit()
        return {"date": as_of, "archived": len(packets)}
    finally:
        conn.close()
