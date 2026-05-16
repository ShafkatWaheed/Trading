"""Manual-refresh service.

User clicks a button in the React UI → a `refresh_jobs` row is created and a
worker thread runs the corresponding pipeline. The UI polls
`GET /refresh/jobs/{id}` to draw the progress bar.

Each refresh kind has:
  * a `runner` callable (synchronous) that does the work
  * a `progress` callable that returns (processed, total) while the runner
    is in flight — used to update the row periodically

Concurrency: at most one running job per `kind` at a time. Other kinds can
run in parallel.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime
from typing import Callable

from src.utils.db import get_connection, init_db


# ── kind registry ────────────────────────────────────────────────────


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _count(sql: str, params: tuple = ()) -> int:
    conn = get_connection()
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


# Runner functions (kept thin — heavy lifting lives in src/*).

def _run_universe() -> dict:
    from src.data.index_loader import fetch_all_indices, refresh_universe_from_cache
    fetch_all_indices()
    return refresh_universe_from_cache()


def _run_industries() -> dict:
    from src.data.industry_loader import apply_yfinance_industries
    return apply_yfinance_industries(log=False)


def _run_conglomerate() -> dict:
    from src.data.conglomerate_overrides import apply_conglomerate_overrides
    return apply_conglomerate_overrides()


def _run_peers() -> dict:
    from src.data.peer_jobs import run_pending_jobs
    return run_pending_jobs(tiers=["B", "C"], log=False)


def _run_causal() -> dict:
    from src.data.causal_extractor import run_for_tiers
    return run_for_tiers(["A", "B"], log=False)


def _run_tenk() -> dict:
    from src.data.sec_10k_extractor import run_for_tier
    return run_for_tier(tier="A", log=False)


def _run_13f_overlap() -> dict:
    from src.graph.institutional_overlap import materialise_overlap_edges
    return materialise_overlap_edges()


def _run_freshness() -> dict:
    from src.freshness.orchestrator import run_orchestrator
    conn = get_connection()
    try:
        symbols = [
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        ]
    finally:
        conn.close()
    return run_orchestrator(symbols, log=False)


# Progress probes — return (processed, total). Called every few seconds
# while a runner is in flight. If a kind doesn't have a meaningful progress
# signal, return (0, 0) — the UI will show an indeterminate spinner.

def _prog_universe() -> tuple[int, int]:
    n = _count("SELECT COUNT(*) FROM stocks_universe")
    # Best-effort universe target: total ETF holdings × 1.5 fudge. Use the
    # current count as both — the bar shows ~100% almost immediately.
    return n, max(n, 1)


def _prog_industries() -> tuple[int, int]:
    processed = _count("SELECT COUNT(DISTINCT symbol) FROM stock_industry")
    total = _count("SELECT COUNT(*) FROM stocks_universe")
    return processed, total


def _prog_conglomerate() -> tuple[int, int]:
    return 0, 0  # near-instant


def _prog_peers() -> tuple[int, int]:
    done = _count("SELECT COUNT(*) FROM peer_jobs WHERE status='done'")
    total = _count("SELECT COUNT(*) FROM peer_jobs")
    # Note: total can grow as new industries get queued mid-run — that's fine,
    # the bar will adjust.
    return done, total


def _prog_causal() -> tuple[int, int]:
    done = _count("SELECT COUNT(*) FROM causal_jobs WHERE status='done'")
    total = _count(
        "SELECT COUNT(*) FROM stocks_universe WHERE tier IN ('A','B')"
    )
    return done, total


def _prog_tenk() -> tuple[int, int]:
    done = _count("SELECT COUNT(*) FROM tenk_jobs WHERE status='done'")
    total = _count("SELECT COUNT(*) FROM stocks_universe WHERE tier='A'")
    return done, total


def _prog_13f_overlap() -> tuple[int, int]:
    return 0, 0


def _prog_freshness() -> tuple[int, int]:
    # Layers 1-3 each touch every stock; sum of processed runs as a stand-in.
    processed = _count(
        "SELECT COUNT(*) FROM edge_freshness "
        "WHERE last_extracted_at IS NOT NULL OR last_filing_check IS NOT NULL"
    )
    total = _count("SELECT COUNT(*) FROM stocks_universe")
    return processed, total


KIND_REGISTRY: dict[str, tuple[Callable[[], dict], Callable[[], tuple[int, int]], str]] = {
    "universe":      (_run_universe,    _prog_universe,    "Pull S&P/R1k/R2k ETF holdings and upsert stocks_universe."),
    "industries":    (_run_industries,  _prog_industries,  "Pull yfinance industry tag for every untagged stock."),
    "conglomerate":  (_run_conglomerate, _prog_conglomerate, "Re-apply hand-curated conglomerate multi-tag overrides."),
    "peers":         (_run_peers,       _prog_peers,       "Rank Tier B/C peers per industry via Claude."),
    "causal":        (_run_causal,      _prog_causal,      "Extract commodity exposures for Tier A+B via Claude."),
    "tenk_mining":   (_run_tenk,        _prog_tenk,        "Mine Tier A 10-K Item 1A for named suppliers/customers."),
    "13f_overlap":   (_run_13f_overlap, _prog_13f_overlap, "Re-materialise common-institutional-holder edges."),
    "freshness":     (_run_freshness,   _prog_freshness,   "Run 5-layer freshness orchestrator and queue drift."),
}


# ── public API ───────────────────────────────────────────────────────


def list_kinds() -> list[dict]:
    """Return [{kind, description}] for the UI to render the card list."""
    return [
        {"kind": k, "description": d}
        for k, (_, _, d) in KIND_REGISTRY.items()
    ]


def list_jobs(kind: str | None = None, limit: int = 20) -> list[dict]:
    init_db()
    conn = get_connection()
    try:
        if kind:
            rows = conn.execute(
                "SELECT * FROM refresh_jobs WHERE kind = ? ORDER BY id DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM refresh_jobs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job(job_id: int) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM refresh_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def latest_per_kind() -> dict[str, dict]:
    """Return {kind: most_recent_job_row} for quick UI rendering."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM refresh_jobs
            WHERE id IN (
                SELECT MAX(id) FROM refresh_jobs GROUP BY kind
            )
            """
        ).fetchall()
        return {r["kind"]: dict(r) for r in rows}
    finally:
        conn.close()


class KindAlreadyRunning(Exception):
    """Raised when a job of the same kind is already running."""


def start_job(kind: str) -> dict:
    """Create a job row + spawn a worker thread.

    Raises:
        KeyError         — unknown kind
        KindAlreadyRunning — a job of the same kind is currently running
    """
    if kind not in KIND_REGISTRY:
        raise KeyError(f"unknown refresh kind: {kind}")

    init_db()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM refresh_jobs WHERE kind = ? AND status IN ('queued','running')",
            (kind,),
        ).fetchone()
        if existing:
            raise KindAlreadyRunning(
                f"refresh '{kind}' is already running (job_id={existing['id']})"
            )

        cur = conn.execute(
            "INSERT INTO refresh_jobs (kind, status, started_at) VALUES (?, 'queued', ?)",
            (kind, _now()),
        )
        job_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    t = threading.Thread(target=_worker, args=(job_id, kind), daemon=True)
    t.start()

    return get_job(job_id)  # type: ignore[return-value]


# ── worker thread ────────────────────────────────────────────────────


def _update(
    job_id: int,
    *,
    status: str | None = None,
    processed: int | None = None,
    total: int | None = None,
    progress: float | None = None,
    message: str | None = None,
    error: str | None = None,
    result_json: str | None = None,
    finished_at: str | None = None,
) -> None:
    conn = get_connection()
    try:
        sets = []
        params: list = []
        for col, val in [
            ("status", status), ("processed", processed), ("total", total),
            ("progress", progress), ("message", message), ("error", error),
            ("result_json", result_json), ("finished_at", finished_at),
        ]:
            if val is not None:
                sets.append(f"{col} = ?")
                params.append(val)
        if not sets:
            return
        params.append(job_id)
        conn.execute(f"UPDATE refresh_jobs SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def _worker(job_id: int, kind: str) -> None:
    runner, progress_fn, _desc = KIND_REGISTRY[kind]

    _update(job_id, status="running", message="starting")

    stop_progress = threading.Event()

    def _progress_loop() -> None:
        while not stop_progress.is_set():
            try:
                processed, total = progress_fn()
                pct = (processed / total) if total > 0 else 0.0
                _update(job_id, processed=processed, total=total, progress=pct)
            except Exception:
                pass
            stop_progress.wait(timeout=3.0)

    poller = threading.Thread(target=_progress_loop, daemon=True)
    poller.start()

    try:
        result = runner()
        stop_progress.set()
        poller.join(timeout=2.0)
        # Final progress sweep
        try:
            processed, total = progress_fn()
            pct = (processed / total) if total > 0 else 1.0
        except Exception:
            processed, total, pct = 0, 0, 1.0

        _update(
            job_id,
            status="done",
            progress=max(pct, 1.0) if pct >= 0.99 else pct,
            processed=processed,
            total=total,
            result_json=json.dumps(result) if isinstance(result, (dict, list)) else None,
            message="completed",
            finished_at=_now(),
        )
    except Exception as exc:
        stop_progress.set()
        poller.join(timeout=2.0)
        err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        _update(
            job_id,
            status="failed",
            error=err,
            message="failed",
            finished_at=_now(),
        )


# ── universe quality snapshot (for the UI's right-side panel) ────────


def quality_snapshot() -> dict:
    """Return a single-shot summary of the graph's current state.

    The UI uses this to render quality cards next to the refresh buttons:
    universe size by tier, industry tag coverage, edge counts by source,
    institutional holdings, freshness status histogram.
    """
    init_db()
    conn = get_connection()
    try:
        def fetch_grouped(sql: str) -> dict:
            return {r[0]: r[1] for r in conn.execute(sql).fetchall()}

        def fetch_one(sql: str) -> int:
            r = conn.execute(sql).fetchone()
            return int(r[0]) if r and r[0] is not None else 0

        # latest stamps from refresh_jobs per kind
        latest_jobs = {}
        for r in conn.execute(
            """
            SELECT kind, status, finished_at FROM refresh_jobs
            WHERE id IN (SELECT MAX(id) FROM refresh_jobs GROUP BY kind)
            """
        ).fetchall():
            latest_jobs[r["kind"]] = {
                "status": r["status"],
                "finished_at": r["finished_at"],
            }

        return {
            "universe": {
                "total": fetch_one("SELECT COUNT(*) FROM stocks_universe"),
                "by_tier": fetch_grouped(
                    "SELECT tier, COUNT(*) FROM stocks_universe GROUP BY tier"
                ),
            },
            "industries": {
                "stock_industry_rows": fetch_one("SELECT COUNT(*) FROM stock_industry"),
                "tagged_symbols": fetch_one(
                    "SELECT COUNT(DISTINCT symbol) FROM stock_industry"
                ),
                "distinct_industries": fetch_one("SELECT COUNT(*) FROM industries"),
            },
            "peers": {
                "by_source": fetch_grouped(
                    "SELECT source, COUNT(*) FROM stock_peers GROUP BY source"
                ),
            },
            "relations": {
                "by_type": fetch_grouped(
                    "SELECT relation_type, COUNT(*) FROM stock_relations GROUP BY relation_type"
                ),
            },
            "commodity_exposures": {
                "by_source": fetch_grouped(
                    "SELECT source, COUNT(*) FROM stock_commodity_exposure GROUP BY source"
                ),
            },
            "institutional": {
                "holdings_total": fetch_one("SELECT COUNT(*) FROM institution_holdings"),
                "by_source": fetch_grouped(
                    "SELECT source, COUNT(*) FROM institution_holdings GROUP BY source"
                ),
            },
            "freshness": {
                "by_status": fetch_grouped(
                    "SELECT status, COUNT(*) FROM edge_freshness GROUP BY status"
                ),
            },
            "latest_jobs": latest_jobs,
        }
    finally:
        conn.close()
