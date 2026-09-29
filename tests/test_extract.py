import json
from pathlib import Path

import pytest

from pipeline.extract import color_kind, cross_checks, extract_paper
from pipeline.topics import tag

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "data" / "intake_manifest.json").read_text())


def source(date: str, slot: str) -> dict:
    return next(s for s in MANIFEST["sources"] if s["date"] == date and s["time_slot"] == slot)


@pytest.fixture(scope="module")
def paper_0909():
    recs, problems = extract_paper(ROOT, source("09.09.2024", "0900"), images=False)
    assert problems == []
    return {(r["section"], r["q_no"]): r for r in recs}


def test_only_quant_and_reasoning_25_each(paper_0909):
    sections = [s for s, _ in paper_0909]
    assert sections.count("QUANT") == 25 and sections.count("REASONING") == 25
    assert len(sections) == 50


def test_golden_reasoning_q1(paper_0909):
    r = paper_0909[("REASONING", 1)]
    assert r["ssc_question_id"] == "630680411715"
    assert "4515 × 5 – 431 ÷ 3 + 821 = ?" in r["stem_text"]
    assert not r["stem_text"].startswith("Q.")
    assert [o["text"] for o in r["options"]] == ["1335", "1775", "1575", "1375"]
    assert r["answer_text_layer"] == r["answer_page_image"] == r["official_answer"] == "D"
    assert r["key_status"] == "UNVERIFIED"
    assert r["option_ids"]["A"] == "6306801605695"
    assert r["status"] == "EXTRACTED"


def test_figure_question_keeps_image(paper_0909):
    dice = paper_0909[("REASONING", 3)]
    assert dice["official_answer"] == "B"
    assert dice["stem_image"] and dice["has_visual"]
    assert not dice["stem_text_complete"]
    mirror = paper_0909[("REASONING", 10)]
    assert all(o["image"] and not o["text"] for o in mirror["options"])


def test_no_candidate_data(paper_0909):
    blob = json.dumps(list(paper_0909.values()))
    for word in ("Chosen Option", "Status :", "Roll Number", "Candidate Name", "Venue"):
        assert word not in blob


def test_math_stem_without_text_layer():
    recs, _ = extract_paper(ROOT, source("10.09.2024", "0900"), images=False)
    q1 = next(r for r in recs if r["section"] == "QUANT" and r["q_no"] == 1)
    assert q1["stem_text"] == ""
    assert q1["stem_image"]
    assert q1["official_answer"] == "B"
    assert [o["text"] for o in q1["options"]] == ["15%", "20%", "30%", "40%"]


def test_clipped_question_id_goes_to_review():
    recs, _ = extract_paper(ROOT, source("26.09.2024", "1600"), images=False)
    q = next(r for r in recs if r["section"] == "QUANT" and r["q_no"] == 15)
    assert q["status"] == "REVIEW"
    assert any("clipped" in x for x in q["review_reasons"])


def test_color_kind():
    assert color_kind(0x40C64B) == "green"
    assert color_kind(0xF61818) == "red"
    assert color_kind(0x252525) == "other"


def _rec(**kw):
    base = {"paper_id": "p", "section": "QUANT", "q_no": 1, "ssc_question_id": "1", "official_answer": "A",
            "review_reasons": [], "status": "EXTRACTED"}
    base.update(kw)
    return base


def test_cross_checks_flag_short_section_and_conflicting_keys():
    recs = [_rec(q_no=i, ssc_question_id=str(i)) for i in range(1, 25)]
    other = _rec(paper_id="q", ssc_question_id="1", official_answer="B")
    other_section = [_rec(paper_id="q", q_no=i, ssc_question_id=f"q{i}") for i in range(2, 26)]
    cross_checks(recs + [other] + other_section)
    assert all("section has 24 questions, expected 25" in r["review_reasons"] for r in recs)
    assert any("keyed differently" in x for x in recs[0]["review_reasons"])
    assert any("keyed differently" in x for x in other["review_reasons"])


@pytest.mark.parametrize("section, stem, topic", [
    ("QUANT", "A shopkeeper marks an article 40% above cost and allows a discount of 10%.", "Profit & Loss"),
    ("QUANT", "Find the mean proportional of 36 and 100.", "Ratio & Proportion"),
    ("REASONING", "In a certain code language, 'NAME' is written as 'FNBO'.", "Coding-Decoding"),
    ("REASONING", "Which letter-cluster will replace the question mark (?) to complete the given series?", "Series"),
    ("REASONING", "Select the number-pair that DOES\nNOT belong to this group.", "Classification"),
])
def test_provisional_tags(section, stem, topic):
    rec = {"section": section, "stem_text": stem, "options": [], "has_visual": False}
    assert tag(rec)["topic"] == topic


def test_image_only_stem_is_not_guessed():
    rec = {"section": "QUANT", "stem_text": "", "options": [{"text": "15%"}], "has_visual": True}
    assert tag(rec)["topic"] is None
