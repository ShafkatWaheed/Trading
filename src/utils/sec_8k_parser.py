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

# Font-family names that leak from PDF/HTML metadata into text extraction.
_FONT_WORDS = {
    "times", "new", "roman", "arial", "helvetica", "calibri", "courier",
    "sans", "serif", "verdana", "georgia", "tahoma", "garamond", "cambria",
}

# Company-suffix tokens (registrant's own name leaking through).
_COMPANY_SUFFIX_WORDS = {
    "inc", "corp", "corporation", "company", "co", "ltd", "llc", "lp",
    "holdings", "group", "trust", "plc", "sa", "ag", "nv", "limited",
    "incorporated",
}

# Form / document boilerplate (matches the structure of an SEC filing).
_DOC_BOILERPLATE_WORDS = {
    "item", "form", "section", "exhibit", "schedule", "annex", "appendix",
    "part", "article",
}

# Body-meta words pulled from headings inside Item 5.02 itself.
_BODY_META_WORDS = {
    "board", "directors", "director", "committee", "officers", "officer",
    "registrant", "company", "corporation",
}

# C-suite / role words that the name regex can grab when no real name exists
# next to the role. Keeps "Chief Financial" from being detected as a person.
_ROLE_WORDS = {
    "chief", "executive", "financial", "operating", "technology", "accounting",
    "legal", "president", "vice", "principal", "senior", "general", "counsel",
    "secretary", "treasurer", "controller", "manager", "head",
}

# Calendar tokens (months, days, fiscal quarters).
_CALENDAR_WORDS = {
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "q1", "q2", "q3", "q4",
}

# Sentence starters / titles / prepositions that can begin a capitalized run.
_SENTENCE_STARTER_WORDS = {
    "on", "the", "mr", "ms", "mrs", "dr", "as", "in", "by", "with", "upon",
    "our", "this", "that", "it", "he", "she", "they", "we", "to", "of", "at",
    "for", "from", "an", "a",
}

# Tokens that must not appear as EITHER the first OR last word of a candidate
# name. Compared lowercase, with punctuation stripped.
_NAME_TOKEN_BLOCKLIST = (
    _FONT_WORDS
    | _COMPANY_SUFFIX_WORDS
    | _DOC_BOILERPLATE_WORDS
    | _BODY_META_WORDS
    | _CALENDAR_WORDS
    | _SENTENCE_STARTER_WORDS
    | _ROLE_WORDS
)


def _clean_token(tok: str) -> str:
    """Lowercase + strip punctuation so blocklist comparisons are robust."""
    return re.sub(r"[^a-zA-Z0-9]", "", tok).lower()


def _is_real_name(cand: str) -> bool:
    """Validate that a regex-matched candidate looks like a real person's name.

    Rejects font names, company names, document boilerplate, calendar tokens,
    single-word matches, names with digits, and overly long matches.
    """
    if not cand:
        return False
    # Reject overly long matches (likely caught a sentence fragment).
    if len(cand) > 60:
        return False
    # Reject anything containing digits (real names don't have digits).
    if any(ch.isdigit() for ch in cand):
        return False

    low = cand.lower().strip()
    if low in _NAME_BLOCK_FULL:
        return False

    tokens = cand.split()
    # Must contain at least 2 tokens (First + Last).
    if len(tokens) < 2:
        return False

    first_clean = _clean_token(tokens[0])
    last_clean = _clean_token(tokens[-1])

    # First token must look like a given name: starts with capital, >= 2 letters.
    if len(first_clean) < 2 or not tokens[0][:1].isupper():
        return False
    # Last token (likely surname) must be at least 3 letters.
    if len(last_clean) < 3:
        return False

    # Reject if either the first OR last token is in the blocklist.
    if first_clean in _NAME_TOKEN_BLOCKLIST:
        return False
    if last_clean in _NAME_TOKEN_BLOCKLIST:
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


# -- 8-K Item 1.01 (license deals) + Item 8.01 (IP litigation) --------


@dataclass(frozen=True)
class LicenseDeal:
    """Parsed 8-K Item 1.01 patent/IP license event."""
    deal_type: str        # 'license' | 'cross_license' | 'royalty' | 'assignment'
    counterparty: str     # Other party to the deal (best-effort extract)
    summary: str          # Truncated sentence describing the deal (<=300 chars)


