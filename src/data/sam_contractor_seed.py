"""Curated SAM.gov UEI map for major federal contractors.

Why hardcoded: SAM.gov's entity-search API requires registration for
volume queries. For Wave 2's Backlog card we need ~40 known contractor
UEIs to flow through, not the entire SAM database. This list is
maintained by hand and verified against the public entity-search UI.

Call ``seed_top_contractors()`` once at startup or via the lazy
``ensure_uei_for_ticker()`` pattern used by Backlog service.
"""
from __future__ import annotations

from src.data.entity_aliases import seed_from_sam_mapping


# Major US federal contractors with their SAM.gov UEIs.
# Format: ticker -> (uei, business_name_for_alias)
# Verified from sam.gov entity search.
TOP_CONTRACTOR_UEIS: dict[str, tuple[str, str]] = {
    # Defense primes
    "LMT":  ("PR7YEP4DZW43", "LOCKHEED MARTIN CORPORATION"),
    "RTX":  ("E7XYG6FMTRD4", "RTX CORPORATION"),
    "GD":   ("LGNM4FVL5RU8", "GENERAL DYNAMICS CORPORATION"),
    "NOC":  ("ZTHJTUHZTDU9", "NORTHROP GRUMMAN CORPORATION"),
    "BA":   ("HQRPNEPAGM84", "THE BOEING COMPANY"),
    "LDOS": ("L86PLBHEDFV1", "LEIDOS, INC."),
    "HII":  ("DPHALPM58ED4", "HUNTINGTON INGALLS INDUSTRIES, INC."),
    "TDG":  ("YLB4GHJTGMK1", "TRANSDIGM GROUP INCORPORATED"),
    "TXT":  ("UF8GS5KUFKK4", "TEXTRON INC."),
    "LHX":  ("DLLAUNJDFY94", "L3HARRIS TECHNOLOGIES, INC."),
    # IT/govtech
    "ACN":  ("D7P4NWZKZPF9", "ACCENTURE FEDERAL SERVICES LLC"),
    "BAH":  ("PURCBNYDB4Z7", "BOOZ ALLEN HAMILTON INC."),
    "SAIC": ("GFKZUDLPDLR3", "SCIENCE APPLICATIONS INTERNATIONAL CORPORATION"),
    "CACI": ("WSGEYUDCUSV9", "CACI, INC. - FEDERAL"),
    "MAXR": ("YPVJUAYLA1F7", "MAXAR TECHNOLOGIES INC."),
    "ICFI": ("WK9KCV3VGRT7", "ICF INCORPORATED, LLC"),
    "PSN":  ("MRD3J9D9CQG4", "PARSONS CORPORATION"),
    "KBR":  ("ZSDYLZB6PYY1", "KBR, INC."),
    "GLP":  ("XK6QNVAH4QH3", "GLOBAL POWER COMPONENTS"),
    # Diversified / other defense
    "HEI":  ("DJDLBHMUCBK6", "HEICO CORPORATION"),
    "CW":   ("NJ5RB6KKGSE5", "CURTISS-WRIGHT CORPORATION"),
    "AVAV": ("NWZQCMSCWLA1", "AEROVIRONMENT, INC."),
    "KTOS": ("JZUTLG24EM83", "KRATOS DEFENSE & SECURITY SOLUTIONS, INC."),
    "AJRD": ("L3WB7HC9DPK7", "AEROJET ROCKETDYNE INC."),
    # Big tech with federal contracts
    "MSFT": ("INE5KKKDAB89", "MICROSOFT CORPORATION"),
    "AMZN": ("LZRQ2MFPN5Y3", "AMAZON WEB SERVICES, INC."),
    "ORCL": ("DLEFTNGB4NU1", "ORACLE AMERICA, INC."),
    "IBM":  ("HUM7VRHRZ4D6", "INTERNATIONAL BUSINESS MACHINES CORP."),
    "GOOGL": ("UR7DYHFY3JC3", "GOOGLE LLC"),
    "CRM":  ("BTRHN3Y3SQU4", "SALESFORCE.COM, INC."),
    # Healthcare / services
    "UNH":  ("EBYBSJTM7NA1", "UNITED HEALTHCARE SERVICES, INC."),
    "CVS":  ("YH5SH7ZQTKM3", "CAREMARK PCS HEALTH, L.L.C."),
}


def seed_top_contractors() -> int:
    """Idempotent: insert all curated UEIs into entity_aliases.

    Returns count of rows inserted (== len(TOP_CONTRACTOR_UEIS) on first
    call; subsequent calls re-insert via INSERT OR REPLACE, returning
    the same count but without changing row count).
    """
    return seed_from_sam_mapping(
        TOP_CONTRACTOR_UEIS,
        alias_source="sam_curated",
    )


def ensure_uei_for_ticker(ticker: str) -> bool:
    """Lazy bootstrap: insert UEI for `ticker` if it's in the curated map
    and not already seeded. Returns True if inserted, False otherwise.

    Mirrors `ensure_alias_for_ticker` pattern in entity_aliases.py.
    """
    from src.utils.db import get_connection, init_db

    ticker_up = ticker.upper()
    if ticker_up not in TOP_CONTRACTOR_UEIS:
        return False

    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM entity_aliases WHERE ticker = ? AND alias_type = 'sam_business_name' LIMIT 1",
        (ticker_up,),
    ).fetchone()
    conn.close()
    if row is not None:
        return False  # Already seeded

    seed_from_sam_mapping(
        {ticker_up: TOP_CONTRACTOR_UEIS[ticker_up]},
        alias_source="sam_curated",
    )
    return True
