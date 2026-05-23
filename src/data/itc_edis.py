"""ITC EDIS fetcher (Wave 2, Phase F — Litigation card).

Free API: https://edis.usitc.gov/data/investigation  (no key required, returns XML)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.

EDIS is the U.S. International Trade Commission's Electronic Document
Information System. Section 337 investigations cover unfair-import
practices (most often patent infringement) and can result in exclusion
orders banning imports of the accused products — a material risk for a
respondent. Being a complainant is offensive/protective and typically
benign.

Note: the /data/investigation listing endpoint does NOT include party
names directly — determining complainant vs respondent would require
fetching each investigation's documents. For Wave 2 we use a
case-insensitive substring match on the investigation title and emit
party_role="unknown".
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from src.utils.db import log_api_call


_EDIS_URL = "https://edis.usitc.gov/data/investigation"


def fetch_337_investigations_for_party(party_name: str) -> list[dict]:
    """Query EDIS for §337 investigations whose title mentions `party_name`.

    Returns a list of normalized investigation dicts:
        {investigation_number, title, party_name, party_role,
         status, filing_date}

    `party_role` is always 'unknown' for this listing endpoint (the
    EDIS /data/investigation feed does not include party rows; only a
    document fetch would). `filing_date` is "" for the same reason.

    Empty list on no-results, parse failure, or network error
    (failures are logged via log_api_call, never silently swallowed).
    """
    url = _EDIS_URL

    if not party_name:
        return []

    try:
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as exc:
        log_api_call("itc_edis", url, "error", error=str(exc))
        return []

    needle = party_name.strip().lower()
    out: list[dict] = []

    for inv in root.iter("investigation"):
        inv_type = (inv.findtext("investigationType") or "").strip()
        inv_number = (inv.findtext("investigationNumber") or "").strip()
        title = (inv.findtext("investigationTitle") or "").strip()
        status = (inv.findtext("investigationStatus") or "").strip()

        # Filter: must be Section 337 (by type or by number prefix)
        is_337 = (
            inv_type.lower() == "section 337"
            or inv_number.upper().startswith("337-TA-")
        )
        if not is_337:
            continue

        # Filter: title must contain the party name (case-insensitive)
        if needle not in title.lower():
            continue

        out.append({
            "investigation_number": inv_number,
            "title": title,
            "party_name": party_name,
            "party_role": "unknown",
            "status": status,
            "filing_date": "",
        })

    log_api_call("itc_edis", url, "ok")
    return out
