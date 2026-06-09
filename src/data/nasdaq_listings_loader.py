"""NASDAQ official listings loader — populates Tier D for the universe.

Source: NASDAQ Trader publishes the canonical exchange listings as two
pipe-delimited text files, refreshed nightly, no key required.

    https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt
    https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt

For Tier D we ONLY care about NASDAQ-listed `Market Category = 'S'`
(Capital Market — the smallest tier of NASDAQ, ~600-800 micro/small caps).
Global Select ('Q') and Global Market ('G') names are typically already
in the S&P/Russell loaders, and tier_classifier promotes them to A/B/C
when the cap/index data is known.

The ON CONFLICT clause in `apply_universe_memberships` will never downgrade
an existing A/B/C row to D — so re-running this loader on an existing
universe is safe and idempotent.

Run from the refresh page (kind `nasdaq_listings`) or via:
    .venv/bin/python -m src.data.nasdaq_listings_loader
"""
from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

import httpx

from src.data.tier_classifier import StockClassificationInputs, classify_tier
from src.utils.db import get_connection, init_db, log_api_call

logger = logging.getLogger(__name__)


NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
# otherlisted.txt covers NYSE / NYSE American / NYSE Arca / IEX — the non-NASDAQ
# venues. Together with nasdaqlisted.txt it names ~every US-listed security.
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

# Cache the raw file for a day — the upstream refreshes nightly so re-fetching
# within the day is wasted bandwidth.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "nasdaq_listings"
_HTTP_TIMEOUT = 30


# ── fetch + parse ───────────────────────────────────────────────────


