"""Pure scoring/ranking helpers for daily picks. No I/O, no src imports beyond stdlib."""
from __future__ import annotations


def conviction_from_score(score: float | None) -> str:
    """Map a 0-100 opportunity score to high/med/low. None -> 'low'."""
    if score is None:
        return "low"
    s = float(score)
    if s >= 70:
        return "high"
    if s >= 45:
        return "med"
    return "low"


def rank_candidates(cands: list[dict], *, key: str, top_n: int) -> list[dict]:
    """Stable descending sort by `key` (missing/None -> 0), truncated to top_n."""
    ranked = sorted(cands, key=lambda c: float(c.get(key) or 0), reverse=True)
    return ranked[:top_n]
