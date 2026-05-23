import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent.parent / "trading.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            report_type TEXT NOT NULL,
            content TEXT NOT NULL,
            verdict TEXT,
            risk_rating INTEGER,
            sentiment_score REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_symbol ON reports(symbol);
        CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(created_at);
        CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type);

        CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol);
        CREATE INDEX IF NOT EXISTS idx_alerts_date ON alerts(created_at);

        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, signal_name TEXT NOT NULL,
            timeframe TEXT, lookback_days INTEGER, hold_days INTEGER,
            total_trades INTEGER, wins INTEGER, losses INTEGER,
            win_rate REAL, avg_return REAL, total_return REAL,
            max_gain REAL, max_loss REAL, max_drawdown REAL,
            sharpe_ratio REAL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_results(symbol);

        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backtest_id INTEGER, symbol TEXT NOT NULL,
            signal_name TEXT, direction TEXT,
            entry_date TEXT, entry_price REAL,
            exit_date TEXT, exit_price REAL,
            pnl REAL, pnl_percent REAL, hold_days INTEGER,
            outcome TEXT
        );

        CREATE TABLE IF NOT EXISTS journal_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, direction TEXT NOT NULL,
            entry_date TEXT, entry_price REAL,
            exit_date TEXT, exit_price REAL,
            shares INTEGER, pnl REAL, pnl_percent REAL,
            report_verdict TEXT, thesis TEXT, notes TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal_trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_journal_status ON journal_trades(status);

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_name TEXT NOT NULL,
            date TEXT NOT NULL, total_value REAL,
            cash REAL, invested REAL,
            daily_return REAL, cumulative_return REAL,
            benchmark_return REAL, positions_json TEXT
        );

        CREATE TABLE IF NOT EXISTS api_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS simulation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            cycle_date TEXT NOT NULL,
            step TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_sim_run ON simulation_runs(run_id, cycle_date, step);

        CREATE TABLE IF NOT EXISTS precomputed_scores (
            symbol TEXT PRIMARY KEY,
            score_data TEXT NOT NULL,
            computed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            starting_capital REAL NOT NULL DEFAULT 100000,
            current_cash REAL NOT NULL DEFAULT 100000,
            risk_per_trade REAL NOT NULL DEFAULT 0.02,
            max_positions INTEGER NOT NULL DEFAULT 5,
            max_buys_per_cycle INTEGER NOT NULL DEFAULT 1,
            min_opportunity_score INTEGER NOT NULL DEFAULT 60,
            stop_loss_pct REAL NOT NULL DEFAULT 12.0,
            rebalance_frequency TEXT NOT NULL DEFAULT 'weekly',
            status TEXT NOT NULL DEFAULT 'stopped',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_run TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL DEFAULT 'long',
            shares INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            entry_date TEXT NOT NULL,
            stop_loss REAL,
            target REAL,
            status TEXT NOT NULL DEFAULT 'open',
            exit_price REAL,
            exit_date TEXT,
            pnl REAL,
            pnl_percent REAL,
            ai_reasoning TEXT,
            source TEXT NOT NULL DEFAULT 'ai',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            step TEXT NOT NULL,
            symbol TEXT,
            decision TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'ai',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            invested REAL NOT NULL,
            daily_return REAL DEFAULT 0,
            cumulative_return REAL DEFAULT 0,
            benchmark_value REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Knowledge-graph prototype tables (PROTOTYPE_PLAN.md) ──

        -- Industries (yfinance taxonomy + sector mapping)
        CREATE TABLE IF NOT EXISTS industries (
            code TEXT PRIMARY KEY,
            sector TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 4,800-stock target universe with tier classification
        CREATE TABLE IF NOT EXISTS stocks_universe (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            tier TEXT NOT NULL CHECK (tier IN ('A','B','C','D')),
            exchange TEXT,                      -- NASDAQ, NYSE, TSX, TSXV, CSE
            country TEXT,                       -- US, CA
            market_cap REAL,
            avg_dollar_volume REAL,
            in_sp500 INTEGER DEFAULT 0,
            in_russell1000 INTEGER DEFAULT 0,
            in_russell2000 INTEGER DEFAULT 0,
            in_tsx60 INTEGER DEFAULT 0,
            in_qqq INTEGER DEFAULT 0,
            source TEXT,                        -- where the row came from (hand|etf|tsx|tsxv|cse|nasdaq)
            as_of TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_stocks_universe_tier ON stocks_universe(tier);

        -- Stock → industry M2M (multi-tag for conglomerates with weights summing to 1.0)
        CREATE TABLE IF NOT EXISTS stock_industry (
            symbol TEXT NOT NULL,
            industry_code TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            is_primary INTEGER NOT NULL DEFAULT 1,
            source TEXT,                        -- 'yfinance' | 'hand'
            as_of TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (symbol, industry_code)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_industry_industry ON stock_industry(industry_code);

        -- Peer / competitor edges
        CREATE TABLE IF NOT EXISTS stock_peers (
            from_symbol TEXT NOT NULL,
            to_symbol TEXT NOT NULL,
            similarity REAL NOT NULL,           -- 0..1
            overlap_dimensions TEXT,            -- "cloud,AI,productivity" (Tier A only, NULL elsewhere)
            source TEXT NOT NULL,               -- 'hand' | 'claude_batch' | 'claude_validated'
            confidence TEXT NOT NULL,           -- 'high' | 'medium' | 'low'
            as_of TEXT NOT NULL DEFAULT (datetime('now')),
            evidence TEXT,
            PRIMARY KEY (from_symbol, to_symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_peers_from ON stock_peers(from_symbol);
        CREATE INDEX IF NOT EXISTS idx_stock_peers_to ON stock_peers(to_symbol);

        -- Supply-chain + structural relations
        CREATE TABLE IF NOT EXISTS stock_relations (
            from_symbol TEXT NOT NULL,
            to_symbol TEXT NOT NULL,
            relation_type TEXT NOT NULL,        -- supplier | customer | substitute | complement
            strength REAL NOT NULL,             -- 0..1
            polarity REAL NOT NULL DEFAULT 1.0, -- usually +1; -1 for substitutes (zero-sum)
            evidence TEXT,                      -- "10-K 2024 Item 1A" | "manual"
            as_of TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (from_symbol, to_symbol, relation_type)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_relations_from ON stock_relations(from_symbol);
        CREATE INDEX IF NOT EXISTS idx_stock_relations_to ON stock_relations(to_symbol);
        CREATE INDEX IF NOT EXISTS idx_stock_relations_type ON stock_relations(relation_type);

        -- Keyword → industry/stock impacts (the news engine's brain)
        CREATE TABLE IF NOT EXISTS keyword_impact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            industry_code TEXT,                 -- nullable if target_stock is set
            target_stock TEXT,                  -- nullable if industry_code is set
            polarity REAL NOT NULL,             -- -1.0 to +1.0
            weight REAL NOT NULL,               -- 0..1
            domain TEXT,                        -- 'ai' | 'oil' | 'war' | 'tariff' | 'rates' | 'fda' | 'court' | 'm&a' | ...
            notes TEXT,
            as_of TEXT NOT NULL DEFAULT (datetime('now')),
            CHECK (industry_code IS NOT NULL OR target_stock IS NOT NULL)
        );
        CREATE INDEX IF NOT EXISTS idx_keyword_impact_kw ON keyword_impact(keyword);
        CREATE INDEX IF NOT EXISTS idx_keyword_impact_domain ON keyword_impact(domain);

        -- Optional: keyword groups for backtest aggregation (deferred)
        CREATE TABLE IF NOT EXISTS keyword_groups (
            group_name TEXT NOT NULL,
            keyword TEXT NOT NULL,
            PRIMARY KEY (group_name, keyword)
        );

        -- Resumable per-industry peer-ranking job ledger (Phase 3 Day 13).
        -- Each row tracks one (industry, tier) batch sent to Claude. Lets us
        -- pause / resume across subscription budget windows.
        CREATE TABLE IF NOT EXISTS peer_jobs (
            industry_code TEXT NOT NULL,
            tier TEXT NOT NULL CHECK (tier IN ('A','B','C','D')),
            status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'done' | 'failed'
            last_attempt TEXT,
            symbols_processed INTEGER DEFAULT 0,
            edges_written INTEGER DEFAULT 0,
            error TEXT,
            PRIMARY KEY (industry_code, tier)
        );
        CREATE INDEX IF NOT EXISTS idx_peer_jobs_status ON peer_jobs(status);

        -- Resumable per-stock 10-K extraction job ledger (Phase 4 Day 17).
        -- One row per stock; tracks extraction state for SEC EDGAR Item 1A mining.
        CREATE TABLE IF NOT EXISTS tenk_jobs (
            symbol TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'done' | 'failed' | 'skipped'
            last_attempt TEXT,
            filing_url TEXT,
            edges_written INTEGER DEFAULT 0,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tenk_jobs_status ON tenk_jobs(status);

        -- Phase 6: commodity nodes + stock-commodity exposure edges.
        -- Captures how stock prices respond to commodity price moves, which
        -- powers cross-sector causal chains ("gas crisis → fertilizer up").
        CREATE TABLE IF NOT EXISTS commodities (
            code TEXT PRIMARY KEY,            -- 'oil', 'gas', 'copper', etc.
            name TEXT NOT NULL,
            unit TEXT,                        -- 'barrel', 'mmbtu', 'lb', etc.
            benchmark_ticker TEXT,            -- ETF / proxy ticker for price tracking
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS stock_commodity_exposure (
            symbol TEXT NOT NULL,
            commodity_code TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('input','output','hedge')),
            polarity REAL NOT NULL,           -- -1..+1
            elasticity REAL NOT NULL,         -- 0..1, pass-through strength
            confidence TEXT NOT NULL,         -- 'high' | 'medium' | 'low' | 'validated' | 'disputed' | 'weak'
            evidence TEXT,                    -- '10-K Item 7' | 'industry standard' | 'manual'
            as_of TEXT NOT NULL DEFAULT (datetime('now')),
            source TEXT NOT NULL,             -- 'hand' | 'claude' | 'backtest'
            PRIMARY KEY (symbol, commodity_code, role)
        );
        CREATE INDEX IF NOT EXISTS idx_sce_symbol ON stock_commodity_exposure(symbol);
        CREATE INDEX IF NOT EXISTS idx_sce_commodity ON stock_commodity_exposure(commodity_code);

        -- Resumable per-stock causal-extraction job ledger (Phase 6).
        CREATE TABLE IF NOT EXISTS causal_jobs (
            symbol TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            last_attempt TEXT,
            edges_written INTEGER DEFAULT 0,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_causal_jobs_status ON causal_jobs(status);

        -- ── Phase 7A: Institutional ownership (BlackRock/Vanguard/etc.) ──
        CREATE TABLE IF NOT EXISTS institutions (
            cik TEXT PRIMARY KEY,             -- SEC CIK (string, leading zeros allowed)
            name TEXT NOT NULL,
            type TEXT,                        -- 'index_fund' | 'active_mgr' | 'hedge_fund' | 'pension' | 'sovereign'
            total_aum REAL,                   -- USD
            last_updated TEXT
        );

        CREATE TABLE IF NOT EXISTS institution_holdings (
            cik TEXT NOT NULL,
            symbol TEXT NOT NULL,
            value_usd REAL,
            shares REAL,
            pct_portfolio REAL,               -- % of institution's portfolio
            pct_outstanding REAL,             -- % of company's float (more actionable)
            rank_in_portfolio INTEGER,
            as_of TEXT NOT NULL,              -- typically the filing's period end
            source TEXT,                      -- '13F' | 'hand'
            PRIMARY KEY (cik, symbol, as_of)
        );
        CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON institution_holdings(symbol);
        CREATE INDEX IF NOT EXISTS idx_holdings_cik ON institution_holdings(cik);

        -- ── Phase 7B: Edge freshness ────────────────────────────────────
        CREATE TABLE IF NOT EXISTS edge_freshness (
            symbol TEXT PRIMARY KEY,
            last_extracted_at TEXT,
            last_summary_hash TEXT,
            last_correlation_check TEXT,
            last_filing_check TEXT,
            last_baseline_correlation REAL,
            status TEXT NOT NULL DEFAULT 'fresh',   -- 'fresh' | 'aging' | 'needs_review' | 'stale'
            trigger_reason TEXT,
            flagged_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_freshness_status ON edge_freshness(status);

        -- ── Sector-influence Wave 1: entity alias table ───────────────────
        CREATE TABLE IF NOT EXISTS entity_aliases (
            ticker          TEXT NOT NULL,
            cik             TEXT,
            uei             TEXT,
            alias_type      TEXT NOT NULL CHECK (alias_type IN (
                                'legal', 'common', 'subsidiary',
                                'uspto_canonical', 'sam_business_name',
                                'brand', 'override'
                            )),
            alias_name      TEXT NOT NULL,
            alias_source    TEXT NOT NULL,
            confidence      REAL NOT NULL,
            created_at      TEXT NOT NULL,
            PRIMARY KEY (ticker, alias_type, alias_name)
        );
        CREATE INDEX IF NOT EXISTS idx_entity_aliases_name ON entity_aliases(alias_name);
        CREATE INDEX IF NOT EXISTS idx_entity_aliases_cik ON entity_aliases(cik);
        CREATE INDEX IF NOT EXISTS idx_entity_aliases_uei ON entity_aliases(uei);

        -- ── Sector-influence Wave 1: per-source freshness registry ───────
        CREATE TABLE IF NOT EXISTS source_freshness (
            source                  TEXT PRIMARY KEY,
            cadence                 TEXT NOT NULL,      -- 'hourly' | 'daily' | 'weekly' | 'monthly' | 'quarterly'
            ttl_seconds             INTEGER NOT NULL,
            last_fetched_at         TEXT,
            next_due_at             TEXT,
            last_status             TEXT,               -- 'ok' | 'error' | 'rate_limited' | 'empty'
            last_error              TEXT,
            last_payload_count      INTEGER,
            rate_limit_budget       INTEGER,
            rate_limit_remaining    INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_source_freshness_next_due ON source_freshness(next_due_at);

        -- ── Sector-influence Wave 1: forward-looking catalysts ───────────
        CREATE TABLE IF NOT EXISTS known_future_events (
            event_id        TEXT PRIMARY KEY,
            ticker          TEXT,
            event_type      TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            source          TEXT NOT NULL,
            source_url      TEXT,
            details_json    TEXT,
            added_at        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_known_future_events_date ON known_future_events(event_date);
        CREATE INDEX IF NOT EXISTS idx_known_future_events_ticker ON known_future_events(ticker);

        -- ── Refresh jobs (manual button-triggered refreshes) ────────────
        CREATE TABLE IF NOT EXISTS refresh_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | failed
            progress REAL DEFAULT 0,                -- 0..1
            processed INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            message TEXT,
            error TEXT,
            result_json TEXT,
            started_at TEXT,
            finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_refresh_jobs_kind ON refresh_jobs(kind);
        CREATE INDEX IF NOT EXISTS idx_refresh_jobs_status ON refresh_jobs(status);

        -- ── AI Track Record: log every AI verdict at generation time ────
        -- Used to grade the AI's accuracy after the prediction window passes.
        CREATE TABLE IF NOT EXISTS ai_decisions (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at              TEXT NOT NULL,           -- ISO 8601 UTC
            symbol                  TEXT NOT NULL,
            source                  TEXT NOT NULL,           -- 'recommendation' | 'ai_analyst' | 'bubble_score' | 'bull_narrative' | 'risk_narrative'
            decision                TEXT NOT NULL,           -- label or normalized verdict
            score                   REAL,                    -- numeric value when applicable (e.g. bubble score)
            price_at_call           REAL NOT NULL,
            context_json            TEXT,                    -- inputs used (verdict, bubble, analyst rating, …)
            prediction_window_days  INTEGER NOT NULL DEFAULT 30,
            metadata_json           TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_decisions_symbol ON ai_decisions(symbol);
        CREATE INDEX IF NOT EXISTS idx_ai_decisions_source ON ai_decisions(source);
        CREATE INDEX IF NOT EXISTS idx_ai_decisions_created ON ai_decisions(created_at);

        CREATE TABLE IF NOT EXISTS ai_decision_outcomes (
            decision_id     INTEGER PRIMARY KEY,
            evaluated_at    TEXT NOT NULL,
            price_now       REAL NOT NULL,
            return_pct      REAL NOT NULL,
            was_correct     INTEGER NOT NULL,                -- 0/1
            notes_json      TEXT,
            FOREIGN KEY (decision_id) REFERENCES ai_decisions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ai_outcomes_was_correct ON ai_decision_outcomes(was_correct);

        -- ── Sector-influence Wave 2: entity-match decision log ──────────
        -- Every fetcher that resolves a free-text name to a ticker writes
        -- one row here, so the Entity Match Debug card can show how each
        -- data point was attributed (CIK exact / UEI exact / fuzzy / etc.)
        -- and what alternatives were considered.
        CREATE TABLE IF NOT EXISTS entity_match_decisions (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                      TEXT,                -- nullable: NULL when no match found
            source                      TEXT NOT NULL,       -- 'patents' | 'fda' | 'gov_contracts' | 'itc' | 'sec_8k' | ...
            input_name                  TEXT NOT NULL,       -- free-text input that was resolved
            matched_alias               TEXT,                -- normalized alias_name from entity_aliases (NULL if no match)
            method                      TEXT NOT NULL,       -- 'exact_cik' | 'exact_uei' | 'exact_alias' | 'fuzzy' | 'no_match'
            confidence                  REAL NOT NULL,       -- 0.0 if no match, else 0.0-1.0
            rejected_candidates_json    TEXT,                -- JSON list of {ticker, alias, score} for top alternatives
            decided_at                  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_entity_match_decisions_ticker ON entity_match_decisions(ticker);
        CREATE INDEX IF NOT EXISTS idx_entity_match_decisions_source ON entity_match_decisions(source);
        CREATE INDEX IF NOT EXISTS idx_entity_match_decisions_decided_at ON entity_match_decisions(decided_at);

        -- ── Orange Book bulk cache (pharma patent cliff signal) ─────────
        -- Caches the FDA Orange Book ZIP unzipped, joined products+patents.
        -- Refreshed every 7 days via fda_orange_book.py.
        CREATE TABLE IF NOT EXISTS orange_book_patents (
            application_number  TEXT NOT NULL,
            patent_number       TEXT NOT NULL,
            patent_expire_date  TEXT,
            drug_substance_flag INTEGER,
            drug_product_flag   INTEGER,
            use_code            TEXT,
            sponsor_name        TEXT,
            trade_name          TEXT,
            fetched_at          TEXT NOT NULL,
            PRIMARY KEY (application_number, patent_number)
        );
        CREATE INDEX IF NOT EXISTS idx_orange_book_sponsor ON orange_book_patents(sponsor_name);
        CREATE INDEX IF NOT EXISTS idx_orange_book_expire ON orange_book_patents(patent_expire_date);
    """)
    conn.commit()
    conn.close()


def cache_get(key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        cache_delete(key)
        return None
    return json.loads(row["value"])


def cache_set(key: str, value: dict, ttl_minutes: int = 15) -> None:
    conn = get_connection()
    now = datetime.utcnow()
    expires = now + timedelta(minutes=ttl_minutes)
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (key, json.dumps(value, default=str), now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()


def cache_delete(key: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def log_ai_decision(
    symbol: str,
    source: str,
    decision: str,
    price_at_call: float,
    *,
    score: float | None = None,
    context: dict | None = None,
    prediction_window_days: int = 30,
    metadata: dict | None = None,
) -> int | None:
    """Append a row to ai_decisions and return the new id.

    Swallows errors and returns None — logging must NEVER break the live AI path.
    Callers should gate this on `not from_cache` so we only record FRESH decisions.
    """
    try:
        if not symbol or not source or decision is None or price_at_call is None:
            return None
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO ai_decisions
              (created_at, symbol, source, decision, score, price_at_call,
               context_json, prediction_window_days, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat() + "Z",
                str(symbol).upper(),
                str(source),
                str(decision),
                float(score) if score is not None else None,
                float(price_at_call),
                json.dumps(context, default=str) if context else None,
                int(prediction_window_days),
                json.dumps(metadata, default=str) if metadata else None,
            ),
        )
        decision_id = cur.lastrowid
        conn.commit()
        conn.close()
        return decision_id
    except Exception:
        return None


def save_precomputed_score(symbol: str, score_data: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO precomputed_scores (symbol, score_data, computed_at) VALUES (?, ?, ?)",
        (symbol, json.dumps(score_data, default=str), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_precomputed_score(symbol: str, max_age_minutes: int = 60) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT score_data, computed_at FROM precomputed_scores WHERE symbol = ?", (symbol,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    computed_at = datetime.fromisoformat(row["computed_at"])
    if datetime.utcnow() - computed_at > timedelta(minutes=max_age_minutes):
        return None
    return json.loads(row["score_data"])


def get_all_precomputed_scores(max_age_minutes: int = 60) -> dict:
    conn = get_connection()
    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()
    rows = conn.execute(
        "SELECT symbol, score_data FROM precomputed_scores WHERE computed_at > ?", (cutoff,)
    ).fetchall()
    conn.close()
    return {row["symbol"]: json.loads(row["score_data"]) for row in rows}


def save_simulation_step(run_id: str, cycle_date: str, step: str, data: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO simulation_runs (run_id, cycle_date, step, data) VALUES (?, ?, ?, ?)",
        (run_id, cycle_date, step, json.dumps(data, default=str)),
    )
    conn.commit()
    conn.close()


def get_simulation_runs() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT run_id FROM simulation_runs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [r["run_id"] for r in rows]


def get_simulation_cycles(run_id: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT cycle_date FROM simulation_runs WHERE run_id = ? ORDER BY cycle_date ASC", (run_id,)
    ).fetchall()
    conn.close()
    return [r["cycle_date"] for r in rows]


def get_simulation_step(run_id: str, cycle_date: str, step: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT data FROM simulation_runs WHERE run_id = ? AND cycle_date = ? AND step = ?",
        (run_id, cycle_date, step),
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["data"])
    return None


def get_simulation_all_steps(run_id: str, cycle_date: str) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT step, data FROM simulation_runs WHERE run_id = ? AND cycle_date = ?",
        (run_id, cycle_date),
    ).fetchall()
    conn.close()
    return {r["step"]: json.loads(r["data"]) for r in rows}


def clear_simulation(run_id: str | None = None) -> None:
    conn = get_connection()
    if run_id:
        conn.execute("DELETE FROM simulation_runs WHERE run_id = ?", (run_id,))
    else:
        conn.execute("DELETE FROM simulation_runs")
    conn.commit()
    conn.close()


def log_api_call(source: str, endpoint: str, status: str, error: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO api_log (source, endpoint, status, error_message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (source, endpoint, status, error, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def save_report(symbol: str, report_type: str, content: str, verdict: str | None = None,
                risk_rating: int | None = None, sentiment_score: float | None = None) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reports (symbol, report_type, content, verdict, risk_rating, sentiment_score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, report_type, content, verdict, risk_rating, sentiment_score, datetime.utcnow().isoformat()),
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id


def get_reports(symbol: str | None = None, report_type: str | None = None, limit: int = 20) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM reports WHERE 1=1"
    params: list = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if report_type:
        query += " AND report_type = ?"
        params.append(report_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report_by_id(report_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_watchlist() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_watchlist_item(symbol: str, name: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO watchlist (symbol, name, added_at) VALUES (?, ?, ?)",
        (symbol.upper(), name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def remove_watchlist_item(symbol: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
    conn.commit()
    conn.close()


# --- Alerts ---

def save_alert(symbol: str, alert_type: str, message: str,
               old_value: str = "", new_value: str = "", severity: str = "info") -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO alerts (symbol, alert_type, message, old_value, new_value, severity, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, alert_type, message, old_value, new_value, severity, datetime.utcnow().isoformat()),
    )
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id


def get_alerts(symbol: str | None = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM alerts WHERE 1=1"
    params: list = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_report_for_symbol(symbol: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reports WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# --- Backtest ---

def save_backtest_result(data: dict) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO backtest_results (symbol, signal_name, timeframe, lookback_days, hold_days, "
        "total_trades, wins, losses, win_rate, avg_return, total_return, "
        "max_gain, max_loss, max_drawdown, sharpe_ratio, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (data["symbol"], data["signal_name"], data.get("timeframe", ""),
         data.get("lookback_days", 0), data.get("hold_days", 0),
         data["total_trades"], data["wins"], data["losses"],
         data["win_rate"], data["avg_return"], data["total_return"],
         data["max_gain"], data["max_loss"], data["max_drawdown"],
         data["sharpe_ratio"], datetime.utcnow().isoformat()),
    )
    conn.commit()
    bt_id = cursor.lastrowid
    conn.close()
    return bt_id


def save_backtest_trade(bt_id: int, trade: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO backtest_trades (backtest_id, symbol, signal_name, direction, "
        "entry_date, entry_price, exit_date, exit_price, pnl, pnl_percent, hold_days, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (bt_id, trade["symbol"], trade["signal_name"], trade["direction"],
         trade["entry_date"], trade["entry_price"], trade["exit_date"], trade["exit_price"],
         trade["pnl"], trade["pnl_percent"], trade["hold_days"], trade["outcome"]),
    )
    conn.commit()
    conn.close()


# --- Journal ---

def save_journal_trade(symbol: str, direction: str, entry_date: str, entry_price: float,
                       shares: int, report_verdict: str = "", thesis: str = "") -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO journal_trades (symbol, direction, entry_date, entry_price, "
        "shares, report_verdict, thesis, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
        (symbol.upper(), direction, entry_date, entry_price, shares,
         report_verdict, thesis, datetime.utcnow().isoformat()),
    )
    conn.commit()
    trade_id = cursor.lastrowid
    conn.close()
    return trade_id


def close_journal_trade(trade_id: int, exit_price: float, exit_date: str = "", notes: str = "") -> None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM journal_trades WHERE id = ?", (trade_id,)).fetchone()
    if not row:
        conn.close()
        return
    entry_price = row["entry_price"]
    shares = row["shares"]
    direction = row["direction"]

    if direction == "long":
        pnl = (exit_price - entry_price) * shares
    else:
        pnl = (entry_price - exit_price) * shares
    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if direction == "long" else ((entry_price - exit_price) / entry_price * 100)

    if not exit_date:
        exit_date = datetime.utcnow().strftime("%Y-%m-%d")

    conn.execute(
        "UPDATE journal_trades SET exit_date=?, exit_price=?, pnl=?, pnl_percent=?, notes=?, status='closed' WHERE id=?",
        (exit_date, exit_price, pnl, pnl_pct, notes, trade_id),
    )
    conn.commit()
    conn.close()


def get_journal_trades(status: str | None = None, symbol: str | None = None) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM journal_trades WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Portfolio Snapshots ---

def save_portfolio_snapshot(name: str, date: str, total_value: float, cash: float,
                            invested: float, daily_return: float, cumulative_return: float,
                            benchmark_return: float, positions_json: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO portfolio_snapshots (portfolio_name, date, total_value, cash, invested, "
        "daily_return, cumulative_return, benchmark_return, positions_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, date, total_value, cash, invested, daily_return, cumulative_return,
         benchmark_return, positions_json),
    )
    conn.commit()
    conn.close()


def get_portfolio_history(name: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM portfolio_snapshots WHERE portfolio_name = ? ORDER BY date",
        (name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
