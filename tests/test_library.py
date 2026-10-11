import copy

from pipeline.library import check_entry, verify_entry

APPROVED = {"percentage.successive-change": {"topic": "Percentage", "subtopic": "Successive change",
                                             "visual": False, "seen": True}}
ANSWERS = {"2024-09-09_0900_Q01": "B"}
ENTRY = {
    "id": "percentage.successive-change", "topic": "Percentage", "subtopic": "Successive change",
    "name": "Successive change", "statement": "(1+a)(1+b)-1", "conditions": [],
    "derivation": ["$x(1+a)(1+b)$"], "visual_proof": None, "shortcut": None,
    "worked_example": {"question_key": "2024-09-09_0900_Q01", "answer": "B", "steps": ["1.4 x 0.9"]},
    "common_traps": ["adding the rates"], "related_ids": [], "diagram": None,
    "verification": {"kind": "identity", "code": "import sympy as s\na,b=s.symbols('a b')\n"
                     "assert s.simplify((1+a)*(1+b)-1-(a+b+a*b))==0", "reason": None},
}


def test_valid_entry_passes_check_and_verify():
    assert check_entry(ENTRY, APPROVED, ANSWERS) == []
    assert verify_entry(ENTRY)["status"] == "PASSED"


def test_worked_example_must_match_verified_answer():
    e = copy.deepcopy(ENTRY)
    e["worked_example"]["answer"] = "C"
    assert any("verified" in x for x in check_entry(e, APPROVED, ANSWERS))


def test_unresolved_token_fails():
    e = copy.deepcopy(ENTRY)
    e["shortcut"] = "see [[f:percentage.nope]]"
    assert any("unresolved token" in x for x in check_entry(e, APPROVED, ANSWERS))


def test_shortcut_needs_1000_cases():
    e = copy.deepcopy(ENTRY)
    e["verification"] = {"kind": "shortcut", "code": "print('CASES=10')", "reason": None}
    assert verify_entry(e)["status"] == "FAILED"
    e["verification"]["code"] = "print('CASES=1000')"
    assert verify_entry(e)["status"] == "PASSED"


def test_conditions_need_boundary_check():
    e = copy.deepcopy(ENTRY)
    e["conditions"] = ["a > -1"]
    assert "BOUNDARY_OK" in verify_entry(e)["note"]


def test_manual_goes_to_review():
    e = copy.deepcopy(ENTRY)
    e["verification"] = {"kind": "manual", "code": None, "reason": "judged on an image"}
    assert check_entry(e, APPROVED, ANSWERS) == []
    assert verify_entry(e)["status"] == "NEEDS_REVIEW"


def test_committed_library_passes_check():
    from pipeline.library import ROOT, check
    assert check(ROOT) == {}
