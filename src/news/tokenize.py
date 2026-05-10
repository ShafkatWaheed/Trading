"""News tokenizer — extract keyword matches, recognized entities, and negation.

Pipeline (pure functions, no I/O after the loaded keyword set is passed in):

    text → normalised → tokens
                       ├─ generate 1-4 grams
                       ├─ match against the keyword dictionary (longest-first)
                       ├─ recognise stock symbols (NER against universe)
                       ├─ recognise country names (small fixed dict)
                       └─ detect negation windows (5-token lookback)
    → list of TokenMatch

A `TokenMatch` is a structured hit: keyword (or symbol/country), match span,
type ('keyword' | 'symbol' | 'country'), and `negated` flag indicating that
the match falls inside a negation phrase like "no AI demand", "tariffs
cancelled", "drug rejection averted".

Loaders are passed in by the caller — this module never reads the DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# How many tokens to look back when checking negation context.
NEGATION_WINDOW = 5

# Negation triggers — lowercase tokens. If any appears in the preceding
# `NEGATION_WINDOW` tokens, the match is flagged `negated=True`.
NEGATION_TRIGGERS: frozenset[str] = frozenset({
    "no", "not", "never", "without",
    "cancelled", "canceled", "averted", "avoided",
    "delayed", "rejected", "denied", "blocked",
    "halted", "suspended", "withdrawn", "scrapped",
    "abandoned", "paused",
})

# Country / region recognition — kept tiny and curated. Used by aggregate.py
# to apply geographic co-occurrence boosts.
COUNTRIES: frozenset[str] = frozenset({
    "us", "usa", "america", "american",
    "china", "chinese", "beijing",
    "russia", "russian", "moscow",
    "ukraine", "ukrainian", "kyiv",
    "iran", "iranian", "tehran",
    "iraq", "iraqi", "baghdad",
    "israel", "israeli", "tel aviv",
    "saudi", "saudi arabia", "riyadh",
    "japan", "japanese", "tokyo",
    "korea", "korean", "seoul",
    "taiwan", "taiwanese", "taipei",
    "germany", "german", "berlin",
    "france", "french", "paris",
    "uk", "britain", "british", "london",
    "india", "indian", "mumbai",
    "mexico", "mexican",
    "canada", "canadian", "toronto",
    "europe", "european", "eu",
    "asia", "asian",
})

# Pre-tokenize regex: keep alphabetic tokens (with internal hyphens / apostrophes
# AND an optional .XX suffix for tickers like "RY.TO" / "BRK.A") OR pure numbers.
# The optional dotted suffix lets us preserve Canadian / TSX tickers as one token.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*(?:\.[A-Za-z]{1,3})?|\d+")
# Symbol candidate: 1-5 uppercase letters, possibly with one hyphen or dot
# (e.g. "BRK-B", "RY.TO"). Detected against the original-case input.
_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9]{0,4}(?:[-.][A-Z]{1,3})?\b")


def _basic_stem(word: str) -> str:
    """Strip simple plural / past-tense suffixes so 'missiles' matches 'missile'.

    Conservative — only handles the common cases. Heuristics:
      * 'ies' → 'y'      (companies → company)
      * 'es'  → '' or 's'  depending on what precedes (taxes → tax, rates → rate)
      * 's'   → ''       (tariffs → tariff)  unless a preserved suffix
      * 'ed'  → ''       (cancelled → cancell — imperfect but rarely used as keyword)
    """
    if len(word) <= 3:
        return word
    # Don't stem words that end in a non-plural -ss / -us / -is / -as / -os.
    if word.endswith(("ss", "us", "is", "as", "os")):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"               # companies → company
    if word.endswith("es"):
        # "taxes", "boxes", "dishes", "wishes" lose 'es'.
        # "rates", "missiles", "rules"      lose only 's'.
        if word[-3] in ("s", "x", "z", "h"):
            return word[:-2]
        return word[:-1]                     # missiles → missile, rates → rate
    if word.endswith("ed") and len(word) > 4:
        return word[:-2]                     # not perfect, but rarely a keyword
    if word.endswith("s"):
        return word[:-1]                     # tariffs → tariff, drones → drone
    return word


@dataclass(frozen=True)
class TokenMatch:
    """A single recognized item in the news text.

    Fields:
        text       — the matched n-gram or symbol, lowercased for keyword/country, original case for symbol.
        kind       — 'keyword' | 'symbol' | 'country'.
        token_span — (start_token_idx, end_token_idx_exclusive) into the lowercased token list.
        negated    — True if a negation trigger appears in the 5-token window before this match.
    """
    text: str
    kind: str
    token_span: tuple[int, int]
    negated: bool


# ── core helpers ─────────────────────────────────────────────────


def normalise(text: str) -> str:
    """Strip control chars, collapse whitespace, keep case (caller decides when to lower)."""
    return re.sub(r"\s+", " ", text.replace("—", "-").replace("–", "-")).strip()


def tokenize(text: str) -> list[str]:
    """Return lowercase tokens. Punctuation dropped; numbers kept."""
    return [tok.lower() for tok in _TOKEN_RE.findall(normalise(text))]


def ngrams(tokens: list[str], n_max: int = 4) -> list[tuple[str, int, int]]:
    """Yield (joined_phrase, start_idx, end_idx_exclusive) for n=1..n_max.

    Longest n first so the matcher can prefer specific phrases over fragments.
    """
    out: list[tuple[str, int, int]] = []
    for n in range(min(n_max, len(tokens)), 0, -1):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i + n])
            out.append((phrase, i, i + n))
    return out


def _is_negated(span_start: int, span_end: int, tokens: list[str]) -> bool:
    """Negation triggers can appear either BEFORE the subject ('no AI demand')
    or AFTER it ('tariff escalation averted'). Check both directions."""
    # Backward window
    back_start = max(0, span_start - NEGATION_WINDOW)
    if any(tokens[i] in NEGATION_TRIGGERS for i in range(back_start, span_start)):
        return True
    # Forward window — checks for post-positioned triggers like 'averted', 'cancelled'.
    fwd_end = min(len(tokens), span_end + NEGATION_WINDOW)
    return any(tokens[i] in NEGATION_TRIGGERS for i in range(span_end, fwd_end))


# ── NER: symbols against the universe ───────────────────────────


def find_symbols(text: str, universe: Iterable[str]) -> list[tuple[str, int, int]]:
    """Scan ORIGINAL-case text for ticker symbols present in the universe.

    Returns (symbol, start_token_idx, end_token_idx) where the indices are
    into the lowercased token list (so callers can join with negation).
    """
    universe_set = {s.upper() for s in universe}
    tokens_lc = tokenize(text)

    out: list[tuple[str, int, int]] = []
    for m in _SYMBOL_RE.finditer(normalise(text)):
        sym = m.group(0)
        if sym not in universe_set:
            continue
        # Locate this symbol in the lowercased token stream by linear scan
        # (the regex match position is in characters; we need a token index).
        # Simple approach: find the i'th occurrence of sym.lower() in tokens_lc.
        target = sym.lower()
        # Reconstruct position: the symbol is whitespace-separated in normalise(text),
        # so its lowercased form appears as a token (possibly split if it has dots).
        if target in tokens_lc:
            idx = tokens_lc.index(target)
            out.append((sym, idx, idx + 1))
        else:
            # Symbols like "BRK-B" survive tokenization as one token because
            # _TOKEN_RE allows hyphens. Symbols like "RY.TO" also survive
            # because we lower-cased "ry.to" — match it.
            for i, tok in enumerate(tokens_lc):
                if tok.upper() == sym:
                    out.append((sym, i, i + 1))
                    break
    # Drop duplicates that would occur if the same symbol appears twice; we
    # only need one match per occurrence anyway, so de-dupe by (sym, idx).
    seen: set[tuple[str, int]] = set()
    deduped: list[tuple[str, int, int]] = []
    for sym, start, end in out:
        key = (sym, start)
        if key not in seen:
            seen.add(key)
            deduped.append((sym, start, end))
    return deduped


# ── public surface ──────────────────────────────────────────────


def extract_matches(
    text: str,
    *,
    keywords: Iterable[str],
    universe: Iterable[str] | None = None,
    longest_first: bool = True,
) -> list[TokenMatch]:
    """Return all keyword / symbol / country matches in `text`.

    `keywords` is the set of keyword phrases to match (lowercased).
    `universe` is the set of valid stock symbols for NER (uppercased).
    `longest_first=True` ensures that "data center" matches before "data"
    AND "center" alone can also match if it's a separate keyword.

    Same span MAY produce multiple matches (e.g. "oil refinery" matches both
    "oil" and "oil refinery") — the aggregator decides how to merge.
    """
    keyword_set = {k.lower() for k in keywords}
    tokens = tokenize(text)
    # For matching, also build a stemmed token list so plurals/past-tense work.
    stems = [_basic_stem(t) for t in tokens]
    matches: list[TokenMatch] = []

    def _build_phrases(tokens_view: list[str]) -> list[tuple[str, int, int]]:
        return ngrams(tokens_view)

    seen_spans: set[tuple[str, int, int]] = set()

    # Keyword n-grams: try literal phrase first, then stemmed phrase.
    for phrase_view in (tokens, stems):
        for phrase, start, end in _build_phrases(phrase_view):
            if phrase in keyword_set:
                # Use the literal phrase from the original tokens for the match text
                # (so logs read naturally even when the match was via stemming).
                literal = " ".join(tokens[start:end])
                key = (phrase, start, end)
                if key in seen_spans:
                    continue
                seen_spans.add(key)
                matches.append(TokenMatch(
                    text=phrase,                    # canonical (stemmed) form
                    kind="keyword",
                    token_span=(start, end),
                    negated=_is_negated(start, end, tokens),
                ))

    # Country names (1-2 grams)
    for phrase, start, end in ngrams(tokens, n_max=2):
        if phrase in COUNTRIES:
            matches.append(TokenMatch(
                text=phrase,
                kind="country",
                token_span=(start, end),
                negated=_is_negated(start, end, tokens),
            ))

    # Stock symbols (case-sensitive scan of original text)
    if universe:
        for sym, start, end in find_symbols(text, universe):
            matches.append(TokenMatch(
                text=sym,
                kind="symbol",
                token_span=(start, end),
                negated=_is_negated(start, end, tokens),
            ))

    if not longest_first:
        return matches
    return sorted(matches, key=lambda m: (-(m.token_span[1] - m.token_span[0]), m.token_span[0]))
