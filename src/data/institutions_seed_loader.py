"""Loaders for institutions + institution_holdings (Phase 7A).

Two CSVs:
    seeds/institutions.csv          — top institutions (CIK, name, type, AUM)
    seeds/institution_holdings.csv  — hand-seeded sample holdings for demo

Both loaders are idempotent. The holdings loader skips orphans (rows whose
symbol isn't in stocks_universe or whose CIK isn't in institutions).
Live SEC 13F-HR data overrides via `src/data/sec_13f_loader.py`.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.utils.db import get_connection, init_db


DEFAULT_INSTITUTIONS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seeds" / "institutions.csv"
)
DEFAULT_HOLDINGS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seeds" / "institution_holdings.csv"
)


VALID_TYPES: frozenset[str] = frozenset({
    "index_fund", "active_mgr", "hedge_fund", "pension", "sovereign",
})


def _coerce(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None


# ── institutions ───────────────────────────────────────────────


def parse_institutions_csv(path: Path | str = DEFAULT_INSTITUTIONS_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"institutions seed CSV not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        clean = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(clean)
    rows = []
    for raw in reader:
        cik = (raw.get("cik") or "").strip()
        name = (raw.get("name") or "").strip()
        if not cik or not name:
            continue
        type_ = (raw.get("type") or "").strip().lower()
        if type_ and type_ not in VALID_TYPES:
            print(f"[institutions] skip row with invalid type={type_!r}: {name}")
            continue
        try:
            aum = float(raw.get("total_aum") or 0) or None
        except ValueError:
            aum = None
        rows.append({
            "cik": cik,
            "name": name,
            "type": type_ or None,
            "total_aum": aum,
        })
    return rows


def load_institutions(
    path: Path | str = DEFAULT_INSTITUTIONS_PATH,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        rows = parse_institutions_csv(path)
        existing = {r["cik"] for r in conn.execute("SELECT cik FROM institutions").fetchall()}
        inserted = 0
        updated = 0
        for r in rows:
            if r["cik"] in existing:
                updated += 1
            else:
                inserted += 1
            conn.execute(
                """
                INSERT INTO institutions (cik, name, type, total_aum, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cik) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    total_aum = excluded.total_aum,
                    last_updated = excluded.last_updated
                """,
                (
                    r["cik"], r["name"], r["type"], r["total_aum"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()
        return {"inserted": inserted, "updated": updated, "total": len(rows)}
    finally:
        if own_conn:
            conn.close()


# ── holdings ───────────────────────────────────────────────────


def parse_holdings_csv(path: Path | str = DEFAULT_HOLDINGS_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"holdings seed CSV not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        clean = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(clean)
    rows = []
    for raw in reader:
        cik = (raw.get("cik") or "").strip()
        symbol = (raw.get("symbol") or "").strip().upper()
        as_of = (raw.get("as_of") or "").strip()
        if not cik or not symbol or not as_of:
            continue
        try:
            value_usd = float(raw.get("value_usd") or 0) or None
            pct_portfolio = float(raw.get("pct_portfolio") or 0) or None
            pct_outstanding = float(raw.get("pct_outstanding") or 0) or None
        except ValueError:
            continue
        rows.append({
            "cik": cik,
            "symbol": symbol,
            "value_usd": value_usd,
            "pct_portfolio": pct_portfolio,
            "pct_outstanding": pct_outstanding,
            "as_of": as_of,
            "notes": _coerce(raw.get("notes")),
        })
    return rows


def load_holdings(
    path: Path | str = DEFAULT_HOLDINGS_PATH,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Replace seed-loaded holdings with the contents of the CSV."""
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM institution_holdings WHERE source='hand'")
        deleted = cur.rowcount

        rows = parse_holdings_csv(path)
        valid_ciks = {r["cik"] for r in conn.execute("SELECT cik FROM institutions").fetchall()}
        valid_syms = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        }

        inserted = 0
        skipped_orphan = 0

        for r in rows:
            if r["cik"] not in valid_ciks or r["symbol"] not in valid_syms:
                skipped_orphan += 1
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO institution_holdings
                        (cik, symbol, value_usd, pct_portfolio, pct_outstanding,
                         as_of, source)
                    VALUES (?, ?, ?, ?, ?, ?, 'hand')
                    ON CONFLICT(cik, symbol, as_of) DO UPDATE SET
                        value_usd = excluded.value_usd,
                        pct_portfolio = excluded.pct_portfolio,
                        pct_outstanding = excluded.pct_outstanding,
                        source = 'hand'
                    """,
                    (
                        r["cik"], r["symbol"], r["value_usd"],
                        r["pct_portfolio"], r["pct_outstanding"], r["as_of"],
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                continue

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


def institution_count() -> int:
    init_db()
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
    finally:
        conn.close()


def holdings_count() -> int:
    init_db()
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM institution_holdings").fetchone()[0]
    finally:
        conn.close()


def load_all() -> dict[str, dict]:
    """Convenience: load institutions + holdings."""
    return {
        "institutions": load_institutions(),
        "holdings": load_holdings(),
    }
