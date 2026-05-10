"""Loader for `seeds/keyword_impact.csv` → `keyword_impact` table.

Reads the hand-curated keyword → industry/stock impact CSV and upserts each row.
Idempotent — re-running replaces all rows tagged with the seed source so
edits to the CSV propagate cleanly without leaving stale rows behind.

The CSV is the operational source of truth for the news engine. It's edited
manually (or via UI in a future phase). This loader is the only thing that
should write rows with `notes` containing 'seed:hand'.

CSV format: keyword,industry_code,target_stock,polarity,weight,domain,notes
  - keyword       (required)  the lowercase phrase to match in news
  - industry_code (optional)  yfinance industry name
  - target_stock  (optional)  symbol when keyword names a specific company
  - polarity      (-1..1)     +1 fully bullish, -1 fully bearish
  - weight        (0..1)      keyword strength when it fires
  - domain        (required)  ai|oil|war|tariff|rates|fda|court|glp1|crypto|climate|mining|demo|strike
  - notes         (optional)  free text comment
Lines starting with `#` are skipped.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.utils.db import get_connection, init_db

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seeds" / "keyword_impact.csv"
)

# Marker we write into `notes` so future re-imports can clear ONLY the seed-loaded
# rows without touching anything written by other code paths.
SEED_NOTES_PREFIX = "seed:hand"


def _normalise_keyword(s: str) -> str:
    return s.strip().lower()


def _coerce(value: str | None) -> str | None:
    """Empty / whitespace-only fields become NULL."""
    if value is None:
        return None
    v = value.strip()
    return v or None


def parse_seed_csv(path: Path | str = DEFAULT_SEED_PATH) -> list[dict]:
    """Parse the seed CSV. Skips comment lines (#) and blank rows."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"keyword seed CSV not found: {p}")

    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        # Strip comment lines BEFORE handing to DictReader so the header is the
        # first non-comment line.
        clean_lines = [
            line for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]
    reader = csv.DictReader(clean_lines)
    for raw in reader:
        keyword = _normalise_keyword(raw.get("keyword") or "")
        if not keyword:
            continue
        industry = _coerce(raw.get("industry_code"))
        target = _coerce(raw.get("target_stock"))
        if industry is None and target is None:
            # CHECK constraint will reject this; skip with a warning rather than
            # blowing up the whole import.
            print(f"[keyword_seed] skip orphan row (no industry or target): {keyword}")
            continue
        try:
            polarity = float(raw.get("polarity") or 0)
            weight = float(raw.get("weight") or 0)
        except ValueError:
            print(f"[keyword_seed] skip row with bad numeric on keyword={keyword}")
            continue
        rows.append({
            "keyword": keyword,
            "industry_code": industry,
            "target_stock": target,
            "polarity": polarity,
            "weight": weight,
            "domain": _coerce(raw.get("domain")),
            "notes": _coerce(raw.get("notes")),
        })
    return rows


def load_keyword_impact(
    path: Path | str = DEFAULT_SEED_PATH,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Replace all seed-loaded rows with the contents of the CSV.

    Strategy: delete rows matching `notes LIKE 'seed:hand%'` first, then insert.
    This keeps any rows added by other code paths (LLM extraction, backtest
    validation, manual UI edits) untouched.

    Returns counts: {"deleted": N, "inserted": M, "skipped": K}.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        # Wipe prior seed rows
        cur = conn.execute(
            f"DELETE FROM keyword_impact WHERE notes LIKE '{SEED_NOTES_PREFIX}%'"
        )
        deleted = cur.rowcount

        rows = parse_seed_csv(path)
        skipped = 0
        inserted = 0

        for r in rows:
            # Tag every row's `notes` with the seed prefix + original notes appended
            tagged_notes = SEED_NOTES_PREFIX
            if r["notes"]:
                tagged_notes = f"{SEED_NOTES_PREFIX} | {r['notes']}"
            try:
                conn.execute(
                    """
                    INSERT INTO keyword_impact
                        (keyword, industry_code, target_stock, polarity, weight, domain, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["keyword"],
                        r["industry_code"],
                        r["target_stock"],
                        r["polarity"],
                        r["weight"],
                        r["domain"],
                        tagged_notes,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError as exc:
                print(f"[keyword_seed] integrity error on {r['keyword']}: {exc}")
                skipped += 1

        conn.commit()
        return {"deleted": deleted, "inserted": inserted, "skipped": skipped}
    finally:
        if own_conn:
            conn.close()


def keyword_impact_counts() -> dict[str, int]:
    """Diagnostic: rows per domain."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT domain, COUNT(*) FROM keyword_impact GROUP BY domain"
        ).fetchall()
        out = {row[0] or "(null)": row[1] for row in rows}
        out["total"] = sum(out.values())
        return out
    finally:
        conn.close()
