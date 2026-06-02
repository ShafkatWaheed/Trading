"""Dual-class share equivalents.

The graph stores peer / supplier / customer / holder edges per ticker, but
some companies trade under two tickers (different voting rights, same
business). Historically edges were seeded against whichever class was
canonical at seeding time, which leaves the non-canonical class looking
edgeless (e.g. GOOG has 1 edge in the graph; GOOGL has dozens — they're the
same business).

This module provides a small map + helpers so query sites can expand a
single ticker to its sibling set at query time. No data migration required.
"""
from __future__ import annotations


# Bidirectional dual/multi-class equivalence groups. Each ticker maps to all
# OTHER tickers for the same company.
#
# IMPORTANT: only include pairs that are actually present in stocks_universe
# under these exact spellings. Yahoo / our universe uses DASH (BRK-B), not dot
# (BRK.B); some duals use no separator at all (BFA/BFB). Adding a non-existent
# ticker to a group is harmless (queries just won't find it) but adding a
# WRONG-SPELLING ticker creates a silent gap, so verify before adding.
#
# Verified present in current stocks_universe (run check_share_classes.py to
# re-verify after universe loader runs).
_GROUPS: list[set[str]] = [
    {"GOOG", "GOOGL"},          # Alphabet — Class C / Class A (both verified)
    {"FOX",  "FOXA"},           # Fox Corporation (both verified)
    {"NWS",  "NWSA"},           # News Corp (both verified)
    {"LBRDA", "LBRDK"},         # Liberty Broadband (both verified)
    {"HEI",  "HEIA"},           # Heico — universe uses concatenated form
]
# Removed (one or both tickers absent from universe):
#   BRK.A/BRK.B  — only BRK-B exists, no Class A in universe → no sibling to unify
#   BF.A/BF.B    — BFA/BFB exist but are Tier B with no names → likely not
#                  Brown-Forman duals; needs manual verification before re-adding
#   MOG.A/MOG.B  — neither variant in universe
#   CWEN/CWEN.A  — neither variant in universe


# Flatten into a sym → siblings (excluding self) map for O(1) lookup
_SIBLINGS: dict[str, frozenset[str]] = {}
for group in _GROUPS:
    for sym in group:
        _SIBLINGS[sym.upper()] = frozenset(s.upper() for s in group if s.upper() != sym.upper())


def siblings(symbol: str) -> frozenset[str]:
    """Other tickers for the same underlying company. Empty for single-class names.

    Example:  siblings("GOOG")  → frozenset({"GOOGL"})
              siblings("AAPL")  → frozenset()
    """
    return _SIBLINGS.get((symbol or "").upper(), frozenset())


def equivalents(symbol: str) -> list[str]:
    """All tickers in the same equivalence group, including the input.

    Order: input first, then siblings sorted. Useful for `WHERE sym IN (...)`.

    Example:  equivalents("GOOG")  → ["GOOG", "GOOGL"]
              equivalents("AAPL")  → ["AAPL"]
    """
    sym = (symbol or "").upper()
    sibs = siblings(sym)
    if not sibs:
        return [sym]
    return [sym, *sorted(sibs)]


def is_sibling(a: str, b: str) -> bool:
    """True iff a and b are different tickers for the same underlying company."""
    a_u = (a or "").upper()
    b_u = (b or "").upper()
    if a_u == b_u:
        return False
    return b_u in _SIBLINGS.get(a_u, frozenset())
