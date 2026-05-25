"""ITC EDIS fetcher (Wave 2, Phase F — Litigation card).

Free API: https://edis.usitc.gov/data/document  (no key required, returns XML)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.

EDIS is the U.S. International Trade Commission's Electronic Document
Information System. Section 337 investigations cover unfair-import
practices (most often patent infringement) and can result in exclusion
orders banning imports of the accused products — a material risk for a
respondent. Being a complainant is offensive/protective and typically
benign.

Background
----------
The naive /data/investigation listing endpoint silently returns only
~20 generic tariff records and ignores `investigationType=Sec 337`
unless other filters are also supplied — it cannot be used to surface
§337 activity by ticker.

Instead, this module pulls the /data/document feed with
`investigationType=Sec 337&investigationStatus=Active`. That feed
exposes the `<onBehalfOf>` field which carries the party that filed
each document (the data we actually need). We aggregate all party
strings per investigation, then case-insensitively word-boundary-match
the requested party name against them. Document titles are scanned for
"Respondent"/"Complainant" keywords to infer party_role; otherwise the
role is "unknown".

The full document feed (Active §337 only) is ~10K rows and is fetched
in 500-row pages. The aggregated party→investigations index is cached
in SQLite for `_CACHE_TTL_MINUTES` so each per-ticker call is cheap.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_EDIS_DOCUMENT_URL = "https://edis.usitc.gov/data/document"
_CACHE_KEY = "itc_edis:active_337_index_v2"
_CACHE_TTL_MINUTES = 6 * 60  # 6h, matches source_freshness_registry cadence
_PAGE_SIZE = 500
_MAX_PAGES = 25  # EDIS WAF caps deep pagination ~page 21; 25 is a safe upper bound
_REQUEST_TIMEOUT = 30.0
_INTER_PAGE_SLEEP = 0.3
_RETRY_BACKOFF = (1.0, 2.0, 4.0)


def _fetch_page(url: str) -> str | None:
    """GET one page with light retry/backoff. Returns XML body or None on failure."""
    for delay in _RETRY_BACKOFF:
        try:
            resp = httpx.get(url, timeout=_REQUEST_TIMEOUT)
        except Exception as exc:  # network error
            log_api_call("itc_edis", url, "error", error=str(exc))
            time.sleep(delay)
            continue
        # EDIS sometimes returns 200 OK with an HTML WAF maintenance page.
        body = resp.text or ""
        if resp.status_code == 200 and (body.startswith("<?xml") or body.startswith("<results")):
            return body
        log_api_call(
            "itc_edis", url, "error",
            error=f"http={resp.status_code} non_xml_body=true",
        )
        time.sleep(delay)
    return None


def _build_active_337_index() -> dict:
    """Page through the active §337 document feed and aggregate by investigation.

    Returns a dict of:
        {
            "<inv_no>": {
                "title": "...",
                "status": "Active",
                "parties": ["Apple Inc.", ...],         # unique onBehalfOf strings
                "roles": {"Apple Inc.": "respondent"},  # inferred per party string
                "first_doc_date": "YYYY-MM-DD",
            },
            ...
        }
    """
    index: dict[str, dict] = {}
    for page in range(1, _MAX_PAGES + 1):
        url = (
            f"{_EDIS_DOCUMENT_URL}?investigationType=Sec%20337"
            f"&investigationStatus=Active&pageSize={_PAGE_SIZE}&pageNumber={page}"
        )
        body = _fetch_page(url)
        if body is None:
            # Could not fetch this page — stop and use what we have.
            break
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            log_api_call("itc_edis", url, "error", error=f"parse: {exc}")
            break

        docs = list(root.iter("document"))
        if not docs:
            break

        for d in docs:
            inv_num = (d.findtext("investigationNumber") or "").strip()
            inv_type = (d.findtext("investigationType") or "").strip()
            # EDIS occasionally returns Import-Injury (701-/731-) rows through
            # this filter; restrict to true §337 records.
            if not inv_num.startswith("337-") and inv_type.lower() != "sec 337":
                continue
            inv_title = (d.findtext("investigationTitle") or "").strip()
            inv_status = (d.findtext("investigationStatus") or "").strip()
            obo = (d.findtext("onBehalfOf") or "").strip()
            doc_title = (d.findtext("documentTitle") or "").strip()
            doc_date = (d.findtext("documentDate") or "").strip()[:10].replace("/", "-")

            entry = index.setdefault(inv_num, {
                "title": inv_title,
                "status": inv_status,
                "parties_role_votes": {},  # party_str -> {"respondent": n, "complainant": n}
                "first_doc_date": doc_date,
            })
            # Keep the earliest date we've seen so far.
            if doc_date and (not entry["first_doc_date"] or doc_date < entry["first_doc_date"]):
                entry["first_doc_date"] = doc_date

            if not obo:
                continue
            votes = entry["parties_role_votes"].setdefault(obo, {"respondent": 0, "complainant": 0})
            doc_title_lo = doc_title.lower()
            if "respondent" in doc_title_lo:
                votes["respondent"] += 1
            if "complainant" in doc_title_lo:
                votes["complainant"] += 1

        if len(docs) < _PAGE_SIZE:
            # Last page.
            break
        time.sleep(_INTER_PAGE_SLEEP)

    # Collapse role votes per party.
    out: dict[str, dict] = {}
    for inv_num, entry in index.items():
        parties = list(entry["parties_role_votes"].keys())
        roles: dict[str, str] = {}
        for party_str, v in entry["parties_role_votes"].items():
            if v["respondent"] > v["complainant"]:
                roles[party_str] = "respondent"
            elif v["complainant"] > v["respondent"]:
                roles[party_str] = "complainant"
            else:
                roles[party_str] = "unknown"
        out[inv_num] = {
            "title": entry["title"],
            "status": entry["status"],
            "parties": parties,
            "roles": roles,
            "first_doc_date": entry["first_doc_date"],
        }

    log_api_call(
        "itc_edis", _EDIS_DOCUMENT_URL, "ok",
        error=f"index_size={len(out)}",
    )
    return out


def _get_index() -> dict:
    """Return the active §337 index, fetching + caching if missing/expired."""
    cached = cache_get(_CACHE_KEY)
    if cached:
        return cached
    fresh = _build_active_337_index()
    if fresh:
        # Only cache non-empty results — an empty index here means the WAF
        # blocked us on page 1, and we want the next call to retry.
        cache_set(_CACHE_KEY, fresh, ttl_minutes=_CACHE_TTL_MINUTES)
    return fresh


def fetch_337_investigations_for_party(party_name: str) -> list[dict]:
    """Return active §337 investigations whose party list matches `party_name`.

    Returns a list of normalized investigation dicts:
        {investigation_number, title, party_name, party_role,
         status, filing_date}

    `party_role` is "respondent" / "complainant" / "unknown" inferred from
    the EDIS document titles attributed to the party. `filing_date` is the
    earliest documentDate observed for the investigation (proxy for the
    institution date — EDIS does not expose the institution date directly).

    Matching is case-insensitive and word-boundary-anchored so e.g.
    "Intel" does not match "CCC Intelligent Solutions".

    Empty list on no-results, parse failure, or network error (failures
    are logged via log_api_call, never silently swallowed).
    """
    if not party_name or not party_name.strip():
        return []

    needle = party_name.strip()
    # Word-boundary, case-insensitive regex over each onBehalfOf string.
    pattern = re.compile(r"\b" + re.escape(needle) + r"\b", re.IGNORECASE)

    index = _get_index()
    if not index:
        return []

    out: list[dict] = []
    for inv_num, entry in index.items():
        matching_role = None
        for party_str in entry.get("parties", []):
            if pattern.search(party_str):
                role = entry.get("roles", {}).get(party_str, "unknown")
                # Prefer a definitive role over "unknown" if multiple party
                # strings match (e.g. "Apple Inc." vs "Apple Inc. and X").
                if matching_role is None or matching_role == "unknown":
                    matching_role = role
                if matching_role != "unknown":
                    break
        if matching_role is None:
            continue
        out.append({
            "investigation_number": inv_num,
            "title": entry.get("title", ""),
            "party_name": party_name,
            "party_role": matching_role,
            "status": entry.get("status", ""),
            "filing_date": entry.get("first_doc_date", "") or "",
        })

    return out
