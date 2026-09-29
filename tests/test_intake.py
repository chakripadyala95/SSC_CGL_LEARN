from pathlib import Path

import pytest

from pipeline.intake import (
    SheetScan,
    original_first,
    parse_filename,
    scan,
    to_hhmm,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
SHEET = "SSC-CGL-Tier-1-Question-Paper-English_{}.pdf"


@pytest.mark.parametrize(
    "name, expected",
    [
        (SHEET.format("09.09.2024_9.00-AM-10.00-AM (1)"), ("09.09.2024", "0900")),
        (SHEET.format("18.09.2024_12.30-PM-01.30-PM"), ("18.09.2024", "1230")),
        (SHEET.format("26.09.2024_04.00-PM-05.00-PM"), ("26.09.2024", "1600")),
        ("SSC-CGL-T-I-Similar-Paper-Held-on-18-Sep-2025-S1-English.pdf", None),
    ],
)
def test_parse_filename(name, expected):
    assert parse_filename(name) == expected


def test_to_hhmm():
    assert to_hhmm("12", "30", "PM") == "1230"
    assert to_hhmm("12", "00", "AM") == "0000"
    assert to_hhmm("4", "00", "PM") == "1600"


def test_original_name_sorts_before_browser_copies():
    names = ["a (2).pdf", "a (1).pdf", "a.pdf"]
    assert sorted(map(Path, names), key=original_first)[0].name == "a.pdf"


def clean_scan() -> SheetScan:
    s = SheetScan(header=True, header_date="09.09.2024", header_hhmm="0900")
    s.qids = ["630680416361"] * 98 + ["63068082920", "6306801048036"]
    s.option_ids, s.statuses, s.chosen = 400, 100, 100
    s.sections = {sec: {"questions": 25, "qids": 25, "labels": 25}
                  for sec in ("REASONING", "GA", "QUANT", "ENGLISH")}
    return s


def test_validate_accepts_11_to_13_digit_ids():
    assert validate(clean_scan(), "09.09.2024", "0900") == []


def test_validate_rejects_header_mismatch_and_short_section():
    s = clean_scan()
    s.sections["QUANT"]["questions"] = 24
    reasons = validate(s, "09.09.2024", "1230")
    assert any("header" in r for r in reasons)
    assert any("QUANT has 24" in r for r in reasons)


def test_validate_counts_overflowed_question_toward_100():
    s = clean_scan()
    s.qids = s.qids[:99]
    s.statuses = s.chosen = 99
    s.sections["QUANT"]["qids"] = 24
    assert validate(s, "09.09.2024", "0900") == []


# Golden-file checks against real sheets in the repo root.
needs_pdfs = pytest.mark.skipif(not (ROOT / SHEET.format("12.09.2024_04.00-PM-05.00-PM")).exists(),
                                reason="source PDFs not present")


@needs_pdfs
def test_golden_sheet_with_missing_question_id_box():
    s = scan(ROOT / SHEET.format("12.09.2024_04.00-PM-05.00-PM"))
    assert len(s.qids) == 99
    assert s.sections["QUANT"] == {"questions": 25, "qids": 24, "labels": 24}
    assert all(v["questions"] == 25 for v in s.sections.values())
    assert validate(s, "12.09.2024", "1600") == []


@needs_pdfs
def test_golden_sheet_with_clipped_question_id():
    s = scan(ROOT / SHEET.format("26.09.2024_04.00-PM-05.00-PM"))
    assert s.clipped_qids == ["630680402"]
    assert validate(s, "26.09.2024", "1600") == []
