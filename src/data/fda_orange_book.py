"""FDA Orange Book bulk-download cache + per-sponsor patent fetch.

Why bulk: openFDA does NOT expose Orange Book patents via JSON API. The
patent → expiration mapping lives only in FDA's bulk text download at:
    https://www.fda.gov/media/76860/download

Strategy:
  1. Download the ZIP (~50 MB) into trading.db's orange_book_patents table.
  2. Refresh weekly (~24 active substances change per release).
  3. Per-sponsor queries hit the local SQLite cache, not the network.

Per CLAUDE.md: data layer. May read/write trading.db. Returns [] on any error.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

import httpx

from src.utils.db import get_connection, init_db, log_api_call


_ORANGE_BOOK_ZIP_URL = "https://www.fda.gov/media/76860/download"
_CACHE_TTL_DAYS = 7


def _cache_is_stale(conn) -> bool:
    """True if the cache is empty or older than _CACHE_TTL_DAYS."""
    row = conn.execute(
        "SELECT MAX(fetched_at) FROM orange_book_patents"
    ).fetchone()
    if not row or not row[0]:
        return True
    last = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
    return (datetime.now(tz=timezone.utc) - last) > timedelta(days=_CACHE_TTL_DAYS)


def _yn_to_bool(s: str) -> int:
    return 1 if (s or "").strip().upper() == "Y" else 0


def _parse_fda_date(s: str) -> str:
    """Convert FDA's 'Mon DD, YYYY' (e.g. 'Aug 15, 2026') to ISO 'YYYY-MM-DD'.

    Returns the original string if parse fails (preserves data for display
    while still allowing chronological sort once normalized).
    """
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _refresh_cache(conn, *, http_get=None) -> int:
    """Download the Orange Book ZIP, parse products.txt + patent.txt, repopulate cache.

    Returns rows inserted. Caller is responsible for catching exceptions.
    `http_get` is dependency-injected for tests; defaults to httpx.get.
    """
    fetch = http_get if http_get is not None else (lambda url: httpx.get(url, timeout=120.0, follow_redirects=True))
    resp = fetch(_ORANGE_BOOK_ZIP_URL)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        # File names are case-variable across FDA releases — match case-insensitive
        product_name = next((n for n in z.namelist() if n.lower().endswith("products.txt")), None)
        patent_name  = next((n for n in z.namelist() if n.lower().endswith("patent.txt")),  None)
        if not product_name or not patent_name:
            raise RuntimeError(f"missing products.txt/patent.txt in zip: {z.namelist()}")

        # Build appl_no -> (sponsor, trade_name) map from products.txt
        appl_meta: dict[str, tuple[str, str]] = {}
        with z.open(product_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text, delimiter="~")  # FDA uses tilde
            # FALLBACK: if tilde-delimited doesn't yield rows, retry with pipe
            rows = list(reader)
            if not rows or len(reader.fieldnames or []) <= 1:
                # Try pipe instead
                text = io.TextIOWrapper(z.open(product_name), encoding="utf-8", errors="replace")
                reader = csv.DictReader(text, delimiter="|")
                rows = list(reader)
            for r in rows:
                appl_no = (r.get("Appl_No") or r.get("Appl No") or "").strip()
                if not appl_no:
                    continue
                sponsor = (r.get("Applicant_Full_Name") or r.get("Applicant") or "").strip()
                trade = (r.get("Trade_Name") or r.get("Drug Name") or "").strip()
                # Keep first non-empty values per appl_no
                if appl_no not in appl_meta or not appl_meta[appl_no][0]:
                    appl_meta[appl_no] = (sponsor, trade)

        # Parse patent.txt → flatten with appl_meta join
        rows_to_insert = []
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        with z.open(patent_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text, delimiter="~")
            rows = list(reader)
            if not rows or len(reader.fieldnames or []) <= 1:
                text = io.TextIOWrapper(z.open(patent_name), encoding="utf-8", errors="replace")
                reader = csv.DictReader(text, delimiter="|")
                rows = list(reader)
            for r in rows:
                appl_no = (r.get("Appl_No") or "").strip()
                patent_no = (r.get("Patent_No") or "").strip()
                if not appl_no or not patent_no:
                    continue
                expire = _parse_fda_date(r.get("Patent_Expire_Date_Text") or "")
                substance = _yn_to_bool(r.get("Drug_Substance_Flag", ""))
                product = _yn_to_bool(r.get("Drug_Product_Flag", ""))
                use_code = (r.get("Patent_Use_Code") or "").strip()
                sponsor, trade = appl_meta.get(appl_no, ("", ""))
                rows_to_insert.append((
                    appl_no, patent_no, expire,
                    substance, product, use_code,
                    sponsor, trade, now_iso,
                ))

    # Clear + rebuild — atomic in one transaction
    conn.execute("DELETE FROM orange_book_patents")
    conn.executemany(
        """
        INSERT OR REPLACE INTO orange_book_patents
          (application_number, patent_number, patent_expire_date,
           drug_substance_flag, drug_product_flag, use_code,
           sponsor_name, trade_name, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    conn.commit()
    return len(rows_to_insert)


def fetch_patents_for_sponsor(
    sponsor_name: str,
    *,
    limit: int = 100,
    http_get=None,
) -> list[dict]:
    """Return Orange Book patents protecting drugs by `sponsor_name`.

    Refreshes the local cache from the FDA bulk download on first call or
    weekly. Per-call query then hits the local SQLite cache (fast).

    Returns normalized list of dicts:
        {application_number, patent_number, patent_expire_date,
         drug_substance_flag, drug_product_flag, use_code,
         sponsor_name, trade_name}

    Empty list on no-match or any error. Failures logged via log_api_call.
    """
    if not sponsor_name or not sponsor_name.strip():
        return []

    init_db()
    conn = get_connection()
    try:
        if _cache_is_stale(conn):
            try:
                n = _refresh_cache(conn, http_get=http_get)
                log_api_call("fda_orange_book", _ORANGE_BOOK_ZIP_URL, "ok",
                             error=f"refreshed {n} rows")
            except Exception as exc:
                log_api_call("fda_orange_book", _ORANGE_BOOK_ZIP_URL, "error",
                             error=str(exc))
                return []

        like = f"%{sponsor_name.strip().upper()}%"
        rows = conn.execute(
            """
            SELECT application_number, patent_number, patent_expire_date,
                   drug_substance_flag, drug_product_flag, use_code,
                   sponsor_name, trade_name
            FROM orange_book_patents
            WHERE UPPER(sponsor_name) LIKE ?
            ORDER BY patent_expire_date
            LIMIT ?
            """,
            (like, limit),
        ).fetchall()
        return [
            {
                "application_number": r["application_number"],
                "patent_number": r["patent_number"],
                "patent_expire_date": r["patent_expire_date"],
                "drug_substance_flag": bool(r["drug_substance_flag"]),
                "drug_product_flag":   bool(r["drug_product_flag"]),
                "use_code":            r["use_code"],
                "sponsor_name":        r["sponsor_name"],
                "trade_name":          r["trade_name"],
            }
            for r in rows
        ]
    finally:
        conn.close()
