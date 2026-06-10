"""Two-stage Claude (Opus) analyst: triage the universe to a shortlist, then
deep-read the shortlist packets and pick the final 10. A momentum-rank fallback
guarantees 10 picks even if Claude is unavailable (never fabricates evidence).
"""
from __future__ import annotations

import json

from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db

_SHORTLIST_N = 35
_PICKS_N = 10


def _universe() -> list[str]:
    from api.services import predictions_service
    return predictions_service._load_universe_ab()


def _assemble_compact(symbols, as_of):
    from api.services import analyst_pit_service
    return analyst_pit_service.assemble_compact(symbols, as_of)


def _assemble_full(symbols, as_of, *, allow_live_search):
    from api.services import analyst_pit_service
    return analyst_pit_service.assemble_full(symbols, as_of, allow_live_search=allow_live_search)


def predict_for_date(as_of: str, *, mode: str) -> dict:
    """Run the two-stage analyst for `as_of` and persist top-10 to daily_predictions.

    mode: 'bootstrap' (PIT, no live search) | 'live' (full board + search).
    Idempotent per date: existing rows for `as_of` are replaced.
    """
    from api.services import predictions_service
    init_db()
    strategy_version = predictions_service.ensure_ai_analyst_strategy()
    try:
        from api.services import analyst_playbook
        playbook = analyst_playbook.read()
    except ImportError:
        playbook = ""
    allow_live = (mode == "live")

    compact = _assemble_compact(_universe(), as_of)
    shortlist = triage(compact, playbook=playbook)
    packets = _assemble_full(shortlist, as_of, allow_live_search=allow_live)
    picks = deep_pick(packets, playbook=playbook, allow_live_search=allow_live)

    _persist(as_of, picks, mode=mode, strategy_version=strategy_version)
    return {"date": as_of, "mode": mode, "count": len(picks), "shortlist": len(shortlist)}


def _persist(as_of: str, picks: list[dict], *, mode: str, strategy_version: int) -> None:
    """Write rank 1..N picks to daily_predictions, replacing any existing rows
    for `as_of` (idempotent)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM daily_predictions WHERE prediction_date=?", (as_of,))
        for i, pick in enumerate(picks, start=1):
            conn.execute(
                "INSERT INTO daily_predictions "
                "(prediction_date, rank, symbol, score, reasoning, strategy_version, "
                " created_at, components_json, mode) VALUES (?,?,?,?,?,?,?,?,?)",
                (as_of, i, pick["symbol"], pick.get("confidence"),
                 pick.get("reasoning"), strategy_version, now,
                 json.dumps(pick.get("evidence") or {}), mode),
            )
        conn.commit()
    finally:
        conn.close()


def triage(compact_rows, *, playbook, claude=ask_claude_json) -> list[str]:
    """Stage 1: Opus reads the compact universe table + playbook → a shortlist of
    up to 35 symbols. Returns only symbols that exist in `compact_rows`."""
    prompt = _triage_prompt(compact_rows, playbook)   # MUST contain the word "shortlist"
    raw = claude(prompt, model="opus", timeout=180, retries=1)
    syms = raw.get("shortlist") if isinstance(raw, dict) else None
    valid = {r["symbol"] for r in compact_rows}
    return [s for s in (syms or []) if s in valid][:_SHORTLIST_N]


def deep_pick(packets, *, playbook, allow_live_search, claude=ask_claude_json) -> list[dict]:
    """Stage 2: Opus reads full packets (+ web search on live days) + playbook →
    final 10 picks, each {symbol, reasoning, confidence}. Falls back to ranking
    packets by momentum.trailing_return when Claude is unavailable/invalid."""
    tools = "WebSearch,WebFetch" if allow_live_search else ""
    raw = claude(_pick_prompt(packets, playbook), model="opus", timeout=240,
                 retries=1, allowed_tools=tools)
    picks = _valid_picks(raw, set(packets))
    if picks:
        return picks[:_PICKS_N]
    # deterministic fallback — never fabricate evidence
    ranked = sorted(packets.items(),
                    key=lambda kv: (kv[1].get("momentum") or {}).get("trailing_return", 0.0)
                    if isinstance(kv[1].get("momentum"), dict) else 0.0,
                    reverse=True)
    return [{"symbol": s, "reasoning": "fallback: momentum rank (Claude unavailable)",
             "confidence": None} for s, _ in ranked[:_PICKS_N]]


def _triage_prompt(compact_rows, playbook) -> str:
    """Stage-1 prompt: embed playbook + compact universe, ask for a JSON shortlist."""
    rows_json = json.dumps(compact_rows, default=str)
    return (
        "You are a disciplined equity analyst screening for tomorrow's top "
        "gainers. Use ONLY the playbook and the compact universe table below — "
        "do not rely on outside knowledge or invent data.\n\n"
        f"PLAYBOOK:\n{playbook}\n\n"
        f"COMPACT UNIVERSE (JSON array of rows):\n{rows_json}\n\n"
        f"Select the {_SHORTLIST_N} best top-gainer candidates that fit the "
        "playbook. Return at most "
        f"{_SHORTLIST_N} symbols, each of which MUST appear in the table above.\n"
        'Respond with JSON only: {"shortlist": ["SYM1", "SYM2", ...]}'
    )


def _pick_prompt(packets, playbook) -> str:
    """Stage-2 prompt: embed playbook + full packets, ask for exactly 10 picks."""
    packets_json = json.dumps(packets, default=str)
    return (
        "You are a disciplined equity analyst making final next-day picks. "
        "Use ONLY the playbook and the per-symbol evidence packets below "
        "(plus any web search results if tools are available). Do not invent "
        "evidence.\n\n"
        f"PLAYBOOK:\n{playbook}\n\n"
        f"EVIDENCE PACKETS (JSON object keyed by symbol):\n{packets_json}\n\n"
        f"Choose exactly {_PICKS_N} symbols. For each, give a concise reasoning "
        "grounded in the packet and a confidence as a float between 0 and 1.\n"
        'Respond with JSON only: '
        '{"picks": [{"symbol": "SYM", "reasoning": "...", "confidence": 0.0}, ...]}'
    )


def _valid_picks(raw, packet_symbols: set) -> list[dict]:
    """Normalize Claude's pick payload; drop anything not keyed in the packets."""
    if not isinstance(raw, dict):
        return []
    items = raw.get("picks")
    if not isinstance(items, list):
        return []
    cleaned: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sym = item.get("symbol")
        if sym not in packet_symbols:
            continue
        cleaned.append({
            "symbol": sym,
            "reasoning": item.get("reasoning") or "",
            "confidence": item.get("confidence"),
        })
    return cleaned
