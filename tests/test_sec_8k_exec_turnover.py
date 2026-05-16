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
