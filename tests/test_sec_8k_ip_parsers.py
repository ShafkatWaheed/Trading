"""Tests for 8-K Item 1.01 (license deals) and Item 8.01 (IP litigation) parsers."""
from src.utils.sec_8k_parser import (
    LicenseDeal,
    LitigationEvent,
    parse_8k_item_101_license_deals,
    parse_8k_item_801_litigation_events,
)


SAMPLE_101_LICENSE = """
Item 1.01 Entry into a Material Definitive Agreement.

On March 12, 2026, the Company entered into a non-exclusive patent license
agreement with Counterparty Holdings Inc. under which the Company will pay
a royalty of 4% on net sales. The license covers the Company's use of
certain semiconductor manufacturing patents owned by Counterparty Holdings.
"""

SAMPLE_101_NONIP = """
Item 1.01 Entry into a Material Definitive Agreement.

On March 12, 2026, the Company entered into a $500M revolving credit
facility with a syndicate of banks led by JPMorgan Chase Bank N.A.
"""

SAMPLE_801_VERDICT_AGAINST = """
Item 8.01 Other Events.

On April 15, 2026, the U.S. District Court for the Eastern District of
Texas issued a verdict against the Company in a patent infringement
lawsuit brought by Plaintiff Co. The jury found the Company liable and
ordered damages of $200 million.
"""

SAMPLE_801_SETTLEMENT = """
Item 8.01 Other Events.

On April 22, 2026, the Company and Adversary Corp. reached a settlement
resolving all pending patent infringement litigation between them. Under
the terms of the settlement, the Company will pay an undisclosed sum.
"""


def test_parse_101_detects_patent_license():
    out = parse_8k_item_101_license_deals(SAMPLE_101_LICENSE)
    assert len(out) >= 1
    assert any(d.deal_type in {"license", "royalty"} for d in out)
    assert any("Counterparty" in d.counterparty or "Counterparty" in d.summary for d in out)


def test_parse_101_skips_non_ip_agreements():
    out = parse_8k_item_101_license_deals(SAMPLE_101_NONIP)
    assert out == []  # credit facility is not an IP deal


def test_parse_801_detects_verdict_against():
    out = parse_8k_item_801_litigation_events(SAMPLE_801_VERDICT_AGAINST)
    assert len(out) >= 1
    e = out[0]
    assert e.event_kind in {"verdict", "judgment"}
    assert e.direction == "against_company"


def test_parse_801_detects_settlement():
    out = parse_8k_item_801_litigation_events(SAMPLE_801_SETTLEMENT)
    assert any(e.event_kind == "settlement" for e in out)


def test_parse_101_empty_returns_empty():
    assert parse_8k_item_101_license_deals("") == []
    assert parse_8k_item_101_license_deals("Item 5.02 some other item") == []


def test_parse_801_empty_returns_empty():
    assert parse_8k_item_801_litigation_events("") == []
    assert parse_8k_item_801_litigation_events("Item 5.02 unrelated") == []
