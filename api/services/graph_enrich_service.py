"""On-demand graph enrichment for a single symbol.

Reuses `src.data.sec_10k_extractor.process_symbol` (the batch nightly
pipeline that already mines suppliers/customers/JVs from 10-K Item 1A)
but with three deltas:
  1. Single-symbol entry point invoked from the Deep Dive page
  2. Opus model (vs Haiku in the batch path) — quality matters more here
     since the user is staring at sparse connections waiting for results
  3. Runs in a background job with heartbeats so the Deep Dive UI can
     poll for progress and auto-reload when done

The output writes the SAME `stock_relations` rows with the same
`evidence: '10k_mined: ...'` prefix the batch path uses. Hand-curated
edges (`evidence LIKE 'seed:hand%'`) are protected from overwrite.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.services._background_jobs import (
    get_job_status,
    heartbeat,
    kick,
)
from src.data.sec_10k_extractor import process_symbol
from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


def _job_key(symbol: str) -> str:
    return f"graph_enrich:{symbol.upper()}"


# 1 enrichment per stock per day — Claude isn't free even on subscription,
# and the underlying 10-K doesn't change daily. Re-running within the
# cooldown is a no-op.
_COOLDOWN_HOURS = 24


def _was_enriched_recently(symbol: str) -> bool:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT MAX(last_verified_at) AS ts
              FROM stock_relations
             WHERE from_symbol = ? AND evidence LIKE '10k_mined:%'
            """,
            (symbol.upper(),),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["ts"]:
        return False
    try:
        ts = datetime.fromisoformat(row["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    age_h = (datetime.now(tz=timezone.utc) - ts).total_seconds() / 3600
    return age_h < _COOLDOWN_HOURS


def _ask_claude_opus(prompt: str, *, model: str = "opus") -> dict | None:
    """Bind the extractor's Claude call to Opus + a longer timeout.

    The default `ask_claude_json` signature only takes `model` as kwarg —
    we pass through model + a 5-min timeout since Opus is slower.
    """
    return ask_claude_json(prompt, model=model, timeout=300, retries=1)


def _run_enrichment(symbol: str) -> dict:
    """The actual work — runs inside the background thread."""
    jk = _job_key(symbol)

    heartbeat(jk, phase="fetching_10k", progress_pct=10)

    if _was_enriched_recently(symbol):
        heartbeat(jk, phase="done", progress_pct=100)
        return {
            "symbol":        symbol,
            "edges_written": 0,
            "skipped":       True,
            "reason":        "enriched_within_cooldown",
        }

    heartbeat(jk, phase="extracting", progress_pct=30)

    result = process_symbol(
        symbol,
        # process_symbol expects extract_fn(prompt, model=...) — _ask_claude_opus
        # binds model to opus + 5-min timeout. Drop-in compatible.
        extract_fn=_ask_claude_opus,
        model="opus",
    )

    heartbeat(jk, phase="done", progress_pct=95)
    return result


def kick_enrichment(symbol: str) -> dict:
    """Idempotent kick — returns existing job status if already running."""
    sym = symbol.upper()
    jk = _job_key(sym)

    existing = get_job_status(jk)
    if existing and existing.get("status") == "running":
        return {
            "kicked":      False,
            "already_running": True,
            "job":         existing,
            "symbol":      sym,
        }

    if _was_enriched_recently(sym):
        return {
            "kicked":  False,
            "reason":  "enriched_within_cooldown",
            "symbol":  sym,
        }

    kick(jk, _run_enrichment, sym)
    return {"kicked": True, "job_key": jk, "symbol": sym}


def get_enrichment_status(symbol: str) -> dict:
    """For frontend polling — returns current job state + cooldown info."""
    jk = _job_key(symbol)
    job = get_job_status(jk)
    return {
        "symbol":              symbol.upper(),
        "job":                 job,
        "in_cooldown":         _was_enriched_recently(symbol),
        "cooldown_hours":      _COOLDOWN_HOURS,
    }