def _fetch_symdir(filename: str, url: str, *,
                  cache_dir: Path | str = DEFAULT_CACHE_DIR,
                  force: bool = False) -> str:
    """Return the raw text of a Nasdaq Trader symdir file, caching on disk.

    Falls back to a stale cached copy if the network fetch fails.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / filename

    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8")

    try:
        resp = httpx.get(
            url,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "TradingApp/1.0"},
        )
        resp.raise_for_status()
        text = resp.text
        cache_path.write_text(text, encoding="utf-8")
        log_api_call("nasdaq_listings", filename, "success")
        return text
    except Exception as e:
        log_api_call("nasdaq_listings", filename, "error", str(e))
        # Fall back to a stale cached copy if available — better than nothing.
        if cache_path.exists():
            logger.warning("symdir fetch failed (%s), using stale cache: %r", filename, e)
            return cache_path.read_text(encoding="utf-8")
        raise


def fetch_nasdaqlisted(*, cache_dir: Path | str = DEFAULT_CACHE_DIR,
                       force: bool = False) -> str:
    """Return the raw text of nasdaqlisted.txt, caching the response on disk."""
    return _fetch_symdir("nasdaqlisted.txt", NASDAQ_LISTED_URL,
                         cache_dir=cache_dir, force=force)


def fetch_otherlisted(*, cache_dir: Path | str = DEFAULT_CACHE_DIR,
                      force: bool = False) -> str:
    """Return the raw text of otherlisted.txt (NYSE/AMEX/Arca), caching on disk."""
    return _fetch_symdir("otherlisted.txt", OTHER_LISTED_URL,
                         cache_dir=cache_dir, force=force)


def parse_nasdaqlisted(text: str) -> list[dict]:
    """Parse the pipe-delimited file into rows.

    Skips:
      • the header row
      • the trailing "File Creation Time" footer
      • test issues (`Test Issue == 'Y'`)
      • ETFs (`ETF == 'Y'`)

    Returns dicts with: symbol, security_name, market_category (Q/G/S),
    financial_status, is_etf, is_test.
    """
    rows: list[dict] = []
    lines = text.splitlines()
    if not lines:
        return rows

    header = lines[0].split("|")
    try:
        idx_sym   = header.index("Symbol")
        idx_name  = header.index("Security Name")
        idx_mc    = header.index("Market Category")
        idx_test  = header.index("Test Issue")
        idx_fs    = header.index("Financial Status")
        idx_etf   = header.index("ETF")
    except ValueError as e:
        logger.warning("nasdaq file format unexpected: %r", e)
        return rows

    for line in lines[1:]:
        # The footer line starts with "File Creation Time:" — skip it and
        # anything that doesn't look like a data row.
        if line.startswith("File Creation Time") or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) <= max(idx_sym, idx_name, idx_mc, idx_test, idx_fs, idx_etf):
            continue
        if parts[idx_test].strip().upper() == "Y":
            continue
        if parts[idx_etf].strip().upper() == "Y":
            continue
        symbol = parts[idx_sym].strip()
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "security_name": parts[idx_name].strip(),
            "market_category": parts[idx_mc].strip().upper(),  # Q/G/S
            "financial_status": parts[idx_fs].strip().upper(),
            "is_etf": False,
            "is_test": False,
        })
    return rows


def parse_otherlisted(text: str) -> list[dict]:
    """Parse otherlisted.txt (NYSE / NYSE American / Arca / IEX) into rows.

    Uses the `ACT Symbol` column. Skips the header, the footer, ETFs
    (`ETF == 'Y'`), and test issues (`Test Issue == 'Y'`).
    Returns dicts with: symbol, security_name.
    """
    rows: list[dict] = []
    lines = text.splitlines()
    if not lines:
        return rows

    header = lines[0].split("|")
    try:
        idx_sym  = header.index("ACT Symbol")
        idx_name = header.index("Security Name")
        idx_etf  = header.index("ETF")
        idx_test = header.index("Test Issue")
    except ValueError as e:
        logger.warning("otherlisted file format unexpected: %r", e)
        return rows

    for line in lines[1:]:
        if line.startswith("File Creation Time") or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) <= max(idx_sym, idx_name, idx_etf, idx_test):
            continue
        if parts[idx_test].strip().upper() == "Y":
            continue
        if parts[idx_etf].strip().upper() == "Y":
            continue
        symbol = parts[idx_sym].strip()
        if not symbol:
            continue
        rows.append({"symbol": symbol, "security_name": parts[idx_name].strip()})
    return rows


# Trailing security-type descriptors to drop for a clean display name.
_SECURITY_TYPE_TAIL = re.compile(
    r"\s+(?:Common Stock|Common Shares|Ordinary Shares)\s*$", re.IGNORECASE
)


def _clean_security_name(raw: str) -> str:
    """Light cleanup → a display name in the curated tier-A style.

    Drops the directory's security-type descriptor: the part after ` - `
    (nasdaqlisted form, e.g. `X - Common Stock`) and a trailing
    `Common Stock`/`Common Shares`/`Ordinary Shares` (otherlisted form).
    """
    name = (raw or "").split(" - ")[0].strip()
    name = _SECURITY_TYPE_TAIL.sub("", name).strip()
    return name


_MARKET_CATEGORY_TO_TIER_INPUT = {
    "Q": "Global Select",      # large NASDAQ — already picked up by index loaders
    "G": "Global Market",
    "S": "Capital Market",     # micro/small caps — these are our Tier D candidates
}


# ── upsert ──────────────────────────────────────────────────────────


def apply_nasdaq_listings(
    rows: list[dict],
    *,
    only_capital_market: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Upsert NASDAQ rows into stocks_universe.

    By default only Capital Market (Tier D candidates) — Global Select/Market
    are already covered by the S&P/Russell loaders. Pass
    `only_capital_market=False` to add the others too as a backstop (rare).

    Safe to re-run: the existing ON CONFLICT logic in
    `apply_universe_memberships` never downgrades A/B/C → D. This loader
    re-implements the same protection inline.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    if only_capital_market:
        rows = [r for r in rows if r["market_category"] == "S"]

    inserted = 0
    updated = 0
    skipped_existing_higher = 0

    try:
        for row in rows:
            symbol = row["symbol"]
            market_category = row["market_category"]

            tier_input_label = _MARKET_CATEGORY_TO_TIER_INPUT.get(market_category)
            if tier_input_label is None:
                continue

            inputs = StockClassificationInputs(
                symbol=symbol,
                nasdaq_market_tier=tier_input_label,
            )
            new_tier = classify_tier(inputs)  # "C" for Q/G, "D" for S

            existing = conn.execute(
                "SELECT tier, name FROM stocks_universe WHERE symbol=?", (symbol,)
            ).fetchone()
            if existing:
                # Don't downgrade. If existing tier is already A/B/C, leave it
                # alone (the index loader knows better — that symbol is in
                # S&P/Russell/etc).
                existing_tier = existing["tier"]
                if existing_tier in ("A", "B", "C"):
                    skipped_existing_higher += 1
                    continue
                # Otherwise update tier + name if missing.
                conn.execute(
                    """
                    UPDATE stocks_universe
                    SET tier   = ?,
                        name   = COALESCE(name, ?),
                        source = COALESCE(source, 'nasdaq_listings')
                    WHERE symbol = ?
                    """,
                    (new_tier, row["security_name"], symbol),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO stocks_universe (
                        symbol, name, tier, exchange, country,
                        market_cap, avg_dollar_volume,
                        in_sp500, in_russell1000, in_russell2000, in_tsx60, in_qqq,
                        source
                    ) VALUES (?, ?, ?, 'NASDAQ', 'US', NULL, NULL, 0, 0, 0, 0, 0, 'nasdaq_listings')
                    """,
                    (symbol, row["security_name"], new_tier),
                )
                inserted += 1

        conn.commit()
        return {
            "inserted": inserted,
            "updated": updated,
            "skipped_existing_higher": skipped_existing_higher,
            "total_processed": len(rows),
        }
    finally:
        if own_conn:
            conn.close()


