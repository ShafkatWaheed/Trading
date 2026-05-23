"""Tests for SEC 8-K Item 5.02 (exec departure/appointment) parser."""
from __future__ import annotations

from src.utils.sec_8k_parser import parse_8k_item_502, ExecChange


SAMPLE_8K_DEPARTURE = """
Item 5.02 Departure of Directors or Certain Officers; Election of Directors;
Appointment of Certain Officers; Compensatory Arrangements of Certain Officers

On April 1, 2026, Jane Smith notified the Board of Directors of XYZ Corporation
that she will resign from her position as Chief Financial Officer of the
Company, effective May 15, 2026. Ms. Smith's resignation is to pursue
other opportunities and is not the result of any disagreement with the Company.
"""

SAMPLE_8K_APPOINTMENT = """
Item 5.02 Departure of Directors or Certain Officers...

On May 1, 2026, the Board of Directors of XYZ Corporation appointed John Doe
as the Company's new Chief Executive Officer, effective immediately,
to succeed Mary Johnson, who will continue to serve as a director.
"""


def test_parse_8k_item_502_detects_departure():
    out = parse_8k_item_502(SAMPLE_8K_DEPARTURE)
    assert any(c.event_type == "departure" for c in out)
    dep = [c for c in out if c.event_type == "departure"][0]
    assert "Smith" in dep.person_name
    assert "Chief Financial Officer" in dep.role or "CFO" in dep.role


def test_parse_8k_item_502_detects_appointment():
    out = parse_8k_item_502(SAMPLE_8K_APPOINTMENT)
    assert any(c.event_type == "appointment" for c in out)
    app = [c for c in out if c.event_type == "appointment"][0]
    assert "Doe" in app.person_name


def test_parse_8k_item_502_empty_returns_empty_list():
    assert parse_8k_item_502("") == []


def test_parse_8k_item_502_non_502_content_returns_empty():
    junk = "Item 7.01 Regulation FD Disclosure. We had a good quarter."
    assert parse_8k_item_502(junk) == []


# -- Regression tests for production false positives -----------------


def test_parse_8k_item_502_rejects_font_name_times_new():
    """Real bug: 'Times New' (font name) leaked from PDF/HTML metadata."""
    # Simulates what we saw in the wild - a stray font reference in the 502 section
    txt = """Item 5.02 Departure of Directors

On April 20, 2026, the Board accepted the resignation of one Director,
font-family: Times New Roman, serif; effective immediately.
"""
    out = parse_8k_item_502(txt)
    # Even if a departure is detected, the person_name must NOT be "Times New"
    assert all("Times" not in c.person_name and "Roman" not in c.person_name for c in out)


def test_parse_8k_item_502_rejects_company_name_as_person():
    """Real bug: 'Apple Inc' (registrant's own company name) detected as a person."""
    txt = """Item 5.02 Departure of Directors

On January 2, 2026, Apple Inc. announced the departure of a Director,
effective immediately. The resignation was made for personal reasons.
"""
    out = parse_8k_item_502(txt)
    assert all("Apple Inc" not in c.person_name and c.person_name != "Apple" for c in out)


def test_parse_8k_item_502_requires_first_and_last_name():
    """Don't match single-word 'names' - must be at least First + Last."""
    txt = """Item 5.02 Departure of Directors

On May 1, 2026, the resignation was accepted, effective immediately as Chief Financial Officer.
"""
    out = parse_8k_item_502(txt)
    # No real name present - parser should yield nothing
    assert out == []


def test_parse_8k_item_502_keeps_real_name_extraction_working():
    """Regression: don't break the case where there IS a real name."""
    txt = """Item 5.02 Departure of Directors

On April 1, 2026, Jane Smith notified the Board that she will resign
from her position as Chief Financial Officer effective May 15, 2026.
"""
    out = parse_8k_item_502(txt)
    departures = [c for c in out if c.event_type == "departure"]
    assert len(departures) == 1
    assert "Smith" in departures[0].person_name
    assert "Jane" in departures[0].person_name
