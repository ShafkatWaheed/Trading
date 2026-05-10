"""Static stock-universe metadata used by the scheduler (pre-fetch list) and
the Discover service (display name + sector).

Previously this dict lived in dashboard.py; both consumers reached into it via
AST parsing to avoid importing Streamlit. Now that dashboard.py is gone, the
canonical home is here. Pure data, no I/O — safe to import from anywhere.
"""

from __future__ import annotations

# (ticker -> (display name, sector, keyword tags for search))
STOCK_DB: dict[str, tuple[str, str, str]] = {
    # Mega cap tech
    "AAPL": ("Apple Inc", "Technology", "iphone mac consumer electronics"),
    "MSFT": ("Microsoft Corp", "Technology", "cloud azure ai software enterprise"),
    "GOOG": ("Alphabet Inc", "Technology", "google search ads ai cloud youtube"),
    "AMZN": ("Amazon.com Inc", "Consumer Discretionary", "ecommerce cloud aws retail"),
    "NVDA": ("NVIDIA Corp", "Technology", "gpu ai chips semiconductors gaming data center"),
    "META": ("Meta Platforms", "Technology", "facebook instagram social media metaverse ads"),
    "TSLA": ("Tesla Inc", "Consumer Discretionary", "ev electric vehicle auto energy battery"),
    "BRK-B": ("Berkshire Hathaway", "Financials", "buffett insurance conglomerate value"),
    # Finance
    "JPM": ("JPMorgan Chase", "Financials", "bank investment banking finance"),
    "V": ("Visa Inc", "Financials", "payments credit card fintech"),
    "MA": ("Mastercard Inc", "Financials", "payments credit card fintech"),
    "BAC": ("Bank of America", "Financials", "bank consumer finance"),
    "GS": ("Goldman Sachs", "Financials", "investment bank wall street trading"),
    "MS": ("Morgan Stanley", "Financials", "investment bank wealth management"),
    # Healthcare / Pharma
    "JNJ": ("Johnson & Johnson", "Healthcare", "pharma medical devices consumer health"),
    "UNH": ("UnitedHealth Group", "Healthcare", "health insurance managed care"),
    "PFE": ("Pfizer Inc", "Healthcare", "pharma drugs vaccine biotech"),
    "ABBV": ("AbbVie Inc", "Healthcare", "pharma biotech immunology"),
    "MRK": ("Merck & Co", "Healthcare", "pharma oncology vaccine"),
    "LLY": ("Eli Lilly", "Healthcare", "pharma glp-1 ozempic weight loss diabetes"),
    "NVO": ("Novo Nordisk", "Healthcare", "pharma glp-1 wegovy obesity diabetes"),
    "ISRG": ("Intuitive Surgical", "Healthcare", "robotics surgical robots medical devices"),
    # Consumer
    "WMT": ("Walmart Inc", "Consumer Staples", "retail grocery discount"),
    "PG": ("Procter & Gamble", "Consumer Staples", "consumer goods household"),
    "KO": ("Coca-Cola Co", "Consumer Staples", "beverages drinks"),
    "PEP": ("PepsiCo Inc", "Consumer Staples", "beverages snacks frito lay"),
    "COST": ("Costco Wholesale", "Consumer Staples", "retail warehouse membership"),
    "MCD": ("McDonald's Corp", "Consumer Discretionary", "fast food restaurant"),
    "SBUX": ("Starbucks Corp", "Consumer Discretionary", "coffee restaurant"),
    "NKE": ("Nike Inc", "Consumer Discretionary", "shoes apparel sports"),
    "HD": ("Home Depot", "Consumer Discretionary", "home improvement retail construction"),
    "DIS": ("Walt Disney Co", "Communication Services", "entertainment streaming theme parks"),
    # Tech / Software
    "CRM": ("Salesforce Inc", "Technology", "crm cloud saas enterprise software"),
    "ORCL": ("Oracle Corp", "Technology", "database cloud enterprise software"),
    "ADBE": ("Adobe Inc", "Technology", "creative cloud design software saas"),
    "NFLX": ("Netflix Inc", "Communication Services", "streaming entertainment content"),
    "AMD": ("Advanced Micro Devices", "Technology", "semiconductors cpu gpu chips ai"),
    "INTC": ("Intel Corp", "Technology", "semiconductors cpu chips manufacturing"),
    "CSCO": ("Cisco Systems", "Technology", "networking infrastructure enterprise"),
    "QCOM": ("Qualcomm Inc", "Technology", "semiconductors mobile 5g wireless chips"),
    "AVGO": ("Broadcom Inc", "Technology", "semiconductors networking infrastructure"),
    # Energy
    "XOM": ("Exxon Mobil", "Energy", "oil gas petroleum refining"),
    "CVX": ("Chevron Corp", "Energy", "oil gas petroleum energy"),
    "OXY": ("Occidental Petroleum", "Energy", "oil gas carbon capture"),
    # Telecom
    "T": ("AT&T Inc", "Communication Services", "telecom wireless 5g"),
    "VZ": ("Verizon Communications", "Communication Services", "telecom wireless 5g"),
    # Industrial / Aerospace
    "BA": ("Boeing Co", "Industrials", "aerospace defense aircraft"),
    "LMT": ("Lockheed Martin", "Industrials", "defense aerospace military"),
    "RTX": ("RTX Corp", "Industrials", "defense aerospace missiles"),
    "CAT": ("Caterpillar Inc", "Industrials", "construction mining heavy equipment"),
    # Fintech / Growth
    "PYPL": ("PayPal Holdings", "Financials", "payments fintech digital wallet"),
    "SQ": ("Block Inc", "Financials", "payments fintech square cash app bitcoin"),
    "SHOP": ("Shopify Inc", "Technology", "ecommerce platform saas"),
    "COIN": ("Coinbase Global", "Financials", "crypto exchange bitcoin ethereum"),
    "SOFI": ("SoFi Technologies", "Financials", "fintech banking lending neobank"),
    # Mobility / Travel
    "UBER": ("Uber Technologies", "Industrials", "rideshare delivery transportation"),
    "ABNB": ("Airbnb Inc", "Consumer Discretionary", "travel vacation rental lodging"),
    "SNAP": ("Snap Inc", "Communication Services", "social media messaging ar"),
    # EV / Clean energy
    "RIVN": ("Rivian Automotive", "Consumer Discretionary", "ev electric vehicle truck"),
    "LCID": ("Lucid Group", "Consumer Discretionary", "ev electric vehicle luxury"),
    "ENPH": ("Enphase Energy", "Technology", "solar energy inverters clean"),
    # AI / Data
    "PLTR": ("Palantir Technologies", "Technology", "ai data analytics government defense"),
    "SNOW": ("Snowflake Inc", "Technology", "cloud data warehouse analytics"),
    "DDOG": ("Datadog Inc", "Technology", "cloud monitoring observability devops"),
    # Quantum / Nuclear
    "IONQ": ("IonQ Inc", "Technology", "quantum computing"),
    "RGTI": ("Rigetti Computing", "Technology", "quantum computing"),
    "SMR": ("NuScale Power", "Utilities", "nuclear smr energy"),
    "OKLO": ("Oklo Inc", "Utilities", "nuclear fission energy"),
    "CCJ": ("Cameco Corp", "Energy", "uranium nuclear mining"),
}


def stock_meta() -> dict[str, dict[str, str]]:
    """Compact (name, sector) lookup — the shape Discover wants."""
    return {sym: {"name": name, "sector": sector} for sym, (name, sector, _kw) in STOCK_DB.items()}