@dataclass(frozen=True)
class LitigationEvent:
    """Parsed 8-K Item 8.01 IP litigation event."""
    event_kind: str       # 'verdict' | 'settlement' | 'injunction' | 'dismissal' | 'judgment' | 'unknown'
    direction: str        # 'against_company' | 'in_favor_of_company' | 'unknown'
    summary: str          # Truncated sentence (<=300 chars)


_ITEM_101_RE = re.compile(r"Item\s*1\.01", flags=re.IGNORECASE)
_ITEM_801_RE = re.compile(r"Item\s*8\.01", flags=re.IGNORECASE)

# Keyword tables for IP detection (Item 1.01)
_LICENSE_KEYWORDS = (
    "patent license", "royalty", "intellectual property",
    "cross-license", "cross license", "ip license",
    "license agreement", "licensing agreement", "patent agreement",
    "ip assignment", "patent assignment",
)

# Keyword tables for IP litigation (Item 8.01)
_LITIGATION_VERDICT_KEYWORDS = (
    "verdict", "judgment", "ruling", "decision",
    "infringement", "settlement", "injunction",
    "dismissed", "dismissal", "patent suit", "patent lawsuit",
)

_DIRECTION_AGAINST = (
    "against the company", "against our company", "found liable",
    "ordered to pay", "damages of", "found infringing",
    "must cease", "adverse ruling", "company liable",
)

_DIRECTION_FAVOR = (
    "in favor of the company", "in our favor", "dismissed against",
    "summary judgment in favor", "company prevailed", "company won",
    "patent upheld",
)


def _strip_item_header(section: str, item_re: re.Pattern[str]) -> str:
    """Drop the 'Item N.NN ...' title block.

    Generic version of _strip_item_502_header for any Item number. Prefers
    cutting at the first blank line after the header; falls back to cutting
    after the first period that follows the Item tag.
    """
    blank = re.search(r"\n\s*\n", section)
    if blank:
        return section[blank.end():]
    m = re.search(item_re.pattern + r"[^.]*\.", section, flags=re.IGNORECASE)
    if m:
        return section[m.end():]
    return section


def _slice_item_section(text: str, item_re: re.Pattern[str]) -> str | None:
    """Find Item N.NN section: from the Item tag to the next Item M.MM or EOF.

    Returns the section text with header stripped, or None if the Item tag
    isn't present.
    """
    if not text:
        return None
    m = item_re.search(text)
    if not m:
        return None
    start = m.start()
    next_item = re.search(r"Item\s*\d+\.\d+", text[start + 1:], flags=re.IGNORECASE)
    end = (start + 1 + next_item.start()) if next_item else len(text)
    section = text[start:end]
    return _strip_item_header(section, item_re)


def _classify_deal_type(sentence_low: str) -> str | None:
    """Classify license deal type from a lowercased sentence.

    Returns one of 'cross_license', 'license', 'royalty', 'assignment', or
    None if no IP keyword is present in the sentence.
    """
    if "cross-license" in sentence_low or "cross license" in sentence_low:
        return "cross_license"
    if "ip assignment" in sentence_low or "patent assignment" in sentence_low:
        return "assignment"
    if (
        "patent license" in sentence_low
        or "ip license" in sentence_low
        or "license agreement" in sentence_low
        or "licensing agreement" in sentence_low
        or "patent agreement" in sentence_low
        or "intellectual property" in sentence_low
    ):
        return "license"
    if "royalty" in sentence_low:
        return "royalty"
    return None


def _extract_counterparty(sentence: str) -> str:
    """Best-effort extraction of the other party to a license deal.

    Looks for capitalized entity names following 'with' / 'between' / 'and'
    that resemble a company (multi-word capitalized run, optionally followed
    by an entity suffix like Inc., Corp., Holdings, LLC, etc.).
    """
    if not sentence:
        return ""
    # Match patterns like "with Foo Bar Holdings Inc." or "with Foo Corp."
    pattern = re.compile(
        r"\b(?:with|between|and|from|to)\s+"
        r"([A-Z][A-Za-z0-9&'\-]+(?:\s+[A-Z][A-Za-z0-9&'\-]+){0,4})",
    )
    for m in pattern.finditer(sentence):
        cand = m.group(1).strip().rstrip(".,;:")
        first_tok = _clean_token(cand.split()[0])
        # Skip obviously non-entity leads.
        if first_tok in {"the", "company", "our", "its"}:
            continue
        # Skip pure role/boilerplate words.
        if first_tok in _NAME_TOKEN_BLOCKLIST and first_tok not in _COMPANY_SUFFIX_WORDS:
            # 'with Counterparty Holdings' → first token 'counterparty' is fine.
            # But 'with Item' / 'with January' should be skipped.
            if first_tok in _CALENDAR_WORDS or first_tok in _DOC_BOILERPLATE_WORDS:
                continue
        return cand
    return ""


