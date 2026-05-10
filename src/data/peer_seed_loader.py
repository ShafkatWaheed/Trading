"""Loader for `seeds/tier_a_peers.csv` → `stock_peers` table.

Seeds the hand-curated Tier A peer edges with `source='hand'` and
`confidence='high'`. Idempotent — re-running deletes seed-loaded rows
first, then re-inserts.

Skips edges whose `from_symbol` or `to_symbol` is not yet in
`stocks_universe` (and counts them) so the seed can include forward
references to Tier B/C names that haven't been loaded yet via the
yfinance pull. Once the universe expands, re-running the loader picks
those up.

Cross-industry peers (e.g. MSFT-AMZN cloud overlap that crosses sector)
live in a separate seed file at the same path but with
`tier_a_cross_industry_peers.csv`.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.utils.db import get_connection, init_db

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seeds" / "tier_a_peers.csv"
)
DEFAULT_CROSS_INDUSTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "seeds" / "tier_a_cross_industry_peers.csv"
)

# Source tag for hand-loaded rows (matches stock_peers.source values).
SEED_SOURCE_HAND = "hand"
SEED_CONFIDENCE_HIGH = "high"


def _coerce(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None


def parse_peer_csv(path: Path | str) -> list[dict]:
    """Parse a peer-edge CSV. Skips comment lines (#) and blank rows."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"peer seed CSV not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        clean = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(clean)
    out: list[dict] = []
    for raw in reader:
        from_sym = (raw.get("from_symbol") or "").strip().upper()
        to_sym = (raw.get("to_symbol") or "").strip().upper()
        if not from_sym or not to_sym or from_sym == to_sym:
            continue
        try:
            similarity = float(raw.get("similarity") or 0)
        except ValueError:
            continue
        out.append({
            "from_symbol": from_sym,
            "to_symbol": to_sym,
            "similarity": max(0.0, min(1.0, similarity)),
            "overlap_dimensions": _coerce(raw.get("overlap_dimensions")),
            "notes": _coerce(raw.get("notes")),
        })
    return out


def _existing_universe(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT symbol FROM stocks_universe").fetchall()
    return {r["symbol"] for r in rows}


def _insert_or_update(
    conn: sqlite3.Connection,
    *,
    from_sym: str,
    to_sym: str,
    similarity: float,
    overlap_dimensions: str | None,
    notes: str | None,
) -> None:
    """Upsert one (from_sym, to_sym) row. Conflict update keeps newest values."""
    conn.execute(
        """
        INSERT INTO stock_peers
            (from_symbol, to_symbol, similarity, overlap_dimensions, source, confidence, evidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(from_symbol, to_symbol) DO UPDATE SET
            similarity = excluded.similarity,
            overlap_dimensions = excluded.overlap_dimensions,
            source = excluded.source,
            confidence = excluded.confidence,
            evidence = excluded.evidence
        """,
        (
            from_sym, to_sym, similarity, overlap_dimensions,
            SEED_SOURCE_HAND, SEED_CONFIDENCE_HIGH, notes,
        ),
    )


def load_tier_a_peers(
    path: Path | str = DEFAULT_SEED_PATH,
    *,
    bidirectional: bool = True,
    wipe_existing: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Load the within-industry hand peer edges.

    Args:
        path: CSV file to load.
        bidirectional: if True (default), also write the reverse edge for each
            row so neighbor queries from either side return results.
        wipe_existing: if True (default), delete all `source='hand'` rows
            before inserting. Set False when chaining a second hand-seed file
            that should ADD to (not replace) the prior load — for instance
            `load_cross_industry_peers` after `load_tier_a_peers`.

    Returns counts dict: deleted, inserted, skipped_orphan, total_input.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        if wipe_existing:
            cur = conn.execute(f"DELETE FROM stock_peers WHERE source='{SEED_SOURCE_HAND}'")
            deleted = cur.rowcount
        else:
            deleted = 0

        rows = parse_peer_csv(path)
        universe = _existing_universe(conn)

        inserted = 0
        skipped_orphan = 0

        for r in rows:
            if r["from_symbol"] not in universe or r["to_symbol"] not in universe:
                skipped_orphan += 1
                continue
            _insert_or_update(
                conn,
                from_sym=r["from_symbol"],
                to_sym=r["to_symbol"],
                similarity=r["similarity"],
                overlap_dimensions=r["overlap_dimensions"],
                notes=r["notes"],
            )
            inserted += 1
            if bidirectional:
                _insert_or_update(
                    conn,
                    from_sym=r["to_symbol"],
                    to_sym=r["from_symbol"],
                    similarity=r["similarity"],
                    overlap_dimensions=r["overlap_dimensions"],
                    notes=r["notes"],
                )
                inserted += 1

        conn.commit()
        return {
            "deleted": deleted,
            "inserted": inserted,
            "skipped_orphan": skipped_orphan,
            "total_input": len(rows),
        }
    finally:
        if own_conn:
            conn.close()


def load_cross_industry_peers(
    path: Path | str = DEFAULT_CROSS_INDUSTRY_PATH,
    *,
    bidirectional: bool = True,
) -> dict[str, int]:
    """Load the cross-industry hand peer edges (e.g. MSFT↔AMZN cloud overlap).

    Adds to the within-industry hand seed without wiping it. Call this AFTER
    `load_tier_a_peers()` so both sets coexist.
    """
    if not Path(path).exists():
        # Acceptable: the cross-industry seed is optional. Skip cleanly.
        return {"deleted": 0, "inserted": 0, "skipped_orphan": 0, "total_input": 0}
    return load_tier_a_peers(path, bidirectional=bidirectional, wipe_existing=False)


def load_all_hand_peers() -> dict[str, int]:
    """Convenience: wipe + reload BOTH within-industry and cross-industry hand seeds.

    Call this when you want a clean slate of hand-curated peers. Idempotent
    end-to-end — safe to run repeatedly.
    """
    a = load_tier_a_peers(wipe_existing=True)
    b = load_cross_industry_peers()
    return {
        "deleted": a["deleted"],
        "inserted": a["inserted"] + b["inserted"],
        "skipped_orphan": a["skipped_orphan"] + b["skipped_orphan"],
        "total_input": a["total_input"] + b["total_input"],
    }


def peer_counts() -> dict[str, int]:
    """Diagnostic: rows per source for stock_peers."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT source, COUNT(*) FROM stock_peers GROUP BY source"
        ).fetchall()
        out = {row[0] or "(null)": row[1] for row in rows}
        out["total"] = sum(out.values())
        return out
    finally:
        conn.close()
