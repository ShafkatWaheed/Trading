"""Index-membership loaders — pull ETF holdings to discover Tier B/C/D universe.

Goal: build the set of ~4,800 stocks across multiple major indices by reading
the holdings CSVs that ETF issuers publish (iShares, Invesco, etc.). Each
function returns a `set[str]` of ticker symbols that we then feed into
`stocks_universe` along with index-membership flags.

Design — offline-first:
  * `load_holdings_csv(path)` parses any ETF holdings CSV from disk. This is
    the unit of testable functionality (no network).
  * `fetch_holdings(url, cache_path)` is the network adapter — it caches the
    fetched CSV to disk and then delegates to `load_holdings_csv`. Network
    calls are explicit, opt-in, and never made during tests.
  * `apply_universe_memberships(...)` upserts the universe table from a
    pre-built dict of {index_name: set[symbols]}.

Tested data sources (URLs may shift; cache file paths are stable):
  - iShares Core S&P 500 (IVV):       holdings CSV
  - iShares Russell 1000 (IWB):       holdings CSV
  - iShares Russell 2000 (IWM):       holdings CSV
  - Invesco QQQ (NASDAQ 100):         holdings CSV
  - iShares S&P/TSX 60 (XIU.TO):      holdings CSV (Canada)

Run order during week 1:
  1. (Online)  Run `fetch_all_indices()` once to populate cache.
  2. (Offline) Run `apply_universe_memberships()` from cached files.

The "fake data" rule from CLAUDE.md is respected: no synthetic data in src/.
Tests that exercise the parser use small real-format fixtures kept under
tests/fixtures/ which are excluded from the data-integrity audit.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Iterable

from src.data.tier_a_seed import tier_a_symbols
from src.data.tier_classifier import (
    StockClassificationInputs,
    TierThresholds,
    classify_tier,
)
from src.utils.db import get_connection, init_db


# Standard ETF holdings cache directory (created on first use).
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "index_cache"


# ── CSV parsing ───────────────────────────────────────────────────────


def load_holdings_csv(path: Path | str) -> set[str]:
    """Parse an ETF holdings CSV and return the set of ticker symbols.

    iShares / Invesco CSVs typically have ~10 lines of fund metadata before
    the actual holdings header row that starts with "Ticker," — we skip
    everything before that. Empty / cash / future rows are filtered out.

    Tickers come back in *exchange* form (no .TO/.V suffix on iShares US
    funds; with suffix on iShares Canadian funds). Caller is responsible for
    canonicalizing to whatever convention `stocks_universe` uses.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"holdings CSV not found: {p}")

    text = p.read_text(encoding="utf-8", errors="replace")
    return _parse_holdings_text(text)


def _parse_holdings_text(text: str) -> set[str]:
    # Find the data header — first line that starts with "Ticker," (case-insensitive).
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.lstrip().lower().startswith("ticker,") or line.lstrip().lower().startswith('"ticker"'):
            header_idx = i
            break
    if header_idx is None:
        return set()  # malformed or empty fund

    body = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(body))
    out: set[str] = set()
    for row in reader:
        sym = (row.get("Ticker") or row.get("ticker") or "").strip()
        if not sym:
            continue
        # Filter: cash holdings, futures, FX — not equities.
        if sym.upper() in ("CASH", "USD", "-"):
            continue
        if "FUTURE" in sym.upper() or sym.startswith("--"):
            continue
        out.add(sym.upper())
    return out


# ── Network-fetch adapter (opt-in) ────────────────────────────────────


