"""Simulation replay: read past simulation_runs records."""
from __future__ import annotations

from src.utils.db import (
    init_db, get_simulation_runs, get_simulation_cycles, get_simulation_step,
)


_VALID_STEPS = {"market_pulse", "discover", "deep_dive", "trades", "ai_decision"}


def list_runs() -> list[str]:
    init_db()
    return get_simulation_runs()


def list_cycles(run_id: str) -> list[str]:
    init_db()
    return get_simulation_cycles(run_id)


def get_step(run_id: str, cycle_date: str, step: str) -> dict | None:
    init_db()
    if step not in _VALID_STEPS:
        return None
    return get_simulation_step(run_id, cycle_date, step)
