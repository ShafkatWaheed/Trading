"""Industries seed — yfinance industry codes mapped to GICS sectors.

Covers ~140 industries across 11 sectors. Used to pre-populate the
`industries` table so that `keyword_impact` rows can reference industries
that don't yet have any stocks loaded (e.g. niche industries that live
entirely in Tier C/D).

When yfinance returns a new industry code we haven't catalogued, the
`industry_loader.py` (week 1 day 4) auto-inserts it with the sector taken
from yfinance — this seed is the canonical baseline, not a complete list.

Pure data, no I/O.
"""

from __future__ import annotations

# (yfinance industry name, GICS-style sector)
INDUSTRIES: list[tuple[str, str]] = [
    # ── Technology (≈25) ───────────────────────────────────────────
    ("Communication Equipment",                     "Technology"),
    ("Computer Hardware",                           "Technology"),
    ("Consumer Electronics",                        "Technology"),
    ("Electronic Components",                       "Technology"),
    ("Electronic Gaming & Multimedia",              "Technology"),
    ("Electronics & Computer Distribution",         "Technology"),
    ("Information Technology Services",             "Technology"),
    ("Scientific & Technical Instruments",          "Technology"),
    ("Semiconductor Equipment & Materials",         "Technology"),
    ("Semiconductors",                              "Technology"),
    ("Software—Application",                        "Technology"),
    ("Software—Infrastructure",                     "Technology"),
    ("Solar",                                       "Technology"),

    # ── Communication Services (≈8) ────────────────────────────────
    ("Advertising Agencies",                        "Communication Services"),
    ("Broadcasting",                                "Communication Services"),
    ("Entertainment",                               "Communication Services"),
    ("Internet Content & Information",              "Communication Services"),
    ("Publishing",                                  "Communication Services"),
    ("Telecom Services",                            "Communication Services"),

    # ── Consumer Cyclical (≈22) ────────────────────────────────────
    ("Apparel Manufacturing",                       "Consumer Cyclical"),
    ("Apparel Retail",                              "Consumer Cyclical"),
    ("Auto & Truck Dealerships",                    "Consumer Cyclical"),
    ("Auto Manufacturers",                          "Consumer Cyclical"),
    ("Auto Parts",                                  "Consumer Cyclical"),
    ("Department Stores",                           "Consumer Cyclical"),
    ("Footwear & Accessories",                      "Consumer Cyclical"),
    ("Furnishings, Fixtures & Appliances",          "Consumer Cyclical"),
    ("Gambling",                                    "Consumer Cyclical"),
    ("Home Improvement Retail",                     "Consumer Cyclical"),
    ("Internet Retail",                             "Consumer Cyclical"),
    ("Leisure",                                     "Consumer Cyclical"),
    ("Lodging",                                     "Consumer Cyclical"),
    ("Luxury Goods",                                "Consumer Cyclical"),
    ("Packaging & Containers",                      "Consumer Cyclical"),
    ("Personal Services",                           "Consumer Cyclical"),
    ("Recreational Vehicles",                       "Consumer Cyclical"),
    ("Resorts & Casinos",                           "Consumer Cyclical"),
    ("Restaurants",                                 "Consumer Cyclical"),
    ("Specialty Retail",                            "Consumer Cyclical"),
    ("Textile Manufacturing",                       "Consumer Cyclical"),
    ("Travel Services",                             "Consumer Cyclical"),

    # ── Consumer Defensive (≈10) ───────────────────────────────────
    ("Beverages—Brewers",                           "Consumer Defensive"),
    ("Beverages—Non-Alcoholic",                     "Consumer Defensive"),
    ("Beverages—Wineries & Distilleries",           "Consumer Defensive"),
    ("Confectioners",                               "Consumer Defensive"),
    ("Discount Stores",                             "Consumer Defensive"),
    ("Education & Training Services",               "Consumer Defensive"),
    ("Farm Products",                               "Consumer Defensive"),
    ("Food Distribution",                           "Consumer Defensive"),
    ("Grocery Stores",                              "Consumer Defensive"),
    ("Household & Personal Products",               "Consumer Defensive"),
    ("Packaged Foods",                              "Consumer Defensive"),
    ("Tobacco",                                     "Consumer Defensive"),

    # ── Healthcare (≈12) ───────────────────────────────────────────
    ("Biotechnology",                               "Healthcare"),
    ("Diagnostics & Research",                      "Healthcare"),
    ("Drug Manufacturers—General",                  "Healthcare"),
    ("Drug Manufacturers—Specialty & Generic",      "Healthcare"),
    ("Health Information Services",                 "Healthcare"),
    ("Healthcare Plans",                            "Healthcare"),
    ("Medical Care Facilities",                     "Healthcare"),
    ("Medical Devices",                             "Healthcare"),
    ("Medical Distribution",                        "Healthcare"),
    ("Medical Instruments & Supplies",              "Healthcare"),
    ("Pharmaceutical Retailers",                    "Healthcare"),

    # ── Financial Services (≈18) ───────────────────────────────────
    ("Asset Management",                            "Financial Services"),
    ("Banks—Diversified",                           "Financial Services"),
    ("Banks—Regional",                              "Financial Services"),
    ("Capital Markets",                             "Financial Services"),
    ("Credit Services",                             "Financial Services"),
    ("Financial Conglomerates",                     "Financial Services"),
    ("Financial Data & Stock Exchanges",            "Financial Services"),
    ("Insurance Brokers",                           "Financial Services"),
    ("Insurance—Diversified",                       "Financial Services"),
    ("Insurance—Life",                              "Financial Services"),
    ("Insurance—Property & Casualty",               "Financial Services"),
    ("Insurance—Reinsurance",                       "Financial Services"),
    ("Insurance—Specialty",                         "Financial Services"),
    ("Mortgage Finance",                            "Financial Services"),
    ("Shell Companies",                             "Financial Services"),

    # ── Energy (≈8) ────────────────────────────────────────────────
    ("Oil & Gas Drilling",                          "Energy"),
    ("Oil & Gas E&P",                               "Energy"),
    ("Oil & Gas Equipment & Services",              "Energy"),
    ("Oil & Gas Integrated",                        "Energy"),
    ("Oil & Gas Midstream",                         "Energy"),
    ("Oil & Gas Refining & Marketing",              "Energy"),
    ("Thermal Coal",                                "Energy"),
    ("Uranium",                                     "Energy"),

    # ── Industrials (≈20) ──────────────────────────────────────────
    ("Aerospace & Defense",                         "Industrials"),
    ("Airlines",                                    "Industrials"),
    ("Airports & Air Services",                     "Industrials"),
    ("Building Products & Equipment",               "Industrials"),
    ("Business Equipment & Supplies",               "Industrials"),
    ("Conglomerates",                               "Industrials"),
    ("Consulting Services",                         "Industrials"),
    ("Electrical Equipment & Parts",                "Industrials"),
    ("Engineering & Construction",                  "Industrials"),
    ("Farm & Heavy Construction Machinery",         "Industrials"),
    ("Industrial Distribution",                     "Industrials"),
    ("Infrastructure Operations",                   "Industrials"),
    ("Integrated Freight & Logistics",              "Industrials"),
    ("Marine Shipping",                             "Industrials"),
    ("Metal Fabrication",                           "Industrials"),
    ("Pollution & Treatment Controls",              "Industrials"),
    ("Railroads",                                   "Industrials"),
    ("Rental & Leasing Services",                   "Industrials"),
    ("Security & Protection Services",              "Industrials"),
    ("Specialty Business Services",                 "Industrials"),
    ("Specialty Industrial Machinery",              "Industrials"),
    ("Staffing & Employment Services",              "Industrials"),
    ("Tools & Accessories",                         "Industrials"),
    ("Trucking",                                    "Industrials"),
    ("Waste Management",                            "Industrials"),

    # ── Basic Materials (≈12) ──────────────────────────────────────
    ("Agricultural Inputs",                         "Basic Materials"),
    ("Aluminum",                                    "Basic Materials"),
    ("Building Materials",                          "Basic Materials"),
    ("Chemicals",                                   "Basic Materials"),
    ("Coking Coal",                                 "Basic Materials"),
    ("Copper",                                      "Basic Materials"),
    ("Gold",                                        "Basic Materials"),
    ("Lumber & Wood Production",                    "Basic Materials"),
    ("Other Industrial Metals & Mining",            "Basic Materials"),
    ("Other Precious Metals & Mining",              "Basic Materials"),
    ("Paper & Paper Products",                      "Basic Materials"),
    ("Silver",                                      "Basic Materials"),
    ("Specialty Chemicals",                         "Basic Materials"),
    ("Steel",                                       "Basic Materials"),

    # ── Real Estate (≈11) ──────────────────────────────────────────
    ("REIT—Diversified",                            "Real Estate"),
    ("REIT—Healthcare Facilities",                  "Real Estate"),
    ("REIT—Hotel & Motel",                          "Real Estate"),
    ("REIT—Industrial",                             "Real Estate"),
    ("REIT—Mortgage",                               "Real Estate"),
    ("REIT—Office",                                 "Real Estate"),
    ("REIT—Residential",                            "Real Estate"),
    ("REIT—Retail",                                 "Real Estate"),
    ("REIT—Specialty",                              "Real Estate"),
    ("Real Estate Services",                        "Real Estate"),
    ("Real Estate—Development",                     "Real Estate"),
    ("Real Estate—Diversified",                     "Real Estate"),

    # ── Utilities (≈7) ─────────────────────────────────────────────
    ("Utilities—Diversified",                       "Utilities"),
    ("Utilities—Independent Power",                 "Utilities"),
    ("Utilities—Independent Power Producers",       "Utilities"),
    ("Utilities—Regulated Electric",                "Utilities"),
    ("Utilities—Regulated Gas",                     "Utilities"),
    ("Utilities—Regulated Water",                   "Utilities"),
    ("Utilities—Renewable",                         "Utilities"),
]


def industries_count() -> int:
    return len(INDUSTRIES)


def industries_by_sector() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for industry, sector in INDUSTRIES:
        out.setdefault(sector, []).append(industry)
    return out


def load_industries(conn=None) -> dict[str, int]:
    """Upsert every industry into the `industries` table.

    Idempotent. Returns {"inserted": N, "updated": M}.
    """
    from src.utils.db import get_connection, init_db

    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        existing = {r["code"] for r in conn.execute(
            "SELECT code FROM industries"
        ).fetchall()}
        inserted = 0
        updated = 0
        for code, sector in INDUSTRIES:
            if code in existing:
                updated += 1
            else:
                inserted += 1
            conn.execute(
                """
                INSERT INTO industries (code, sector)
                VALUES (?, ?)
                ON CONFLICT(code) DO UPDATE SET sector = excluded.sector
                """,
                (code, sector),
            )
        conn.commit()
        return {"inserted": inserted, "updated": updated}
    finally:
        if own_conn:
            conn.close()