def parse_8k_item_101_license_deals(text: str) -> list[LicenseDeal]:
    """Parse 8-K text for IP/patent license deals in Item 1.01.

    Detects sentences mentioning: 'patent license', 'royalty', 'intellectual
    property', 'cross-license', 'IP assignment', 'license agreement'.
    Returns empty list if no Item 1.01 content or no IP keywords found.
    """
    body = _slice_item_section(text, _ITEM_101_RE)
    if body is None:
        return []

    out: list[LicenseDeal] = []
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        s = sentence.strip()
        if len(s) < 20:
            continue
        low = s.lower()
        # Require at least one IP keyword in the sentence.
        if not any(kw in low for kw in _LICENSE_KEYWORDS):
            continue
        deal_type = _classify_deal_type(low)
        if deal_type is None:
            continue
        counterparty = _extract_counterparty(s)
        out.append(LicenseDeal(
            deal_type=deal_type,
            counterparty=counterparty,
            summary=s[:300],
        ))
    return out


def _classify_event_kind(sentence_low: str) -> str:
    """Map a litigation sentence to an event_kind.

    Specific kinds win over generic ones (e.g. 'settlement' over 'judgment'
    when both appear).
    """
    if "settlement" in sentence_low or "settled" in sentence_low:
        return "settlement"
    if "injunction" in sentence_low:
        return "injunction"
    if "dismissed" in sentence_low or "dismissal" in sentence_low:
        return "dismissal"
    if "verdict" in sentence_low:
        return "verdict"
    if "judgment" in sentence_low:
        return "judgment"
    if "ruling" in sentence_low or "decision" in sentence_low:
        return "verdict"
    return "unknown"


def _classify_direction(sentence_low: str) -> str:
    """Classify litigation direction (against/in_favor/unknown).

    If both 'against' and 'in favor' signals fire, return 'unknown' to avoid
    a misleading classification.
    """
    has_against = any(p in sentence_low for p in _DIRECTION_AGAINST)
    has_favor = any(p in sentence_low for p in _DIRECTION_FAVOR)
    if has_against and has_favor:
        return "unknown"
    if has_against:
        return "against_company"
    if has_favor:
        return "in_favor_of_company"
    return "unknown"


def parse_8k_item_801_litigation_events(text: str) -> list[LitigationEvent]:
    """Parse 8-K text for IP litigation outcomes in Item 8.01.

    Detects: 'verdict', 'judgment', 'settlement', 'injunction', 'dismissed',
    'patent infringement'. Distinguishes outcomes against company vs in favor.
    Returns empty list if no Item 8.01 content.
    """
    body = _slice_item_section(text, _ITEM_801_RE)
    if body is None:
        return []

    out: list[LitigationEvent] = []
    seen_kinds: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        s = sentence.strip()
        if len(s) < 20:
            continue
        low = s.lower()
        # Require at least one litigation keyword.
        if not any(kw in low for kw in _LITIGATION_VERDICT_KEYWORDS):
            continue
        # Require IP context — either 'patent', 'infringement', 'intellectual
        # property', or a generic 'lawsuit/suit/litigation' alongside a clear
        # IP signal. We use a broad filter so we don't lose obvious cases.
        if not (
            "patent" in low
            or "infringement" in low
            or "intellectual property" in low
            or "ip " in low
            or "trademark" in low
            or "copyright" in low
        ):
            continue
        kind = _classify_event_kind(low)
        direction = _classify_direction(low)
        # Deduplicate by (kind, direction) so a multi-sentence narrative
        # describing the same outcome doesn't produce repeats.
        key = f"{kind}|{direction}"
        if key in seen_kinds:
            continue
        seen_kinds.add(key)
        out.append(LitigationEvent(
            event_kind=kind,
            direction=direction,
            summary=s[:300],
        ))
    return out
