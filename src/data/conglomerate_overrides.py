"""Multi-tag overrides for conglomerates whose single-industry tag is misleading.

yfinance returns ONE industry per stock. For most stocks that's fine. For a
handful of true conglomerates, a single tag obscures material business-line
exposure that the news engine needs to capture:

  AMZN  — Internet Retail tag hides AWS cloud (~30% of revenue, growing share)
  GOOGL — Internet Content tag hides Google Cloud (~10% but growing fast)
  MSFT  — Software—Infrastructure tag hides M365, LinkedIn, gaming diversity
  AAPL  — Consumer Electronics tag hides Services (~25% of revenue)
  BRK-B — Insurance tag hides railroads, energy, retail, consumer brands
  TSLA  — Auto tag hides Solar + Software/AI
  ...

For these stocks the loader REPLACES the single yfinance tag with multiple
weighted tags (`weight` sums to 1.0). The stock_industry rows from
`source='yfinance'` are deleted before the override rows are written.

Used by `apply_conglomerate_overrides()` once after the yfinance industry
load completes (week 1 day 4 → day 5).

Pure data, no I/O.
"""

from __future__ import annotations

import sqlite3

from src.utils.db import get_connection, init_db


# (symbol, [(industry_code, weight), ...]) — weights must sum to 1.0
# When adding a new entry, also confirm each industry_code exists in
# industries_seed.py or will be auto-created from yfinance.
CONGLOMERATE_TAGS: list[tuple[str, list[tuple[str, float]]]] = [
    ("AMZN", [
        ("Internet Retail",                     0.55),    # core e-commerce
        ("Software—Infrastructure",             0.30),    # AWS
        ("Internet Content & Information",      0.15),    # advertising + Prime media
    ]),
    ("GOOGL", [
        ("Internet Content & Information",      0.75),    # Search + Ads + YouTube
        ("Software—Infrastructure",             0.20),    # Google Cloud
        ("Consumer Electronics",                0.05),    # Pixel + Nest
    ]),
    ("GOOG", [
        ("Internet Content & Information",      0.75),
        ("Software—Infrastructure",             0.20),
        ("Consumer Electronics",                0.05),
    ]),
    ("MSFT", [
        ("Software—Infrastructure",             0.55),    # Azure + Windows Server + AI infra
        ("Software—Application",                0.35),    # M365 + Dynamics + GitHub
        ("Internet Content & Information",      0.10),    # LinkedIn + Bing/MSN
    ]),
    ("AAPL", [
        ("Consumer Electronics",                0.75),    # iPhone + Mac + iPad + wearables
        ("Software—Application",                0.25),    # Services (App Store, iCloud, Music, TV+)
    ]),
    ("META", [
        ("Internet Content & Information",      0.95),    # Family of Apps (ads)
        ("Consumer Electronics",                0.05),    # Reality Labs (Quest)
    ]),
    ("BRK-B", [
        ("Insurance—Diversified",               0.40),    # GEICO + General Re + reinsurance
        ("Conglomerates",                       0.30),    # BNSF, BHE, Marmon, See's, etc.
        ("Banks—Diversified",                   0.10),    # equity portfolio bank exposure
        ("Specialty Industrial Machinery",      0.10),    # PCC + IMC tools
        ("Specialty Retail",                    0.10),    # nebraska furniture, jewelry
    ]),
    ("TSLA", [
        ("Auto Manufacturers",                  0.85),    # vehicles
        ("Solar",                               0.08),    # SolarCity / energy
        ("Software—Application",                0.07),    # FSD / Dojo
    ]),
    ("F", [
        ("Auto Manufacturers",                  0.85),
        ("Credit Services",                     0.15),    # Ford Credit captive
    ]),
    ("GM", [
        ("Auto Manufacturers",                  0.85),
        ("Credit Services",                     0.10),    # GM Financial
        ("Software—Application",                0.05),    # Cruise / OnStar
    ]),
    ("DIS", [
        ("Entertainment",                       0.65),    # Studios + Streaming + Networks
        ("Resorts & Casinos",                   0.35),    # Parks & Experiences
    ]),
    ("CVS", [
        ("Healthcare Plans",                    0.45),    # Aetna
        ("Pharmaceutical Retailers",            0.35),    # retail pharmacy + clinic
        ("Medical Distribution",                0.20),    # Caremark PBM
    ]),
    ("PEP", [
        ("Beverages—Non-Alcoholic",             0.55),    # Pepsi/Mtn Dew/Gatorade
        ("Packaged Foods",                      0.45),    # Frito-Lay + Quaker
    ]),
    ("WMT", [
        ("Discount Stores",                     0.85),    # brick & mortar
        ("Internet Retail",                     0.15),    # Walmart.com / Sam's online
    ]),
    ("JNJ", [
        ("Drug Manufacturers—General",          0.55),    # Innovative Medicine
        ("Medical Devices",                     0.45),    # MedTech (post-Kenvue spin)
    ]),
    ("GE", [
        ("Aerospace & Defense",                 0.70),    # GE Aerospace (post-Vernova spin)
        ("Specialty Industrial Machinery",      0.30),    # remaining industrial
    ]),
    ("ORCL", [
        ("Software—Infrastructure",             0.70),    # OCI + database
        ("Software—Application",                0.30),    # Cerner + ERP apps
    ]),
    ("IBM", [
        ("Information Technology Services",     0.50),    # Consulting (Kyndryl-adjacent)
        ("Software—Infrastructure",             0.40),    # Red Hat + watsonx
        ("Software—Application",                0.10),    # remaining apps
    ]),
    ("T", [
        ("Telecom Services",                    1.00),    # already pure-play post-WBD; explicit for completeness
    ]),
]


def apply_conglomerate_overrides(conn: sqlite3.Connection | None = None) -> dict[str, int]:
    """Replace yfinance single-tags with hand-curated multi-tag mappings.

    For each conglomerate in CONGLOMERATE_TAGS:
      1. Delete any existing stock_industry rows where source='yfinance'.
      2. Insert one row per (industry, weight) with source='hand_conglomerate'.

    Idempotent: re-running clears prior 'hand_conglomerate' rows for the same
    symbol before re-inserting, so weight changes propagate cleanly.

    Returns counts: {"symbols": N, "rows_written": M}.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    n_symbols = 0
    n_rows = 0

    try:
        for symbol, tags in CONGLOMERATE_TAGS:
            # weight sanity
            total = sum(w for _, w in tags)
            if abs(total - 1.0) > 0.01:
                raise ValueError(
                    f"conglomerate {symbol} weights sum to {total:.3f}, expected 1.0"
                )

            # Wipe ALL existing rows for the conglomerate (any source) so the
            # multi-tag mapping is canonical. Re-running with new weights then
            # propagates cleanly.
            conn.execute("DELETE FROM stock_industry WHERE symbol=?", (symbol,))

            # Pick the highest-weight industry as the primary.
            primary_industry = max(tags, key=lambda t: t[1])[0]
            for industry, weight in tags:
                # Make sure the industry exists.
                conn.execute(
                    "INSERT OR IGNORE INTO industries (code, sector) VALUES (?, ?)",
                    (industry, "Unknown"),
                )
                conn.execute(
                    """
                    INSERT INTO stock_industry
                        (symbol, industry_code, weight, is_primary, source)
                    VALUES (?, ?, ?, ?, 'hand_conglomerate')
                    """,
                    (symbol, industry, weight, 1 if industry == primary_industry else 0),
                )
                n_rows += 1
            n_symbols += 1

        conn.commit()
        return {"symbols": n_symbols, "rows_written": n_rows}
    finally:
        if own_conn:
            conn.close()
