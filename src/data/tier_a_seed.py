"""Hand-curated Tier A universe — ~150 mega/large-cap stocks with deep liquidity.

Tier A is the layer where every theme tag, supply-chain edge, and peer
relationship is hand-verified. These are the names where:
  - Deep sell-side analyst coverage (3+ analysts)
  - Detailed 10-K supplier/customer disclosures
  - Daily news flow
  - Average daily dollar volume > $500M
  - Market cap > $50B (most names; some growth/cyclical exceptions)
  - S&P 500 membership (with a few NDX-100 / TSX 60 additions)

Pure data, no I/O. Imported by:
  - src/data/universe_loader.py to backfill stocks_universe with tier='A'
  - tests/test_universe_schema.py to verify the seed integrity

When adding a new Tier A stock, also propagate to:
  - seeds/tier_a_peers.csv (~7 peer edges)
  - seeds/keyword_impact.csv if it has a unique theme exposure
  - any relevant theme→industry edge for its industry
"""

from __future__ import annotations

# (symbol, name, sector, primary_industry, exchange, country)
TIER_A: list[tuple[str, str, str, str, str, str]] = [
    # ── Mega-cap Tech (Mag 7 + adjacent) ────────────────────────────
    ("AAPL",   "Apple Inc",                   "Technology",             "Consumer Electronics",          "NASDAQ", "US"),
    ("MSFT",   "Microsoft Corp",              "Technology",             "Software—Infrastructure",       "NASDAQ", "US"),
    ("GOOGL",  "Alphabet Inc Class A",        "Communication Services", "Internet Content & Information","NASDAQ", "US"),
    ("GOOG",   "Alphabet Inc Class C",        "Communication Services", "Internet Content & Information","NASDAQ", "US"),
    ("AMZN",   "Amazon.com Inc",              "Consumer Cyclical",      "Internet Retail",               "NASDAQ", "US"),
    ("NVDA",   "NVIDIA Corp",                 "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("META",   "Meta Platforms Inc",          "Communication Services", "Internet Content & Information","NASDAQ", "US"),
    ("TSLA",   "Tesla Inc",                   "Consumer Cyclical",      "Auto Manufacturers",            "NASDAQ", "US"),

    # ── AI/Semis ────────────────────────────────────────────────────
    ("AVGO",   "Broadcom Inc",                "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("AMD",    "Advanced Micro Devices",      "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("QCOM",   "QUALCOMM Inc",                "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("TXN",    "Texas Instruments",           "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("MU",     "Micron Technology",           "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("ARM",    "Arm Holdings plc ADR",        "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("INTC",   "Intel Corp",                  "Technology",             "Semiconductors",                "NASDAQ", "US"),
    ("TSM",    "Taiwan Semiconductor ADR",    "Technology",             "Semiconductors",                "NYSE",   "US"),
    ("ASML",   "ASML Holding NV ADR",         "Technology",             "Semiconductor Equipment",       "NASDAQ", "US"),
    ("AMAT",   "Applied Materials",           "Technology",             "Semiconductor Equipment",       "NASDAQ", "US"),
    ("LRCX",   "Lam Research",                "Technology",             "Semiconductor Equipment",       "NASDAQ", "US"),
    ("KLAC",   "KLA Corp",                    "Technology",             "Semiconductor Equipment",       "NASDAQ", "US"),

    # ── Software / SaaS / Cloud ─────────────────────────────────────
    ("ORCL",   "Oracle Corp",                 "Technology",             "Software—Infrastructure",       "NYSE",   "US"),
    ("CRM",    "Salesforce Inc",              "Technology",             "Software—Application",          "NYSE",   "US"),
    ("ADBE",   "Adobe Inc",                   "Technology",             "Software—Infrastructure",       "NASDAQ", "US"),
    ("NOW",    "ServiceNow Inc",              "Technology",             "Software—Application",          "NYSE",   "US"),
    ("INTU",   "Intuit Inc",                  "Technology",             "Software—Application",          "NASDAQ", "US"),
    ("IBM",    "International Business Machines","Technology",          "Information Technology Services","NYSE",  "US"),
    ("ACN",    "Accenture plc",               "Technology",             "Information Technology Services","NYSE",  "US"),
    ("PANW",   "Palo Alto Networks",          "Technology",             "Software—Infrastructure",       "NASDAQ", "US"),
    ("CRWD",   "CrowdStrike Holdings",        "Technology",             "Software—Infrastructure",       "NASDAQ", "US"),
    ("SNOW",   "Snowflake Inc",               "Technology",             "Software—Application",          "NYSE",   "US"),
    ("CSCO",   "Cisco Systems",               "Technology",             "Communication Equipment",       "NASDAQ", "US"),

    # ── Communication / Media ───────────────────────────────────────
    ("NFLX",   "Netflix Inc",                 "Communication Services", "Entertainment",                 "NASDAQ", "US"),
    ("DIS",    "Walt Disney Co",              "Communication Services", "Entertainment",                 "NYSE",   "US"),
    ("CMCSA",  "Comcast Corp",                "Communication Services", "Telecom Services",              "NASDAQ", "US"),
    ("T",      "AT&T Inc",                    "Communication Services", "Telecom Services",              "NYSE",   "US"),
    ("VZ",     "Verizon Communications",      "Communication Services", "Telecom Services",              "NYSE",   "US"),
    ("TMUS",   "T-Mobile US",                 "Communication Services", "Telecom Services",              "NASDAQ", "US"),

    # ── Mega-bank Financials ────────────────────────────────────────
    ("JPM",    "JPMorgan Chase",              "Financial Services",     "Banks—Diversified",             "NYSE",   "US"),
    ("BAC",    "Bank of America",             "Financial Services",     "Banks—Diversified",             "NYSE",   "US"),
    ("WFC",    "Wells Fargo",                 "Financial Services",     "Banks—Diversified",             "NYSE",   "US"),
    ("C",      "Citigroup Inc",               "Financial Services",     "Banks—Diversified",             "NYSE",   "US"),
    ("GS",     "Goldman Sachs",               "Financial Services",     "Capital Markets",               "NYSE",   "US"),
    ("MS",     "Morgan Stanley",              "Financial Services",     "Capital Markets",               "NYSE",   "US"),

    # ── Payments / Fintech / Asset Mgmt ─────────────────────────────
    ("V",      "Visa Inc",                    "Financial Services",     "Credit Services",               "NYSE",   "US"),
    ("MA",     "Mastercard Inc",              "Financial Services",     "Credit Services",               "NYSE",   "US"),
    ("AXP",    "American Express",            "Financial Services",     "Credit Services",               "NYSE",   "US"),
    ("PYPL",   "PayPal Holdings",             "Financial Services",     "Credit Services",               "NASDAQ", "US"),
    ("BLK",    "BlackRock Inc",               "Financial Services",     "Asset Management",              "NYSE",   "US"),
    ("SCHW",   "Charles Schwab",              "Financial Services",     "Capital Markets",               "NYSE",   "US"),
    ("BX",     "Blackstone Inc",              "Financial Services",     "Asset Management",              "NYSE",   "US"),
    ("KKR",    "KKR & Co Inc",                "Financial Services",     "Asset Management",              "NYSE",   "US"),
    ("ICE",    "Intercontinental Exchange",   "Financial Services",     "Financial Data & Stock Exchanges","NYSE", "US"),
    ("CME",    "CME Group",                   "Financial Services",     "Financial Data & Stock Exchanges","NASDAQ","US"),
    ("SPGI",   "S&P Global",                  "Financial Services",     "Financial Data & Stock Exchanges","NYSE", "US"),

    # ── Insurance ───────────────────────────────────────────────────
    ("BRK-B",  "Berkshire Hathaway B",        "Financial Services",     "Insurance—Diversified",         "NYSE",   "US"),
    ("PGR",    "Progressive Corp",            "Financial Services",     "Insurance—Property & Casualty", "NYSE",   "US"),
    ("AIG",    "American International Group","Financial Services",     "Insurance—Diversified",         "NYSE",   "US"),
    ("MET",    "MetLife Inc",                 "Financial Services",     "Insurance—Life",                "NYSE",   "US"),
    ("TRV",    "Travelers Companies",         "Financial Services",     "Insurance—Property & Casualty", "NYSE",   "US"),

    # ── Pharma mega ─────────────────────────────────────────────────
    ("LLY",    "Eli Lilly",                   "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),
    ("JNJ",    "Johnson & Johnson",           "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),
    ("MRK",    "Merck & Co",                  "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),
    ("PFE",    "Pfizer Inc",                  "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),
    ("ABBV",   "AbbVie Inc",                  "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),
    ("BMY",    "Bristol-Myers Squibb",        "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),
    ("AMGN",   "Amgen Inc",                   "Healthcare",             "Drug Manufacturers—General",    "NASDAQ", "US"),
    ("GILD",   "Gilead Sciences",             "Healthcare",             "Drug Manufacturers—General",    "NASDAQ", "US"),
    ("NVO",    "Novo Nordisk ADR",            "Healthcare",             "Drug Manufacturers—General",    "NYSE",   "US"),

    # ── Healthcare insurance / services ─────────────────────────────
    ("UNH",    "UnitedHealth Group",          "Healthcare",             "Healthcare Plans",              "NYSE",   "US"),
    ("ELV",    "Elevance Health",             "Healthcare",             "Healthcare Plans",              "NYSE",   "US"),
    ("CI",     "Cigna Group",                 "Healthcare",             "Healthcare Plans",              "NYSE",   "US"),
    ("HUM",    "Humana Inc",                  "Healthcare",             "Healthcare Plans",              "NYSE",   "US"),
    ("CVS",    "CVS Health",                  "Healthcare",             "Healthcare Plans",              "NYSE",   "US"),

    # ── Medical devices / biotech ───────────────────────────────────
    ("ISRG",   "Intuitive Surgical",          "Healthcare",             "Medical Devices",               "NASDAQ", "US"),
    ("MDT",    "Medtronic plc",               "Healthcare",             "Medical Devices",               "NYSE",   "US"),
    ("ABT",    "Abbott Laboratories",         "Healthcare",             "Medical Devices",               "NYSE",   "US"),
    ("SYK",    "Stryker Corp",                "Healthcare",             "Medical Devices",               "NYSE",   "US"),
    ("BSX",    "Boston Scientific",           "Healthcare",             "Medical Devices",               "NYSE",   "US"),
    ("BDX",    "Becton, Dickinson",           "Healthcare",             "Medical Devices",               "NYSE",   "US"),
    ("EW",     "Edwards Lifesciences",        "Healthcare",             "Medical Devices",               "NYSE",   "US"),
    ("REGN",   "Regeneron Pharmaceuticals",   "Healthcare",             "Biotechnology",                 "NASDAQ", "US"),
    ("VRTX",   "Vertex Pharmaceuticals",      "Healthcare",             "Biotechnology",                 "NASDAQ", "US"),

    # ── Consumer Staples mega ───────────────────────────────────────
    ("WMT",    "Walmart Inc",                 "Consumer Defensive",     "Discount Stores",               "NYSE",   "US"),
    ("COST",   "Costco Wholesale",            "Consumer Defensive",     "Discount Stores",               "NASDAQ", "US"),
    ("PG",     "Procter & Gamble",            "Consumer Defensive",     "Household & Personal Products", "NYSE",   "US"),
    ("KO",     "Coca-Cola Co",                "Consumer Defensive",     "Beverages—Non-Alcoholic",       "NYSE",   "US"),
    ("PEP",    "PepsiCo Inc",                 "Consumer Defensive",     "Beverages—Non-Alcoholic",       "NASDAQ", "US"),
    ("MDLZ",   "Mondelez International",      "Consumer Defensive",     "Confectioners",                 "NASDAQ", "US"),
    ("MO",     "Altria Group",                "Consumer Defensive",     "Tobacco",                       "NYSE",   "US"),
    ("PM",     "Philip Morris International", "Consumer Defensive",     "Tobacco",                       "NYSE",   "US"),
    ("CL",     "Colgate-Palmolive",           "Consumer Defensive",     "Household & Personal Products", "NYSE",   "US"),

    # ── Consumer Discretionary mega ─────────────────────────────────
    ("HD",     "Home Depot",                  "Consumer Cyclical",      "Home Improvement Retail",       "NYSE",   "US"),
    ("LOW",    "Lowe's Companies",            "Consumer Cyclical",      "Home Improvement Retail",       "NYSE",   "US"),
    ("MCD",    "McDonald's Corp",             "Consumer Cyclical",      "Restaurants",                   "NYSE",   "US"),
    ("SBUX",   "Starbucks Corp",              "Consumer Cyclical",      "Restaurants",                   "NASDAQ", "US"),
    ("NKE",    "Nike Inc",                    "Consumer Cyclical",      "Footwear & Accessories",        "NYSE",   "US"),
    ("TJX",    "TJX Companies",               "Consumer Cyclical",      "Apparel Retail",                "NYSE",   "US"),
    ("BKNG",   "Booking Holdings",            "Consumer Cyclical",      "Travel Services",               "NASDAQ", "US"),
    ("MAR",    "Marriott International",      "Consumer Cyclical",      "Lodging",                       "NASDAQ", "US"),
    ("ABNB",   "Airbnb Inc",                  "Consumer Cyclical",      "Travel Services",               "NASDAQ", "US"),

    # ── Auto ────────────────────────────────────────────────────────
    ("GM",     "General Motors",              "Consumer Cyclical",      "Auto Manufacturers",            "NYSE",   "US"),
    ("F",      "Ford Motor",                  "Consumer Cyclical",      "Auto Manufacturers",            "NYSE",   "US"),

    # ── Energy mega ─────────────────────────────────────────────────
    ("XOM",    "Exxon Mobil",                 "Energy",                 "Oil & Gas Integrated",          "NYSE",   "US"),
    ("CVX",    "Chevron Corp",                "Energy",                 "Oil & Gas Integrated",          "NYSE",   "US"),
    ("COP",    "ConocoPhillips",              "Energy",                 "Oil & Gas E&P",                 "NYSE",   "US"),
    ("OXY",    "Occidental Petroleum",        "Energy",                 "Oil & Gas E&P",                 "NYSE",   "US"),
    ("EOG",    "EOG Resources",               "Energy",                 "Oil & Gas E&P",                 "NYSE",   "US"),
    ("VLO",    "Valero Energy",               "Energy",                 "Oil & Gas Refining & Marketing","NYSE",   "US"),
    ("MPC",    "Marathon Petroleum",          "Energy",                 "Oil & Gas Refining & Marketing","NYSE",   "US"),
    ("PSX",    "Phillips 66",                 "Energy",                 "Oil & Gas Refining & Marketing","NYSE",   "US"),
    ("KMI",    "Kinder Morgan",               "Energy",                 "Oil & Gas Midstream",           "NYSE",   "US"),
    ("ENB",    "Enbridge Inc",                "Energy",                 "Oil & Gas Midstream",           "NYSE",   "US"),
    ("SLB",    "Schlumberger Ltd",            "Energy",                 "Oil & Gas Equipment & Services","NYSE",   "US"),
    ("HAL",    "Halliburton Co",              "Energy",                 "Oil & Gas Equipment & Services","NYSE",   "US"),

    # ── Industrials / Aerospace / Defense ───────────────────────────
    ("BA",     "Boeing Co",                   "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("LMT",    "Lockheed Martin",             "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("RTX",    "RTX Corp",                    "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("NOC",    "Northrop Grumman",            "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("GD",     "General Dynamics",            "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("HII",    "Huntington Ingalls",          "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("HON",    "Honeywell International",     "Industrials",            "Conglomerates",                 "NASDAQ", "US"),
    ("GE",     "GE Aerospace",                "Industrials",            "Aerospace & Defense",           "NYSE",   "US"),
    ("GEV",    "GE Vernova Inc",              "Industrials",            "Specialty Industrial Machinery","NYSE",   "US"),
    ("ETN",    "Eaton Corp plc",              "Industrials",            "Specialty Industrial Machinery","NYSE",   "US"),
    ("EMR",    "Emerson Electric",            "Industrials",            "Specialty Industrial Machinery","NYSE",   "US"),
    ("ITW",    "Illinois Tool Works",         "Industrials",            "Specialty Industrial Machinery","NYSE",   "US"),
    ("MMM",    "3M Company",                  "Industrials",            "Conglomerates",                 "NYSE",   "US"),
    ("CAT",    "Caterpillar Inc",             "Industrials",            "Farm & Heavy Construction Machinery","NYSE","US"),
    ("DE",     "Deere & Co",                  "Industrials",            "Farm & Heavy Construction Machinery","NYSE","US"),

    # ── Logistics / Transport ───────────────────────────────────────
    ("UPS",    "United Parcel Service",       "Industrials",            "Integrated Freight & Logistics","NYSE",   "US"),
    ("FDX",    "FedEx Corp",                  "Industrials",            "Integrated Freight & Logistics","NYSE",   "US"),
    ("UNP",    "Union Pacific",               "Industrials",            "Railroads",                     "NYSE",   "US"),
    ("NSC",    "Norfolk Southern",            "Industrials",            "Railroads",                     "NYSE",   "US"),
    ("CSX",    "CSX Corp",                    "Industrials",            "Railroads",                     "NASDAQ", "US"),
    ("ODFL",   "Old Dominion Freight Line",   "Industrials",            "Trucking",                      "NASDAQ", "US"),

    # ── Materials ───────────────────────────────────────────────────
    ("LIN",    "Linde plc",                   "Basic Materials",        "Specialty Chemicals",           "NASDAQ", "US"),
    ("SHW",    "Sherwin-Williams",            "Basic Materials",        "Specialty Chemicals",           "NYSE",   "US"),
    ("ECL",    "Ecolab Inc",                  "Basic Materials",        "Specialty Chemicals",           "NYSE",   "US"),
    ("FCX",    "Freeport-McMoRan",            "Basic Materials",        "Copper",                        "NYSE",   "US"),
    ("NEM",    "Newmont Corp",                "Basic Materials",        "Gold",                          "NYSE",   "US"),
    ("NUE",    "Nucor Corp",                  "Basic Materials",        "Steel",                         "NYSE",   "US"),

    # ── Utilities ───────────────────────────────────────────────────
    ("NEE",    "NextEra Energy",              "Utilities",              "Utilities—Regulated Electric",  "NYSE",   "US"),
    ("DUK",    "Duke Energy",                 "Utilities",              "Utilities—Regulated Electric",  "NYSE",   "US"),
    ("SO",     "Southern Company",            "Utilities",              "Utilities—Regulated Electric",  "NYSE",   "US"),
    ("AEP",    "American Electric Power",     "Utilities",              "Utilities—Regulated Electric",  "NASDAQ", "US"),
    ("XEL",    "Xcel Energy",                 "Utilities",              "Utilities—Regulated Electric",  "NASDAQ", "US"),
    ("EXC",    "Exelon Corp",                 "Utilities",              "Utilities—Regulated Electric",  "NASDAQ", "US"),
    ("CEG",    "Constellation Energy",        "Utilities",              "Utilities—Renewable",           "NASDAQ", "US"),
    ("VST",    "Vistra Corp",                 "Utilities",              "Utilities—Independent Power",   "NYSE",   "US"),
    ("AES",    "AES Corp",                    "Utilities",              "Utilities—Independent Power",   "NYSE",   "US"),

    # ── Real Estate (REITs) ─────────────────────────────────────────
    ("PLD",    "Prologis Inc",                "Real Estate",            "REIT—Industrial",               "NYSE",   "US"),
    ("AMT",    "American Tower",              "Real Estate",            "REIT—Specialty",                "NYSE",   "US"),
    ("CCI",    "Crown Castle",                "Real Estate",            "REIT—Specialty",                "NYSE",   "US"),
    ("EQIX",   "Equinix Inc",                 "Real Estate",            "REIT—Specialty",                "NASDAQ", "US"),
    ("DLR",    "Digital Realty Trust",        "Real Estate",            "REIT—Specialty",                "NYSE",   "US"),
    ("PSA",    "Public Storage",              "Real Estate",            "REIT—Industrial",               "NYSE",   "US"),
    ("SPG",    "Simon Property Group",        "Real Estate",            "REIT—Retail",                   "NYSE",   "US"),
    ("O",      "Realty Income",               "Real Estate",            "REIT—Retail",                   "NYSE",   "US"),

    # ── Crypto / Fintech (large-cap by liquidity) ───────────────────
    ("COIN",   "Coinbase Global",             "Financial Services",     "Capital Markets",               "NASDAQ", "US"),

    # ── Uranium / Nuclear infrastructure (Tier A by AI-power thesis) ──
    ("CCJ",    "Cameco Corp",                 "Energy",                 "Uranium",                       "NYSE",   "US"),
]


def tier_a_symbols() -> list[str]:
    """Return the Tier A ticker list."""
    return [row[0] for row in TIER_A]


def tier_a_count() -> int:
    return len(TIER_A)