# ── one-shot ────────────────────────────────────────────────────────


def refresh_nasdaq_listings(*, force_fetch: bool = False,
                             only_capital_market: bool = True) -> dict[str, int]:
    """End-to-end: fetch (or read cache) → parse → upsert. Returns counts."""
    text = fetch_nasdaqlisted(force=force_fetch)
    rows = parse_nasdaqlisted(text)
    return apply_nasdaq_listings(rows, only_capital_market=only_capital_market)


# ── name backfill (nasdaqlisted + otherlisted → symbol→name map) ────


def build_name_map(*, force: bool = False) -> dict[str, str]:
    """Merge nasdaqlisted + otherlisted into {SYMBOL: clean display name}.

    Either file being unavailable degrades to whatever the other provides
    (never raises). Names are lightly cleaned via `_clean_security_name`.
    """
    name_map: dict[str, str] = {}
    # Both directories are authoritative; either order is fine. nasdaq second
    # so a symbol present on both ends up with the NASDAQ-form name.
    for fetch, parse in (
        (fetch_otherlisted, parse_otherlisted),
        (fetch_nasdaqlisted, parse_nasdaqlisted),
    ):
        try:
            for r in parse(fetch(force=force)):
                clean = _clean_security_name(r["security_name"])
                if clean:
                    name_map[r["symbol"].upper()] = clean
        except Exception as e:
            logger.warning("name-map source unavailable: %r", e)
    return name_map


def backfill_universe_names(
    name_map: dict[str, str], *, conn: sqlite3.Connection | None = None
) -> dict[str, int]:
    """Fill `stocks_universe.name` for rows currently missing a name.

    Only touches rows where name IS NULL or empty — never overwrites an
    existing name. Returns {total_missing, filled, remaining}.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        missing = conn.execute(
            "SELECT symbol FROM stocks_universe WHERE name IS NULL OR TRIM(name) = ''"
        ).fetchall()
        filled = 0
        for row in missing:
            symbol = row["symbol"]
            new_name = name_map.get(symbol.upper())
            if not new_name:
                continue
            conn.execute(
                "UPDATE stocks_universe SET name = ? "
                "WHERE symbol = ? AND (name IS NULL OR TRIM(name) = '')",
                (new_name, symbol),
            )
            filled += 1
        conn.commit()
        return {
            "total_missing": len(missing),
            "filled": filled,
            "remaining": len(missing) - filled,
        }
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    out = refresh_nasdaq_listings(force_fetch=True)
    print(out)
