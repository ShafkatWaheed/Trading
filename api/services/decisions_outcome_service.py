"""Grade AI decisions against actual price moves.

Two responsibilities:
  1. `evaluate_pending_decisions()`  — daily cron. Find any ai_decisions row
     whose prediction_window has passed and no outcome row exists yet, pull the
     current price, compute return_pct, and write an ai_decision_outcomes row.
  2. `get_track_record()` / `recent_decisions()` — aggregate accuracy stats and
     recent-decision listings for the Track Record dashboard.

Correctness rules per `source`:
  - recommendation : STRONG_BUY/BUY  → correct if return >= +2%
                     TRIM/SELL/STRONG_SELL → correct if return <= -2%
                     HOLD/BUY_ON_DIP → correct if -2% < return < +2%
  - ai_analyst    : BUY  → correct if return >= +1%
                     SELL → correct if return <= -1%
                     HOLD → correct if -1% < return < +1%
  - bubble_score   : score >= 70 (stretched/bubble) → correct if return <= 0
                     score < 30 (value zone)         → correct if return >= 0
                     30..70 (fair value)             → correct if -10% <= return <= +10%
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Iterable

from src.data.gateway import DataGateway
from src.utils.db import get_connection


# ── Correctness rules ─────────────────────────────────────────────


_RECOMMENDATION_BULL = {"STRONG_BUY", "BUY"}
_RECOMMENDATION_BEAR = {"TRIM", "SELL", "STRONG_SELL"}
_RECOMMENDATION_NEUTRAL = {"HOLD", "BUY_ON_DIP"}


def _grade_recommendation(decision: str, return_pct: float) -> bool:
    d = (decision or "").upper()
    if d in _RECOMMENDATION_BULL:
        return return_pct >= 2.0
    if d in _RECOMMENDATION_BEAR:
        return return_pct <= -2.0
    if d in _RECOMMENDATION_NEUTRAL:
        return -2.0 < return_pct < 2.0
    return False


def _grade_ai_analyst(decision: str, return_pct: float) -> bool:
    d = (decision or "").upper()
    if d == "BUY":
        return return_pct >= 1.0
    if d == "SELL":
        return return_pct <= -1.0
    if d == "HOLD":
        return -1.0 < return_pct < 1.0
    return False


def _grade_bubble_score(score: float | None, return_pct: float) -> bool:
    if score is None:
        return False
    if score >= 70.0:
        return return_pct <= 0.0
    if score < 30.0:
        return return_pct >= 0.0
    # Fair value band: expect movement to stay roughly contained.
    return -10.0 <= return_pct <= 10.0


def _grade(source: str, decision: str, score: float | None, return_pct: float) -> bool:
    if source == "recommendation":
        return _grade_recommendation(decision, return_pct)
    if source == "ai_analyst":
        return _grade_ai_analyst(decision, return_pct)
    if source == "bubble_score":
        return _grade_bubble_score(score, return_pct)
    # Unknown source — conservative default.
    return False


# ── Price snapshot ────────────────────────────────────────────────


_PRICE_CACHE: dict[str, float | None] = {}


def _current_price(symbol: str) -> float | None:
    """Latest close from yfinance via DataGateway. Memoized per-run."""
    if symbol in _PRICE_CACHE:
        return _PRICE_CACHE[symbol]
    try:
        hist = DataGateway().get_historical(symbol, period_days=10)
        if hist is None or hist.empty:
            _PRICE_CACHE[symbol] = None
            return None
        price = float(hist["close"].iloc[-1])
        _PRICE_CACHE[symbol] = price
        return price
    except Exception:
        _PRICE_CACHE[symbol] = None
        return None


# ── Evaluator (daily cron entry point) ────────────────────────────


def evaluate_pending_decisions(limit: int | None = None) -> dict:
    """Grade all decisions whose prediction_window has passed and have no outcome yet.

    Returns counters for logging / observability.
    """
    _PRICE_CACHE.clear()
    conn = get_connection()
    try:
        now = datetime.utcnow()
        # Pull decisions whose window ended on or before now and have no outcome row.
        sql = """
            SELECT d.id, d.created_at, d.symbol, d.source, d.decision, d.score,
                   d.price_at_call, d.prediction_window_days
            FROM ai_decisions AS d
            LEFT JOIN ai_decision_outcomes AS o ON o.decision_id = d.id
            WHERE o.decision_id IS NULL
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql).fetchall()

        evaluated = 0
        skipped_pending = 0
        skipped_no_price = 0
        correct = 0

        for r in rows:
            try:
                created = datetime.fromisoformat(r["created_at"].rstrip("Z"))
            except Exception:
                # Malformed timestamp — skip, never break the cron.
                continue
            window = timedelta(days=int(r["prediction_window_days"]))
            if created + window > now:
                skipped_pending += 1
                continue

            price_now = _current_price(r["symbol"])
            if price_now is None or r["price_at_call"] is None or r["price_at_call"] <= 0:
                skipped_no_price += 1
                continue

            return_pct = ((price_now - float(r["price_at_call"])) / float(r["price_at_call"])) * 100.0
            was_correct = _grade(r["source"], r["decision"], r["score"], return_pct)

            conn.execute(
                """
                INSERT OR REPLACE INTO ai_decision_outcomes
                  (decision_id, evaluated_at, price_now, return_pct, was_correct, notes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(r["id"]), now.isoformat() + "Z", float(price_now),
                    float(return_pct), 1 if was_correct else 0,
                    json.dumps({"rule_version": 1}),
                ),
            )
            evaluated += 1
            if was_correct:
                correct += 1

        conn.commit()
        return {
            "ran_at": now.isoformat() + "Z",
            "candidates": len(rows),
            "evaluated": evaluated,
            "correct": correct,
            "incorrect": evaluated - correct,
            "skipped_pending": skipped_pending,
            "skipped_no_price": skipped_no_price,
        }
    finally:
        conn.close()


# ── Aggregations for the dashboard ────────────────────────────────


def _row_to_dict(r) -> dict:
    return {k: r[k] for k in r.keys()}


def get_track_record(
    source: str | None = None,
    symbol: str | None = None,
    days: int | None = 90,
) -> dict:
    """Aggregate accuracy across decisions whose window has been graded.

    Filters:
      - `source`  : 'recommendation' | 'ai_analyst' | 'bubble_score' | None (all)
      - `symbol`  : specific ticker or None (all)
      - `days`    : how many days back from now to include (by created_at). None = all-time.
    """
    conn = get_connection()
    try:
        where = ["o.decision_id IS NOT NULL"]
        params: list = []
        if source:
            where.append("d.source = ?")
            params.append(source)
        if symbol:
            where.append("d.symbol = ?")
            params.append(symbol.upper())
        if days:
            cutoff = (datetime.utcnow() - timedelta(days=int(days))).isoformat() + "Z"
            where.append("d.created_at >= ?")
            params.append(cutoff)

        where_sql = " AND ".join(where)

        overall = conn.execute(
            f"""
            SELECT COUNT(*)               AS total,
                   SUM(o.was_correct)     AS correct,
                   AVG(o.return_pct)      AS avg_return,
                   AVG(CASE WHEN o.was_correct=1 THEN o.return_pct ELSE NULL END) AS avg_win_return,
                   AVG(CASE WHEN o.was_correct=0 THEN o.return_pct ELSE NULL END) AS avg_loss_return
            FROM ai_decisions AS d
            JOIN ai_decision_outcomes AS o ON o.decision_id = d.id
            WHERE {where_sql}
            """,
            params,
        ).fetchone()

        per_source = conn.execute(
            f"""
            SELECT d.source                AS source,
                   COUNT(*)                AS total,
                   SUM(o.was_correct)      AS correct,
                   AVG(o.return_pct)       AS avg_return
            FROM ai_decisions AS d
            JOIN ai_decision_outcomes AS o ON o.decision_id = d.id
            WHERE {where_sql}
            GROUP BY d.source
            ORDER BY d.source
            """,
            params,
        ).fetchall()

        pending = conn.execute(
            f"""
            SELECT COUNT(*) AS pending
            FROM ai_decisions AS d
            LEFT JOIN ai_decision_outcomes AS o ON o.decision_id = d.id
            WHERE o.decision_id IS NULL
              { ("AND d.source = ?" if source else "") }
              { ("AND d.symbol = ?" if symbol else "") }
            """,
            ([source] if source else []) + ([symbol.upper()] if symbol else []),
        ).fetchone()

        total = int(overall["total"] or 0)
        correct = int(overall["correct"] or 0)
        accuracy_pct = round((correct / total) * 100.0, 1) if total else 0.0

        by_source = [
            {
                "source": r["source"],
                "total": int(r["total"]),
                "correct": int(r["correct"] or 0),
                "accuracy_pct": round((int(r["correct"] or 0) / int(r["total"])) * 100.0, 1) if r["total"] else 0.0,
                "avg_return_pct": round(float(r["avg_return"] or 0.0), 2),
            }
            for r in per_source
        ]

        return {
            "filter": {"source": source, "symbol": symbol, "days": days},
            "overall": {
                "total": total,
                "correct": correct,
                "accuracy_pct": accuracy_pct,
                "avg_return_pct": round(float(overall["avg_return"] or 0.0), 2),
                "avg_win_return_pct": round(float(overall["avg_win_return"] or 0.0), 2),
                "avg_loss_return_pct": round(float(overall["avg_loss_return"] or 0.0), 2),
            },
            "by_source": by_source,
            "pending_count": int(pending["pending"] or 0),
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
    finally:
        conn.close()


def recent_decisions(
    source: str | None = None,
    symbol: str | None = None,
    limit: int = 50,
) -> dict:
    """Recent decisions log with outcome (or 'pending') joined."""
    conn = get_connection()
    try:
        where = ["1=1"]
        params: list = []
        if source:
            where.append("d.source = ?")
            params.append(source)
        if symbol:
            where.append("d.symbol = ?")
            params.append(symbol.upper())
        where_sql = " AND ".join(where)
        params.append(int(max(1, min(limit, 500))))

        rows = conn.execute(
            f"""
            SELECT d.id, d.created_at, d.symbol, d.source, d.decision, d.score,
                   d.price_at_call, d.prediction_window_days, d.context_json,
                   d.metadata_json,
                   o.evaluated_at, o.price_now, o.return_pct, o.was_correct
            FROM ai_decisions AS d
            LEFT JOIN ai_decision_outcomes AS o ON o.decision_id = d.id
            WHERE {where_sql}
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        items = []
        for r in rows:
            ctx = json.loads(r["context_json"]) if r["context_json"] else None
            meta = json.loads(r["metadata_json"]) if r["metadata_json"] else None
            evaluated = r["evaluated_at"] is not None
            items.append({
                "id": int(r["id"]),
                "created_at": r["created_at"],
                "symbol": r["symbol"],
                "source": r["source"],
                "decision": r["decision"],
                "score": float(r["score"]) if r["score"] is not None else None,
                "price_at_call": float(r["price_at_call"]),
                "prediction_window_days": int(r["prediction_window_days"]),
                "context": ctx,
                "metadata": meta,
                "status": (
                    "correct" if (evaluated and r["was_correct"] == 1)
                    else "incorrect" if evaluated
                    else "pending"
                ),
                "evaluated_at": r["evaluated_at"],
                "price_now": float(r["price_now"]) if r["price_now"] is not None else None,
                "return_pct": float(r["return_pct"]) if r["return_pct"] is not None else None,
            })

        return {
            "filter": {"source": source, "symbol": symbol, "limit": limit},
            "items": items,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
    finally:
        conn.close()


def top_wins_and_losses(limit: int = 10, days: int | None = 90) -> dict:
    """Sortable top wins and losses by return_pct, filtered to graded decisions."""
    conn = get_connection()
    try:
        where = ["o.decision_id IS NOT NULL"]
        params: list = []
        if days:
            cutoff = (datetime.utcnow() - timedelta(days=int(days))).isoformat() + "Z"
            where.append("d.created_at >= ?")
            params.append(cutoff)
        where_sql = " AND ".join(where)

        def _fetch(order: str) -> list[dict]:
            rows = conn.execute(
                f"""
                SELECT d.id, d.created_at, d.symbol, d.source, d.decision,
                       d.price_at_call, o.return_pct, o.was_correct
                FROM ai_decisions AS d
                JOIN ai_decision_outcomes AS o ON o.decision_id = d.id
                WHERE {where_sql}
                ORDER BY o.return_pct {order}
                LIMIT ?
                """,
                params + [int(limit)],
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

        return {
            "wins": _fetch("DESC"),
            "losses": _fetch("ASC"),
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
    finally:
        conn.close()