def fetch_holdings(url: str, cache_path: Path | str, *, force: bool = False) -> set[str]:
    """Download ETF holdings CSV (network) and cache to disk; return tickers.

    `force=True` re-downloads even if the cache file exists.
    """
    import httpx  # local import — keeps module import-clean for offline tests

    cache = Path(cache_path)
    cache.parent.mkdir(parents=True, exist_ok=True)

    if cache.exists() and not force:
        return load_holdings_csv(cache)

    resp = httpx.get(url, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    cache.write_bytes(resp.content)
    return load_holdings_csv(cache)


# ── Universe upsert ───────────────────────────────────────────────────


# Display-name lookup for the cached files. The actual URLs are intentionally
# left in fetch_all_indices() rather than hard-coded here, since iShares and
# Invesco rotate their CDN paths.
INDEX_FILES: dict[str, str] = {
    "sp500":      "ivv_holdings.csv",
    "russell1k":  "iwb_holdings.csv",
    "russell2k":  "iwm_holdings.csv",
    "qqq":        "qqq_holdings.csv",
    "tsx60":      "xiu_holdings.csv",
}


def load_all_cached(cache_dir: Path | str = DEFAULT_CACHE_DIR) -> dict[str, set[str]]:
    """Load every index from its cached CSV. Missing caches return empty sets."""
    cache = Path(cache_dir)
    out: dict[str, set[str]] = {}
    for index_name, fname in INDEX_FILES.items():
        path = cache / fname
        out[index_name] = load_holdings_csv(path) if path.exists() else set()
    return out


def apply_universe_memberships(
    memberships: dict[str, set[str]],
    *,
    name_map: dict[str, str] | None = None,
    market_cap_map: dict[str, float] | None = None,
    adv_map: dict[str, float] | None = None,
    thresholds: TierThresholds | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Upsert all stocks discovered via index memberships into `stocks_universe`.

    `memberships` looks like {"sp500": {"AAPL", "MSFT", ...}, ...}.
    Optional `*_map` dicts provide enrichment for the tier classifier
    (otherwise the classifier falls back to "in_sp500 alone → tier B").

    Tier A from `tier_a_seed.py` is force-promoted regardless of cap/ADV.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    name_map = name_map or {}
    market_cap_map = market_cap_map or {}
    adv_map = adv_map or {}
    forced_a = set(tier_a_symbols())

    # Union all symbols across indices.
    all_symbols: set[str] = set()
    for syms in memberships.values():
        all_symbols.update(syms)

    inserted = 0
    updated = 0

    try:
        for symbol in sorted(all_symbols):
            inputs = StockClassificationInputs(
                symbol=symbol,
                market_cap=market_cap_map.get(symbol),
                avg_dollar_volume=adv_map.get(symbol),
                in_sp500=symbol in memberships.get("sp500", set()),
                in_russell1000=symbol in memberships.get("russell1k", set()),
                in_russell2000=symbol in memberships.get("russell2k", set()),
                in_qqq=symbol in memberships.get("qqq", set()),
                in_tsx60=symbol in memberships.get("tsx60", set()),
                hand_seeded_tier_a=symbol in forced_a,
            )
            tier = classify_tier(inputs, thresholds)

            existing = conn.execute(
                "SELECT 1 FROM stocks_universe WHERE symbol=?", (symbol,)
            ).fetchone()
            if existing:
                updated += 1
            else:
                inserted += 1

            conn.execute(
                """
                INSERT INTO stocks_universe (
                    symbol, name, tier, exchange, country,
                    market_cap, avg_dollar_volume,
                    in_sp500, in_russell1000, in_russell2000, in_tsx60, in_qqq,
                    source
                ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, 'index_loader')
                ON CONFLICT(symbol) DO UPDATE SET
                    tier            = CASE WHEN excluded.tier = 'A' THEN 'A'
                                           WHEN stocks_universe.tier = 'A' THEN 'A'
                                           ELSE excluded.tier END,
                    market_cap      = COALESCE(excluded.market_cap, stocks_universe.market_cap),
                    avg_dollar_volume = COALESCE(excluded.avg_dollar_volume, stocks_universe.avg_dollar_volume),
                    in_sp500        = excluded.in_sp500,
                    in_russell1000  = excluded.in_russell1000,
                    in_russell2000  = excluded.in_russell2000,
                    in_tsx60        = excluded.in_tsx60,
                    in_qqq          = excluded.in_qqq,
                    name            = COALESCE(stocks_universe.name, excluded.name)
                """,
                (
                    symbol,
                    name_map.get(symbol),
                    tier,
                    inputs.market_cap,
                    inputs.avg_dollar_volume,
                    int(inputs.in_sp500),
                    int(inputs.in_russell1000),
                    int(inputs.in_russell2000),
                    int(inputs.in_tsx60),
                    int(inputs.in_qqq),
                ),
            )

        conn.commit()
        return {"inserted": inserted, "updated": updated, "total_seen": len(all_symbols)}
    finally:
        if own_conn:
            conn.close()


# ── Convenience: end-to-end refresh ───────────────────────────────────


def refresh_universe_from_cache(cache_dir: Path | str = DEFAULT_CACHE_DIR) -> dict[str, int]:
    """One-shot convenience: read all cached CSVs, upsert to stocks_universe.

    Run AFTER `fetch_all_indices()` (network) has populated the cache.
    """
    memberships = load_all_cached(cache_dir)
    return apply_universe_memberships(memberships)


# ── Network fetch driver (opt-in) ─────────────────────────────────────


# iShares & Invesco CDN paths shift periodically; left as constants here so a
# single point of update suffices when they break.
INDEX_URLS: dict[str, str] = {
    "sp500":     "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund",
    "russell1k": "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund",
    "russell2k": "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
    "qqq":       "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ",
    "tsx60":     "https://www.blackrock.com/ca/investors/en/products/239837/ishares-sp-tsx-60-index-etf/1506923770892.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund",
}


def fetch_all_indices(
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    *,
    force: bool = False,
    indices: Iterable[str] | None = None,
) -> dict[str, set[str]]:
    """Pull every configured index's holdings CSV. Returns memberships dict.

    Cache-miss behavior: downloads. Cache-hit behavior: parses local file.
    `force=True` always re-downloads. Use `indices=["sp500"]` to update one.
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    targets = list(indices) if indices else list(INDEX_URLS.keys())
    out: dict[str, set[str]] = {}
    for name in targets:
        url = INDEX_URLS[name]
        path = cache / INDEX_FILES[name]
        try:
            out[name] = fetch_holdings(url, path, force=force)
        except Exception as exc:
            # Don't fail the whole refresh on one bad source — log + empty.
            print(f"[index_loader] {name} fetch failed: {exc}")
            out[name] = set()
    return out
