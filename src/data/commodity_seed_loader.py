"""Loaders for commodities + stock_commodity_exposure (Phase 6).

Two CSVs feed the commodity layer:
    seeds/commodities.csv               — 30 commodity nodes
    seeds/tier_a_commodity_exposure.csv — ~150 hand-curated stock↔commodity edges

Both loaders are idempotent (UPSERT on conflict). The exposure loader skips
rows whose `symbol` is not in `stocks_universe` or whose `commodity_code` is
not in `commodities` so forward references resolve cleanly when the universe
expands.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.utils.db import get_connection, init_db

DEFAULT_COMMODITIES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seeds" / "commodities.csv"
)
DEFAULT_EXPOSURE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "seeds" / "tier_a_commodity_exposure.csv"
)

# Source tag for hand-loaded rows (matches stock_commodity_exposure.source values).
SEED_SOURCE_HAND = "hand"
SEED_CONFIDENCE_HIGH = "high"


def _coerce(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None


# ── commodities CSV ──────────────────────────────────────────────


def parse_commodities_csv(path: Path | str = DEFAULT_COMMODITIES_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"commodities seed CSV not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        clean = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(clean)
    out = []
    for raw in reader:
        code = (raw.get("code") or "").strip().lower()
        name = (raw.get("name") or "").strip()
        if not code or not name:
            continue
        out.append({
            "code": code,
            "name": name,
            "unit": _coerce(raw.get("unit")),
            "benchmark_ticker": _coerce(raw.get("benchmark_ticker")),
            "description": _coerce(raw.get("description")),
        })
    return out


def load_commodities(
    path: Path | str = DEFAULT_COMMODITIES_PATH,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        rows = parse_commodities_csv(path)
        existing = {r["code"] for r in conn.execute("SELECT code FROM commodities").fetchall()}
        inserted = 0
        updated = 0
        for r in rows:
            if r["code"] in existing:
                updated += 1
            else:
                inserted += 1
            conn.execute(
                """
                INSERT INTO commodities (code, name, unit, benchmark_ticker, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    unit = excluded.unit,
                    benchmark_ticker = excluded.benchmark_ticker,
                    description = excluded.description
                """,
                (r["code"], r["name"], r["unit"], r["benchmark_ticker"], r["description"]),
            )
        conn.commit()
        return {"inserted": inserted, "updated": updated, "total": len(rows)}
    finally:
        if own_conn:
            conn.close()


def commodity_count() -> int:
    init_db()
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM commodities").fetchone()[0]
    finally:
        conn.close()


# ── stock_commodity_exposure CSV ─────────────────────────────────


VALID_ROLES: frozenset[str] = frozenset({"input", "output", "hedge"})


def parse_exposure_csv(path: Path | str = DEFAULT_EXPOSURE_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"exposure seed CSV not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        clean = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(clean)
    out = []
    for raw in reader:
        sym = (raw.get("symbol") or "").strip().upper()
        code = (raw.get("commodity_code") or "").strip().lower()
        role = (raw.get("role") or "").strip().lower()
        if not sym or not code:
            continue
        if role not in VALID_ROLES:
            print(f"[exposure_seed] skip row with invalid role={role!r} for {sym}")
            continue
        try:
            polarity = float(raw.get("polarity") or 0)
            elasticity = float(raw.get("elasticity") or 0)
        except ValueError:
            continue
        out.append({
            "symbol": sym,
            "commodity_code": code,
            "role": role,
            "polarity": max(-1.0, min(1.0, polarity)),
            "elasticity": max(0.0, min(1.0, elasticity)),
            "evidence": _coerce(raw.get("evidence")),
            "notes": _coerce(raw.get("notes")),
        })
    return out


def load_exposures(
    path: Path | str = DEFAULT_EXPOSURE_PATH,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Replace seed-loaded exposures with the contents of the CSV."""
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        cur = conn.execute(
            f"DELETE FROM stock_commodity_exposure WHERE source='{SEED_SOURCE_HAND}'"
        )
        deleted = cur.rowcount

        rows = parse_exposure_csv(path)
        universe = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        }
        commodity_codes = {
            r["code"]
            for r in conn.execute("SELECT code FROM commodities").fetchall()
        }

        inserted = 0
        skipped_orphan = 0

        for r in rows:
            if r["symbol"] not in universe:
                skipped_orphan += 1
                continue
            if r["commodity_code"] not in commodity_codes:
                skipped_orphan += 1
                continue
            evidence = r["evidence"] or r["notes"]
            try:
                conn.execute(
                    """
                    INSERT INTO stock_commodity_exposure
                        (symbol, commodity_code, role, polarity, elasticity,
                         confidence, evidence, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, commodity_code, role) DO UPDATE SET
                        polarity = excluded.polarity,
                        elasticity = excluded.elasticity,
                        confidence = excluded.confidence,
                        evidence = excluded.evidence,
                        source = excluded.source
                    """,
                    (
                        r["symbol"],
                        r["commodity_code"],
                        r["role"],
                        r["polarity"],
                        r["elasticity"],
                        SEED_CONFIDENCE_HIGH,
                        evidence,
                        SEED_SOURCE_HAND,
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


def exposure_counts() -> dict[str, int]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, COUNT(*) FROM stock_commodity_exposure GROUP BY role"
        ).fetchall()
        out = {row[0] or "(null)": row[1] for row in rows}
        out["total"] = sum(out.values())
        return out
    finally:
        conn.close()


def load_all() -> dict[str, dict]:
    """Convenience: load both commodities and exposures."""
    a = load_commodities()
    b = load_exposures()
    return {"commodities": a, "exposures": b}
