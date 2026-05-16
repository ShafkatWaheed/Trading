"""8-K Item 5.02 executive turnover parser.

Pure regex/text logic — no I/O, no external dependencies. Lives in
`src/utils/` so the analysis layer can consume it without violating
the CLAUDE.md "analysis must not import from data/" dependency rule.

Stdlib only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# -- 8-K Item 5.02 exec turnover parsing (Wave 2) ---------------------


@dataclass(frozen=True)
class ExecChange:
    """Parsed 8-K Item 5.02 event (exec departure or appointment)."""
    event_type: str           # 'departure' | 'appointment'
    person_name: str
    role: str                 # 'CEO' | 'CFO' | 'COO' | 'Chief Financial Officer' | ...
    raw_excerpt: str          # snippet from the filing (for the card display)


# C-suite role patterns. Order: longer first to avoid 'Chief' matching 'CEO'.
_ROLE_PATTERNS = (
    r"Chief\s+Executive\s+Officer",
    r"Chief\s+Financial\s+Officer",
    r"Chief\s+Operating\s+Officer",
    r"Chief\s+Technology\s+Officer",
    r"Chief\s+Accounting\s+Officer",
    r"Chief\s+Legal\s+Officer",
    r"\bCEO\b", r"\bCFO\b", r"\bCOO\b", r"\bCTO\b",
    r"President", r"Director",
)
_ROLE_RE = re.compile("|".join(_ROLE_PATTERNS), flags=re.IGNORECASE)

_ITEM_502_RE = re.compile(
    r"Item\s*5\.02", flags=re.IGNORECASE,
)
_NAME_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z'\-]+))\b"
)
_DEPARTURE_TRIGGERS = (
    "resign", "depart", "step down", "stepped down", "termination", "terminated",
    "will leave", "no longer serve", "ceased to be",
)
_APPOINTMENT_TRIGGERS = (
    "appoint", "elect", "named", "succeed", "assume the role",
)


def _classify_sentence(s: str) -> str | None:
    low = s.lower()
    is_dep = any(t in low for t in _DEPARTURE_TRIGGERS)
    is_app = any(t in low for t in _APPOINTMENT_TRIGGERS)
    if is_dep and not is_app:
        return "departure"
    if is_app and not is_dep:
        return "appointment"
    if is_dep and is_app:
        first_dep = min((low.find(t) for t in _DEPARTURE_TRIGGERS if t in low), default=10**9)
        first_app = min((low.find(t) for t in _APPOINTMENT_TRIGGERS if t in low), default=10**9)
        return "departure" if first_dep < first_app else "appointment"
    return None


# Words/phrases that look like names to the regex but aren't people.
# Compared against `cand.lower()` (full match) or the first token.
_NAME_BLOCK_FULL = {
    "item", "board", "company", "corporation", "directors", "certain officers",
    "certain officer", "election of", "appointment of", "departure of",
    "compensatory arrangements", "board of",
}
_NAME_BLOCK_FIRST_TOKEN = {
    "on", "the", "ms", "mr", "mrs", "dr", "our", "this", "that", "it",
    "he", "she", "they", "we", "as", "to", "in", "of", "at", "by",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}


def _is_real_name(cand: str) -> bool:
    low = cand.lower()
    if low in _NAME_BLOCK_FULL:
        return False
    first = low.split()[0] if low.split() else ""
    if first in _NAME_BLOCK_FIRST_TOKEN:
        return False
    return True


def _strip_item_502_header(section: str) -> str:
    """Drop the 'Item 5.02 ...' title block (up to first blank line or sentence break).

    The Item 5.02 header itself contains words like 'Departure', 'Appointment',
    'Directors', 'Certain Officers' that produce false positives for both
    classification and name extraction. Remove it before parsing sentences.
    """
    # Prefer cutting at the first blank line after the header.
    blank = re.search(r"\n\s*\n", section)
    if blank:
        return section[blank.end():]
    # Fall back to cutting after the first period that follows the 'Item 5.02' tag.
    m = re.search(r"Item\s*5\.02[^.]*\.", section, flags=re.IGNORECASE)
    if m:
        return section[m.end():]
    return section


def parse_8k_item_502(text: str) -> list[ExecChange]:
    """Parse 8-K text for Item 5.02 exec changes.

    Returns a list of ExecChange events (departure/appointment) found in
    the Item 5.02 section. Returns [] if no Item 5.02 content is present.
    """
    if not text or not _ITEM_502_RE.search(text):
        return []

    start = _ITEM_502_RE.search(text).start()
    next_item = re.search(r"Item\s*\d+\.\d+", text[start + 1:], flags=re.IGNORECASE)
    end = (start + 1 + next_item.start()) if next_item else len(text)
    section = text[start:end]
    body = _strip_item_502_header(section)

    out: list[ExecChange] = []
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        s = sentence.strip()
        if len(s) < 20:
            continue
        kind = _classify_sentence(s)
        if kind is None:
            continue
        # Find all role matches; prefer the most specific (longest) one so
        # that 'Chief Financial Officer' wins over 'Director' / 'President'
        # that may appear earlier (e.g. 'Board of Directors').
        role_matches = list(_ROLE_RE.finditer(s))
        if not role_matches:
            continue
        role = max((m.group(0) for m in role_matches), key=len)
        name = ""
        for m in _NAME_RE.finditer(s):
            cand = m.group(0)
            if not _is_real_name(cand):
                continue
            name = cand
            break
        if not name:
            continue
        out.append(ExecChange(
            event_type=kind,
            person_name=name,
            role=role,
            raw_excerpt=s[:300],
        ))
    return out
