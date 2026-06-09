"""Pre-market top movers screener.

Scores the entire Tier A universe by pre-market gap and returns the top
gainers + losers along with that day's predicted picks overlaid so the
user can see at a glance: "which of today's predictions are already
moving pre-open?"

Reuses predictions_service._bulk_premarket_signals (which itself uses
yfinance + 30-min cache) so this page doesn't double-fetch.

Output shape:
  {
    "date":              "2026-06-09",
    "as_of":             "2026-06-09T13:30:00Z",
    "universe_size":     150,
    "gainers":           [{"symbol", "gap_pct", "in_predictions", "rank"}],
    "losers":            [...],
    "predicted_premarket": [
      {"symbol", "rank", "gap_pct" (or None if no pre-market data)}
    ],
  }
"""
from __future__ import annotations

from datetime import datetime, timezone

from api.services import predictions_service


def get_premarket_movers(*, top_n: int = 20) -> dict:
    """Compute the top-N pre-market gainers + losers from Tier A.

    Overlays today's predictions so the page can chip "predicted" badges
    on movers that the prediction list already named.
    """
    symbols = predictions_service._load_universe("A")
    if not symbols:
        return {
            "date":          datetime.now(tz=timezone.utc).date().isoformat(),
            "as_of":         datetime.now(tz=timezone.utc).isoformat(),
            "universe_size": 0,
            "gainers":       [],
            "losers":        [],
            "predicted_premarket": [],
        }

    # bulk_premarket_signals returns score in [-1, +1] (5% saturation).
    # We multiply by 5 to recover the gap %.
    scores = predictions_service._bulk_premarket_signals(symbols)

    today_preds = predictions_service.get_predictions_today()
    pred_ranks = {p["symbol"]: p["rank"] for p in (today_preds.get("picks") or [])}

    movers = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    def _row(sym: str, score: float, rank: int) -> dict:
        return {
            "symbol":          sym,
            "gap_pct":         round(score * 5.0, 2),    # un-normalize back to %
            "in_predictions":  sym in pred_ranks,
            "predicted_rank":  pred_ranks.get(sym),
        }

    gainers = [_row(s, v, i + 1) for i, (s, v) in enumerate(movers[:top_n])]
    losers  = [_row(s, v, i + 1) for i, (s, v) in enumerate(list(reversed(movers))[:top_n])]

    # Predictions list with pre-market data attached
    predicted_premarket = []
    for p in (today_preds.get("picks") or []):
        sym = p["symbol"]
        score = scores.get(sym)
        predicted_premarket.append({
            "symbol":   sym,
            "rank":     p["rank"],
            "gap_pct":  round(score * 5.0, 2) if score is not None else None,
        })

    return {
        "date":          datetime.now(tz=timezone.utc).date().isoformat(),
        "as_of":         datetime.now(tz=timezone.utc).isoformat(),
        "universe_size": len(symbols),
        "scored_size":   len(scores),
        "gainers":       gainers,
        "losers":        losers,
        "predicted_premarket": predicted_premarket,
    }
