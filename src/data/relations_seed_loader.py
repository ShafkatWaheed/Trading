"""Loader for `seeds/stock_relations.csv` → `stock_relations` table.

Hand-curated supply-chain spine. ~30-50 high-confidence edges across
NVDA-TSM-ASML chip chain, oil services chain, pharma-PBM, hyperscaler-DC-utility,
defense, EV substitution, etc. Idempotent — re-running deletes seed-tagged
edges first so CSV deletions propagate.

Convention recap (mirrors the CSV header comment):
    (NVDA, TSM, "supplier")  ⇒ NVDA's supplier is TSM
    (TSM, NVDA, "customer")  ⇒ TSM's customer is NVDA
The seed contains both directions where both are knowable; the loader does
NOT auto-mirror because a (supplier ↔ customer) inversion is meaningful and
shouldn't be implicit.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.utils.db import get_connection, init_db

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "seeds" / "stock_relations.csv"
)

VALID_RELATION_TYPES: frozenset[str] = frozenset({
    # Phase 4 core types
    "supplier", "customer", "substitute", "complement",
    # Phase 6 extension — mechanism-typed relations.
    # The first three are mostly synonyms for the existing types but carry
    # different polarity/semantics in the causal-chain traversal:
    "input_dependency",        # ≈ supplier, but explicit about feedstock cost-pass-through
    "output_substitute",       # ≈ substitute on the output side (zero-sum revenue)
    "complementary_demand",    # ≈ complement, but with explicit demand correlation
    # The other three are genuinely new:
    "cost_passthrough",        # B's price rise → A's cost rise (e.g. airlines ← jet fuel)
    "regulatory_substitute",   # regulating A → demand shifts to B (e.g. coal → gas)
    "geographic_co_exposure",  # A and B share country-level exposure (China revenue, etc.)
})

# Tag we write to `evidence` so we can wipe just the seed-loaded rows.
SEED_EVIDENCE_PREFIX = "seed:hand"


def _coerce(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None


def parse_relations_csv(path: Path | str = DEFAULT_SEED_PATH) -> list[dict]:
    """Parse the spine CSV. Skips comment lines and blank rows."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"relations seed CSV not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        clean = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(clean)

    rows: list[dict] = []
    for raw in reader:
        from_sym = (raw.get("from_symbol") or "").strip().upper()
        to_sym = (raw.get("to_symbol") or "").strip().upper()
        rel = (raw.get("relation_type") or "").strip().lower()
        if not from_sym or not to_sym or from_sym == to_sym:
            continue
        if rel not in VALID_RELATION_TYPES:
            print(f"[relations_seed] skip row with invalid relation_type={rel!r}")
            continue
        try:
            strength = float(raw.get("strength") or 0)
            polarity = float(raw.get("polarity") or 1.0)
        except ValueError:
            continue
        rows.append({
            "from_symbol": from_sym,
            "to_symbol": to_sym,
            "relation_type": rel,
            "strength": max(0.0, min(1.0, strength)),
            "polarity": max(-1.0, min(1.0, polarity)),
            "evidence": _coerce(raw.get("evidence")),
            "notes": _coerce(raw.get("notes")),
        })
    return rows


def load_spine(
    path: Path | str = DEFAULT_SEED_PATH,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Replace seed-loaded rows with the contents of the CSV.

    Idempotent. Skips edges whose `from_symbol` or `to_symbol` is not in
    `stocks_universe` (counted as orphan).
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        # Wipe prior seed rows
        cur = conn.execute(
            f"DELETE FROM stock_relations WHERE evidence LIKE '{SEED_EVIDENCE_PREFIX}%'"
        )
        deleted = cur.rowcount

        rows = parse_relations_csv(path)
        universe = {
            r["symbol"] for r in conn.execute(
                "SELECT symbol FROM stocks_universe"
            ).fetchall()
        }

        inserted = 0
        skipped_orphan = 0
        for r in rows:
            if r["from_symbol"] not in universe or r["to_symbol"] not in universe:
                skipped_orphan += 1
                continue

            evidence_tag = SEED_EVIDENCE_PREFIX
            if r["evidence"]:
                evidence_tag = f"{SEED_EVIDENCE_PREFIX} | {r['evidence']}"
            elif r["notes"]:
                evidence_tag = f"{SEED_EVIDENCE_PREFIX} | {r['notes']}"

            try:
                conn.execute(
                    """
                    INSERT INTO stock_relations
                        (from_symbol, to_symbol, relation_type, strength, polarity, evidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(from_symbol, to_symbol, relation_type) DO UPDATE SET
                        strength = excluded.strength,
                        polarity = excluded.polarity,
                        evidence = excluded.evidence
                    """,
                    (
                        r["from_symbol"],
                        r["to_symbol"],
                        r["relation_type"],
                        r["strength"],
                        r["polarity"],
                        evidence_tag,
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


def relation_counts() -> dict[str, int]:
    """Diagnostic: rows per relation_type."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT relation_type, COUNT(*) FROM stock_relations GROUP BY relation_type"
        ).fetchall()
        out = {row[0] or "(null)": row[1] for row in rows}
        out["total"] = sum(out.values())
        return out
    finally:
        conn.close()
