"""Tests for entity-alias name normalization (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import normalize_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Apple Inc.", "apple"),
        ("APPLE INC", "apple"),
        ("Apple, Inc.", "apple"),
        ("Microsoft Corporation", "microsoft"),
        ("Berkshire Hathaway Inc.", "berkshire hathaway"),
        ("JPMorgan Chase & Co.", "jpmorgan chase"),
        ("Alphabet Inc. Class A", "alphabet class a"),
        ("Tesla, Inc.", "tesla"),
        ("Lockheed Martin Corp", "lockheed martin"),
        ("Beats Electronics, LLC", "beats electronics"),
        ("3M Company", "3m"),
        ("AT&T Inc.", "at&t"),
        ("  whitespace  test  ", "whitespace test"),
    ],
)
def test_normalize_strips_suffixes_and_lowercases(raw: str, expected: str):
    assert normalize_name(raw) == expected


def test_normalize_handles_empty_string():
    assert normalize_name("") == ""


def test_normalize_handles_only_suffix():
    # Edge case: a string that's only suffix words. Don't blow up.
    assert normalize_name("Inc.") == ""


def test_normalize_is_idempotent():
    assert normalize_name(normalize_name("Apple Inc.")) == "apple"


def test_normalize_preserves_internal_ampersand_between_words():
    """Mid-string '& word' must NOT be eaten by suffix-stripping cleanup."""
    assert normalize_name("Procter & Gamble Co") == "procter & gamble"
    assert normalize_name("Johnson & Johnson") == "johnson & johnson"
    assert normalize_name("AT&T Inc.") == "at&t"   # regression: embedded must still pass
