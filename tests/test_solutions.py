"""Crispness lint and check-code rules for Phase 3d solutions."""

import copy

import pytest

from pipeline.solutions import check, lint
from pipeline.solve import question_version

Q = {"ssc_question_id": "1", "stem_text": "An article is marked 40% above cost, then sold after successive discounts of "
     "10% and 5%. What is the profit percentage?", "stem_image": None,
     "options": [{"label": x, "text": t, "image": None} for x, t in zip("ABCD", ["25%", "19.7%", "20%", "18%"])]}
TAG = {"topic": "Profit & Loss", "subtopic": "Successive discount"}
ENTRIES = {"percentage.successive-change": {"name": "Successive change and constant growth"},
           "profit-loss.profit-percent": {"name": "Profit percent"}}
CODE = """from fractions import Fraction as F
opts = {"A": F(25), "B": F(197, 10), "C": F(20), "D": F(18)}
result = (F(14, 10) * F(9, 10) * F(95, 100) - 1) * 100
match = [k for k, v in opts.items() if v == result]
assert len(match) == 1
print(f"ANSWER={match[0]}")
"""
GOOD = {"key": "k", "question_version": question_version(Q), "answer": "B", "answer_value": "19.7%",
        "trick": "multiplying factors",
        "fastest": ["$1.4 \\times 0.9 \\times 0.95 = 1.197$ [[f:percentage.successive-change]]", "Profit **19.7%**"],
        "elimination": None, "elimination_is_fastest": False,
        "trap": "$40 - 10 - 5 = 25\\%$ → (a). Successive discounts don't add.", "diagram": None,
        "full": ["CP = 100, MP = 140.", "After 10%: 126; after 5%: 119.7.", "Profit 19.7%."],
        "formula_ids": ["percentage.successive-change"], "check_code": CODE, "writer": "w",
        "prompt_version": "solution_v1"}


def bad(**change):
    s = copy.deepcopy(GOOD)
    s.update(change)
    return lint(s, Q, TAG, "B", ENTRIES)


def test_style_example_passes():
    assert lint(GOOD, Q, TAG, "B", ENTRIES) == []
    assert check(GOOD, "B") == (True, "")


@pytest.mark.parametrize("change,message", [
    ({"fastest": ["a [[f:percentage.successive-change]]"] * 5}, "5 steps"),
    ({"fastest": ["word " * 61 + "[[f:percentage.successive-change]]"]}, "61 words"),
    ({"fastest": ["$1.4 \\times 0.9 \\times 0.95$", "**19.7%**"]}, "links no formula"),
    ({"fastest": ["Let us use [[f:nope.nope]]"]}, "unresolved token"),
    ({"full": ["Use profit percent here."]}, "without its token"),
    ({"full": ["Let us take CP = 100."]}, "banned phrase 'let us'"),
    ({"fastest": ["An article is marked 40% above cost, then sold after [[f:percentage.successive-change]]"]},
     "restates the question"),
    ({"trap": "Adding the discounts gives 25%."}, "name the wrong option"),
    ({"answer": "C"}, "not the verified answer"),
    ({"diagram": {"alt_text": "bars", "spec": {"type": "bar-model"}}}, "pure arithmetic"),
])
def test_lint_failures(change, message):
    assert any(message in e for e in bad(**change)), bad(**change)


def test_math_does_not_count_as_words():
    long_math = "$" + " + ".join(["1"] * 80) + "$ [[f:percentage.successive-change]]"
    assert bad(fastest=[long_math]) == []


def test_geometry_needs_a_diagram_and_figures_keep_the_crop():
    assert any("needs a diagram" in e for e in lint(GOOD, Q, {"topic": "Geometry", "subtopic": "Triangles"}, "B",
                                                   ENTRIES))
    s = dict(GOOD, diagram={"alt_text": "venn", "spec": {"type": "venn"}})
    assert any("original crop" in e for e in lint(s, Q, {"topic": "Figure-based", "subtopic": "x"}, "B", ENTRIES))


def test_check_code_must_print_the_verified_answer():
    assert check(dict(GOOD, check_code='print("ANSWER=C")'), "B")[0] is False
    assert check(dict(GOOD, check_code="assert False"), "B")[0] is False


def test_trap_may_be_left_out_but_not_blank():
    assert bad(trap=None) == []
    assert any("one line" in e for e in bad(trap="  "))
