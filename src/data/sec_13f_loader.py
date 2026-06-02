"""SEC EDGAR 13F-HR loader — fetches institutional holdings (Phase 7A).

For each institution in the `institutions` table, fetches their most-recent
13F-HR filing from EDGAR, parses the holdings XML, maps each CUSIP to a
ticker symbol, and writes rows to `institution_holdings` with `source='13F'`.

Network-gated: tests mock both the EDGAR submissions API and the holdings
XML parsing. Live runs require:
    * Real CIKs (the prototype seed has placeholder CIKs for many)
    * SEC fair-access user-agent header
    * CUSIP → ticker mapping (we use yfinance.cusip lookups + symbology cache)

CLI:
    python -m src.data.sec_13f_loader --top 50
    python -m src.data.sec_13f_loader --cik 1364742 --force
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone

import httpx

from src.utils.db import get_connection, init_db


SEC_HEADERS = {
    "User-Agent": "Trading Prototype research@example.com",
    "Accept-Encoding": "gzip, deflate",
}


# ── XML parsing (string-based, no etree dependency) ──────────────


# XML may or may not use an `ns1:` (or `n1:` or other) namespace prefix on every
# element. Bridgewater + Baupost prefix everything; BlackRock + Vanguard don't.
# Use a non-capturing optional prefix group on each tag so both forms parse.
_NS = r"(?:[a-zA-Z][\w-]*:)?"   # e.g. "ns1:" or "" — non-capturing

_HOLDING_RE = re.compile(
    rf"<{_NS}infoTable>(.*?)</{_NS}infoTable>", re.DOTALL | re.IGNORECASE
)
_NAME_RE = re.compile(rf"<{_NS}nameOfIssuer>(.*?)</{_NS}nameOfIssuer>", re.IGNORECASE)
_CUSIP_RE = re.compile(rf"<{_NS}cusip>(.*?)</{_NS}cusip>", re.IGNORECASE)
_VALUE_RE = re.compile(rf"<{_NS}value>(.*?)</{_NS}value>", re.IGNORECASE)
_SHARES_RE = re.compile(rf"<{_NS}sshPrnamt>(.*?)</{_NS}sshPrnamt>", re.IGNORECASE)


def parse_13f_holdings_xml(xml: str, *, period_of_report: str | None = None) -> list[dict]:
    """Parse a 13F-HR information-table XML into a list of holdings.

    Each element of the returned list has keys: name, cusip, value_usd, shares.
    Robust to malformed entries — silently skips rows missing required fields.

    Note on units: SEC changed the <value> reporting unit from $thousands to
    actual dollars effective for filings due on/after 2023-01-03 (period >=
    Q4 2022). We use period_of_report to decide whether to apply the ×1000
    multiplier. Backfill of pre-2023 quarters needs this; modern filings do not.
    """
    multiplier = 1.0
    if period_of_report:
        # Anything reporting a quarter ending BEFORE 2022-12-31 used $thousands.
        # Q4 2022 (period 2022-12-31) was the first quarter filed in dollars.
        try:
            if period_of_report < "2022-12-31":
                multiplier = 1000.0
        except Exception:
            pass

    out: list[dict] = []
    for m in _HOLDING_RE.finditer(xml):
        block = m.group(1)
        name_m = _NAME_RE.search(block)
        cusip_m = _CUSIP_RE.search(block)
        value_m = _VALUE_RE.search(block)
        shares_m = _SHARES_RE.search(block)
        if not (name_m and cusip_m and value_m):
            continue
        try:
            value_usd = float(value_m.group(1).strip()) * multiplier
            shares = float(shares_m.group(1).strip()) if shares_m else None
        except (ValueError, AttributeError):
            continue
        out.append({
            "name": name_m.group(1).strip(),
            "cusip": cusip_m.group(1).strip(),
            "value_usd": value_usd,
            "shares": shares,
        })
    return out


# ── EDGAR fetch ──────────────────────────────────────────────────


def _list_13f_filings(cik: str) -> list[tuple[str, str]]:
    """Return [(accession_no_dashes, period_of_report), ...] for ALL 13F-HRs of a CIK,
    newest first. Used by both `fetch_latest_13f` and the historical backfill."""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        resp = httpx.get(url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    period_of_reports = recent.get("reportDate", [])
    out: list[tuple[str, str]] = []
    for i, form in enumerate(forms):
        if form == "13F-HR":
            acc = accessions[i].replace("-", "")
            period = period_of_reports[i] if i < len(period_of_reports) else ""
            out.append((acc, period))
    return out


def _fetch_holdings_for_accession(cik: str, accession: str) -> str | None:
    """Walk an accession's index.json + fetch the holdings XML.

    Returns the raw XML text or None on failure. Shared between the latest-only
    and historical backfill paths.
    """
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}"
    try:
        idx = httpx.get(f"{base}/index.json", headers=SEC_HEADERS, timeout=30)
        idx.raise_for_status()
        items = idx.json().get("directory", {}).get("item", []) or []
    except Exception:
        return None

    KNOWN_PATTERNS = ("informationtable", "infotable", "info_table", "13f")
    pattern_match = None
    fallback_match = None
    for it in items:
        name = (it.get("name") or "")
        name_lc = name.lower()
        if not name_lc.endswith(".xml") or name_lc == "primary_doc.xml":
            continue
        if pattern_match is None and any(p in name_lc for p in KNOWN_PATTERNS):
            pattern_match = name
        if fallback_match is None:
            fallback_match = name
    info_doc = pattern_match or fallback_match
    if not info_doc:
        return None

    try:
        resp = httpx.get(f"{base}/{info_doc}", headers=SEC_HEADERS, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def fetch_latest_13f(cik: str) -> tuple[str | None, str | None]:
    """Returns (info_table_xml, period_of_report) — both may be None on failure.

    Walks SEC EDGAR in two steps:
      1. Fetch the filer's submissions JSON to find the most recent 13F-HR
         accession + report date.
      2. Fetch the accession's index.json to locate the actual holdings file
         (usually `informationTable.xml`, sometimes prefixed with the filer's
         name). The submissions JSON only exposes the cover page in
         `primaryDocument` — the holdings live in a separate document.
    """
    filings = _list_13f_filings(cik)
    if not filings:
        return None, None
    acc, period = filings[0]
    xml = _fetch_holdings_for_accession(cik, acc)
    return xml, period


# ── CUSIP → ticker resolution (best-effort) ──────────────────────


_CORPORATE_SUFFIXES = (
    " INC", " INCORPORATED", " CORP", " CORPORATION", " CO", " COMPANY",
    " COMPANIES", " HOLDINGS", " HOLDING", " GROUP", " GRP", " ENTERPRISES",
    " LLC", " LP", " LTD", " LIMITED", " PLC", " NV", " AG", " SA",
    " THE", " CLASS A", " CLASS B", " CLASS C", " CL A", " CL B", " CL C",
    " COM", " COMMON", " ORD", " ORDINARY", " SHARES",
)


def _normalize_name(name: str) -> str:
    """Lowercase, strip corporate suffixes + punctuation. Used to compare
    a 13F-reported issuer name against stocks_universe.name."""
    n = (name or "").upper().strip()
    # Strip trailing corporate suffixes — iteratively (some names stack them
    # like "BROOKFIELD CORP THE NEW")
    for _ in range(4):
        before = n
        for suffix in _CORPORATE_SUFFIXES:
            if n.endswith(suffix):
                n = n[:-len(suffix)].rstrip(" ,.")
        if n == before:
            break
    # Drop punctuation that varies between sources
    for ch in ".,/()&'":
        n = n.replace(ch, " ")
    return " ".join(n.split())


def cusip_to_symbol(cusip: str, name: str | None = None) -> str | None:
    """Resolve a CUSIP to a ticker. The full mapping is non-trivial — for the
    prototype we use normalized-name matching against the loaded universe.
    Live use should plug in a richer CUSIP database (OpenFIGI, CRSP).

    Strategy (most-specific first):
      1. Exact match on the FULL normalized issuer name.
      2. Match on the first 3+ words of the normalized name (avoids the false
         positives the old first-word-only matcher hit).
      3. Match on the first 2 words.

    Returns None when no confident match — never invents a symbol.
    """
    if not name:
        return None
    init_db()
    conn = get_connection()
    try:
        normalized = _normalize_name(name)
        if not normalized:
            return None
        words = normalized.split()
        if not words:
            return None

        # 1. Exact normalized-name match (strongest signal)
        rows = conn.execute(
            """
            SELECT symbol, name FROM stocks_universe
            WHERE name IS NOT NULL AND name != ''
              AND UPPER(name) = ?
            LIMIT 1
            """,
            (normalized,),
        ).fetchall()
        if rows:
            return rows[0]["symbol"]

        # 2. Prefix match on the first 3+ words (e.g. "BROOKFIELD ASSET MANAGEMENT")
        if len(words) >= 3:
            prefix = " ".join(words[:3])
            rows = conn.execute(
                """
                SELECT symbol FROM stocks_universe
                WHERE name IS NOT NULL AND name != ''
                  AND UPPER(name) LIKE ?
                ORDER BY LENGTH(name)
                LIMIT 1
                """,
                (f"{prefix}%",),
            ).fetchall()
            if rows:
                return rows[0]["symbol"]

        # 3. Prefix match on the first 2 words
        if len(words) >= 2:
            prefix = " ".join(words[:2])
            rows = conn.execute(
                """
                SELECT symbol FROM stocks_universe
                WHERE name IS NOT NULL AND name != ''
                  AND UPPER(name) LIKE ?
                ORDER BY LENGTH(name)
                LIMIT 1
                """,
                (f"{prefix}%",),
            ).fetchall()
            if rows:
                return rows[0]["symbol"]

        # No confident match — return None rather than guessing
        return None
    finally:
        conn.close()


# ── per-institution processing ───────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_institution(
    cik: str,
    *,
    fetch_fn=None,
    parse_fn=None,
    resolve_fn=None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Process one institution end-to-end. Resolves CUSIPs and writes holdings.

    `fetch_fn(cik) -> (xml, period)`, `parse_fn(xml) -> list[dict]`,
    `resolve_fn(cusip, name) -> symbol` — all injection points for tests.
    Defaults call live SEC EDGAR + the inbuilt resolver.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    fetch_fn = fetch_fn or fetch_latest_13f
    parse_fn = parse_fn or parse_13f_holdings_xml
    resolve_fn = resolve_fn or cusip_to_symbol

    try:
        xml, period = fetch_fn(cik)
        if not xml:
            return {"cik": cik, "rows_written": 0, "error": "no_filing"}
        if not period:
            period = _now()[:10]   # fallback to today

        # Pass period_of_report so the parser can apply the correct $ multiplier
        # (×1000 pre-2023, ×1 post-2023 — SEC unit change effective 2023-01-03).
        try:
            holdings = parse_fn(xml, period_of_report=period)
        except TypeError:
            holdings = parse_fn(xml)
        if not holdings:
            return {"cik": cik, "rows_written": 0, "error": "no_holdings_parsed"}

        # Compute total value to derive pct_portfolio
        total_value = sum(h["value_usd"] for h in holdings) or 1.0

        # Resolve CUSIPs to symbols (universe-only)
        valid_universe = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        }

        rows_written = 0
        for rank, h in enumerate(sorted(holdings, key=lambda x: -x["value_usd"]), start=1):
            symbol = resolve_fn(h["cusip"], h["name"])
            if not symbol or symbol not in valid_universe:
                continue
            pct_portfolio = (h["value_usd"] / total_value) * 100.0
            conn.execute(
                """
                INSERT INTO institution_holdings
                    (cik, symbol, value_usd, shares, pct_portfolio, pct_outstanding,
                     rank_in_portfolio, as_of, source)
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, '13F')
                ON CONFLICT(cik, symbol, as_of) DO UPDATE SET
                    value_usd = excluded.value_usd,
                    shares = excluded.shares,
                    pct_portfolio = excluded.pct_portfolio,
                    rank_in_portfolio = excluded.rank_in_portfolio,
                    source = '13F'
                """,
                (
                    cik, symbol, h["value_usd"], h.get("shares"),
                    pct_portfolio, rank, period,
                ),
            )
            rows_written += 1

        conn.commit()
        return {"cik": cik, "rows_written": rows_written, "error": None, "period": period}
    finally:
        if own_conn:
            conn.close()


# ── historical backfill (sequential-quarter snapshots per CIK) ───


def process_institution_history(
    cik: str,
    *,
    quarters: int = 4,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Process the last N 13F-HRs for a CIK so we have sequential snapshots.

    The standard `process_institution` only fetches the most recent filing,
    which leaves the delta-flow math impossible (need 2+ snapshots per CIK to
    compute net adds/trims between quarters). This walks back `quarters`
    filings via the submissions JSON and writes each as a row in
    `institution_holdings` keyed by `as_of=period_of_report`.

    On-conflict: existing rows are updated (idempotent re-runs are safe).
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        filings = _list_13f_filings(cik)
        if not filings:
            return {"cik": cik, "error": "no_filings", "snapshots_written": 0, "rows_written": 0}

        snapshots_written = 0
        rows_written = 0
        errors: list[str] = []

        valid_universe = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        }

        for acc, period in filings[:quarters]:
            if not period:
                errors.append(f"{acc}:no_period")
                continue
            xml = _fetch_holdings_for_accession(cik, acc)
            if not xml:
                errors.append(f"{acc}:no_xml")
                continue
            holdings = parse_13f_holdings_xml(xml, period_of_report=period)
            if not holdings:
                errors.append(f"{acc}:no_holdings")
                continue

            total_value = sum(h["value_usd"] for h in holdings) or 1.0
            wrote = 0
            for rank, h in enumerate(sorted(holdings, key=lambda x: -x["value_usd"]), start=1):
                symbol = cusip_to_symbol(h["cusip"], h["name"])
                if not symbol or symbol not in valid_universe:
                    continue
                pct_portfolio = (h["value_usd"] / total_value) * 100.0
                conn.execute(
                    """
                    INSERT INTO institution_holdings
                        (cik, symbol, value_usd, shares, pct_portfolio, pct_outstanding,
                         rank_in_portfolio, as_of, source)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?, '13F')
                    ON CONFLICT(cik, symbol, as_of) DO UPDATE SET
                        value_usd = excluded.value_usd,
                        shares = excluded.shares,
                        pct_portfolio = excluded.pct_portfolio,
                        rank_in_portfolio = excluded.rank_in_portfolio,
                        source = '13F'
                    """,
                    (
                        cik, symbol, h["value_usd"], h.get("shares"),
                        pct_portfolio, rank, period,
                    ),
                )
                wrote += 1
            if wrote:
                snapshots_written += 1
                rows_written += wrote
            conn.commit()

        return {
            "cik": cik,
            "filings_found": len(filings),
            "snapshots_written": snapshots_written,
            "rows_written": rows_written,
            "errors": errors,
            "error": None if snapshots_written else "no_snapshots_written",
        }
    finally:
        if own_conn:
            conn.close()


def backfill_history(top: int | None = None, quarters: int = 4, *, log: bool = True) -> dict:
    """Backfill last `quarters` 13F-HR snapshots for every institution in DB.

    Used to unlock delta-flow math for the sector tape. Pass `top=None` to
    process every CIK in the institutions table.
    """
    init_db()
    conn = get_connection()
    try:
        sql = "SELECT cik FROM institutions ORDER BY total_aum DESC NULLS LAST"
        if top:
            sql += f" LIMIT {int(top)}"
        ciks = [r["cik"] for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()

    succeeded = 0
    failed = 0
    snapshots = 0
    rows = 0
    for cik in ciks:
        if log:
            print(f"  [13F-history] CIK {cik}…", flush=True)
        out = process_institution_history(cik, quarters=quarters)
        if out.get("error") and not out.get("snapshots_written"):
            failed += 1
            if log:
                print(f"    -> failed: {out.get('error')}", flush=True)
        else:
            succeeded += 1
            snapshots += out["snapshots_written"]
            rows += out["rows_written"]
            if log:
                print(f"    -> {out['snapshots_written']} snapshots, {out['rows_written']} rows", flush=True)
    return {
        "processed": len(ciks),
        "succeeded": succeeded,
        "failed": failed,
        "snapshots_written": snapshots,
        "rows_written": rows,
    }


# ── batch runner ────────────────────────────────────────────────


def run_for_top(top: int = 50, *, log: bool = True) -> dict:
    """Process the top-N institutions (by total_aum) currently in DB."""
    init_db()
    conn = get_connection()
    try:
        ciks = [
            r["cik"] for r in conn.execute(
                "SELECT cik FROM institutions ORDER BY total_aum DESC NULLS LAST LIMIT ?",
                (top,),
            ).fetchall()
        ]
    finally:
        conn.close()

    succeeded = 0
    failed = 0
    rows = 0
    for cik in ciks:
        if log:
            print(f"  [13F] CIK {cik}…")
        out = process_institution(cik)
        if out.get("error"):
            failed += 1
        else:
            succeeded += 1
            rows += out["rows_written"]
    return {
        "processed": len(ciks),
        "succeeded": succeeded,
        "failed": failed,
        "rows_written": rows,
    }


# ── CLI ─────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--cik", help="Single CIK to process")
    p.add_argument(
        "--backfill-history",
        action="store_true",
        help="Backfill last N sequential 13F-HRs per institution (unlocks delta-flow math)",
    )
    p.add_argument(
        "--quarters",
        type=int,
        default=4,
        help="How many sequential quarters to backfill per CIK (used with --backfill-history)",
    )
    args = p.parse_args()

    if args.backfill_history:
        out = backfill_history(top=args.top if args.top else None, quarters=args.quarters)
        for k, v in out.items():
            print(f"  {k:20s}: {v}")
        return 0 if out["failed"] == 0 else 1

    if args.cik:
        out = process_institution(args.cik)
        print(out)
        return 0 if not out.get("error") else 1

    out = run_for_top(args.top)
    for k, v in out.items():
        print(f"  {k:20s}: {v}")
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
