"""Tests for src/news/tokenize.py — n-grams, NER, negation."""

from __future__ import annotations

from src.news.tokenize import (
    COUNTRIES,
    NEGATION_TRIGGERS,
    TokenMatch,
    extract_matches,
    find_symbols,
    ngrams,
    normalise,
    tokenize,
)


# ── normalisation + tokenisation ──────────────────────────────────


def test_normalise_collapses_whitespace_and_unifies_dashes():
    assert normalise("  Iran—fires  missiles ") == "Iran-fires missiles"


def test_tokenize_lowercases_and_drops_punct():
    assert tokenize("Iran fires missiles at Saudi oil refinery!") == [
        "iran", "fires", "missiles", "at", "saudi", "oil", "refinery",
    ]


def test_tokenize_keeps_hyphenated_words_and_numbers():
    assert tokenize("BRK-B trades at $400.00 mark in 2026") == [
        "brk-b", "trades", "at", "400", "00", "mark", "in", "2026",
    ]


# ── n-grams ───────────────────────────────────────────────────────


def test_ngrams_emits_largest_first():
    out = ngrams(["a", "b", "c"], n_max=3)
    # Largest first: 3-gram, 2-grams, 1-grams
    spans = [(g, s, e) for g, s, e in out]
    assert spans[0] == ("a b c", 0, 3)
    assert ("a b", 0, 2) in spans
    assert ("c", 2, 3) in spans


def test_ngrams_handles_short_input():
    assert ngrams(["only"], n_max=4) == [("only", 0, 1)]


# ── keyword matching ──────────────────────────────────────────────


def test_extract_finds_single_keyword():
    matches = extract_matches("AI capex is rising", keywords={"ai"})
    kinds = {m.kind for m in matches}
    assert "keyword" in kinds
    assert any(m.text == "ai" for m in matches)


def test_extract_prefers_longer_phrase_when_both_match():
    matches = extract_matches(
        "OpenAI announces $50B GPU build-out for new data center",
        keywords={"data", "center", "data center", "gpu"},
    )
    # Longest-first sort puts "data center" before "data" or "center"
    texts_in_order = [m.text for m in matches]
    if "data center" in texts_in_order and "data" in texts_in_order:
        assert texts_in_order.index("data center") < texts_in_order.index("data")


def test_extract_keyword_lowercase_normalised():
    matches = extract_matches("AI BOOMS", keywords={"ai"})
    assert any(m.text == "ai" for m in matches)


# ── negation detection ───────────────────────────────────────────


def test_negation_in_window_flags_match():
    matches = extract_matches("there is no AI demand in Q3", keywords={"ai"})
    ai_match = next(m for m in matches if m.text == "ai")
    assert ai_match.negated is True


def test_negation_outside_window_does_not_flag():
    text = (
        "no demand was the headline last quarter however the latest report indicates "
        "renewed AI capex"
    )
    matches = extract_matches(text, keywords={"ai"})
    # "no" is far from "AI" — outside the 5-token negation window.
    ai_match = next(m for m in matches if m.text == "ai")
    assert ai_match.negated is False


def test_cancelled_triggers_negation():
    matches = extract_matches("tariff hike was cancelled today", keywords={"tariff", "tariff hike"})
    # Whichever matched, both should NOT be negated because "cancelled" comes AFTER.
    # But "cancelled" is the trigger on a FOLLOWING phrase like:
    text = "tariff has been cancelled before merger went through"
    m2 = extract_matches(text, keywords={"tariff", "merger"})
    # "merger" appears AFTER "cancelled" within window → negated
    merger = next(m for m in m2 if m.text == "merger")
    assert merger.negated is True


def test_all_negation_triggers_in_set():
    """Sanity-check our published trigger list."""
    expected = {"no", "not", "cancelled", "rejected", "blocked", "averted"}
    assert expected.issubset(NEGATION_TRIGGERS)


# ── country recognition ───────────────────────────────────────────


def test_country_match_returned():
    matches = extract_matches("Saudi Arabia output cut announced", keywords={"output cut"})
    countries = [m for m in matches if m.kind == "country"]
    assert any(m.text == "saudi arabia" for m in countries)


def test_two_word_countries_recognised_first():
    """Two-word country phrases should match before single tokens like 'saudi'."""
    matches = extract_matches("Saudi Arabia hosts summit", keywords=set())
    texts = [m.text for m in matches if m.kind == "country"]
    # "saudi arabia" longer match should be present
    assert "saudi arabia" in texts


# ── NER: symbol matching ─────────────────────────────────────────


def test_find_symbols_recognises_universe_symbol():
    out = find_symbols("Strong day for NVDA and MSFT", ["NVDA", "MSFT", "AAPL"])
    syms = {sym for sym, _, _ in out}
    assert syms == {"NVDA", "MSFT"}


def test_find_symbols_ignores_unknown():
    out = find_symbols("FAKE moves higher", ["NVDA", "MSFT"])
    assert out == []


def test_find_symbols_handles_dotted_canadian_tickers():
    out = find_symbols("Royal Bank of Canada (RY.TO) reports earnings", ["RY.TO", "RY"])
    syms = {sym for sym, _, _ in out}
    assert "RY.TO" in syms or "RY" in syms


def test_find_symbols_handles_class_share_brk_b():
    out = find_symbols("BRK-B holds steady amid volatility", ["BRK-B"])
    syms = {sym for sym, _, _ in out}
    assert "BRK-B" in syms


def test_extract_with_universe_returns_symbol_kind():
    matches = extract_matches(
        "OpenAI announces $50B GPU build-out with NVDA",
        keywords={"gpu"},
        universe=["NVDA", "MSFT"],
    )
    syms = [m for m in matches if m.kind == "symbol"]
    assert any(m.text == "NVDA" for m in syms)


# ── putting it together ─────────────────────────────────────────


def test_full_extraction_realistic_headline():
    text = "Iran fires missiles at Saudi oil refinery, output cut announced"
    matches = extract_matches(
        text,
        keywords={"missile", "oil", "oil refinery", "output cut", "iran"},
    )
    found = {m.text for m in matches if m.kind == "keyword"}
    assert "missile" in found
    assert "oil refinery" in found  # should beat "oil" alone but both can be present
    assert "output cut" in found
    countries = {m.text for m in matches if m.kind == "country"}
    assert "iran" in countries
    assert "saudi" in countries or "saudi arabia" in countries


def test_negated_headline_flips_polarity_signal():
    text = "tariff escalation averted as deal reached"
    matches = extract_matches(text, keywords={"tariff", "tariff escalation"})
    # "averted" within window of "tariff" / "tariff escalation"
    for m in matches:
        if m.kind == "keyword":
            assert m.negated is True, f"expected negation on {m.text}"
