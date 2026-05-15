"""Tests for 10-K Exhibit 21 subsidiary parser (Wave 1)."""
from __future__ import annotations

from src.data.sec_10k_extractor import parse_exhibit_21_subsidiaries


SAMPLE_EXHIBIT_21 = """
Exhibit 21

List of Subsidiaries of the Registrant

Name                                     Jurisdiction of Incorporation
Apple Operations International           Ireland
Apple Operations Europe Limited          Ireland
Beats Electronics, LLC                   Delaware
Beddit Oy                                Finland
Braeburn Capital, Inc.                   Nevada
Filemaker, Inc.                          California
"""


SAMPLE_EXHIBIT_21_HTML = """
<HTML>
<BODY>
<H1>EXHIBIT 21</H1>
<P>SUBSIDIARIES OF THE REGISTRANT</P>
<TABLE>
<TR><TD>Subsidiary</TD><TD>State / Country</TD></TR>
<TR><TD>Lockheed Martin International, S.A.</TD><TD>Belgium</TD></TR>
<TR><TD>Sikorsky Aircraft Corporation</TD><TD>Delaware</TD></TR>
</TABLE>
</BODY>
</HTML>
"""


def test_parse_exhibit_21_plaintext_extracts_subsidiaries():
    subs = parse_exhibit_21_subsidiaries(SAMPLE_EXHIBIT_21)
    assert "Apple Operations International" in subs
    assert "Beats Electronics, LLC" in subs
    assert "Braeburn Capital, Inc." in subs
    # Header lines and the "List of Subsidiaries" preamble should NOT be subs
    assert "Name" not in subs
    assert "Jurisdiction of Incorporation" not in subs
    assert "List of Subsidiaries of the Registrant" not in subs


def test_parse_exhibit_21_html_extracts_subsidiaries():
    subs = parse_exhibit_21_subsidiaries(SAMPLE_EXHIBIT_21_HTML)
    assert "Lockheed Martin International, S.A." in subs
    assert "Sikorsky Aircraft Corporation" in subs


def test_parse_exhibit_21_empty_string_returns_empty_list():
    assert parse_exhibit_21_subsidiaries("") == []


def test_parse_exhibit_21_no_subs_section_returns_empty():
    junk = "This is just some text with no exhibit data."
    assert parse_exhibit_21_subsidiaries(junk) == []
