from api.services import predictions_service as ps
from src.utils.db import get_connection, init_db


def test_ensure_creates_ai_analyst_strategy():
    init_db()
    v = ps.ensure_ai_analyst_strategy()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT name, config_json FROM prediction_strategies WHERE version=?", (v,)
        ).fetchone()
    finally:
        conn.close()
    assert row["name"] == "ai_analyst_v1"
    import json
    cfg = json.loads(row["config_json"])
    assert cfg["ranking_signal"] == "ai_analyst"
    assert cfg["universe_tier"] == "AB"


def test_ensure_is_idempotent():
    init_db()
    v1 = ps.ensure_ai_analyst_strategy()
    v2 = ps.ensure_ai_analyst_strategy()
    assert v1 == v2  # no duplicate row
