from pipeline.solve import decide, run_check, validate


def v(answer, passed=None, valid=True):
    return {"solver_answer": answer, "check_passed": passed, "valid": valid}


def test_decide_confirmed_code_needs_a_passing_quant_check():
    assert decide("B", "QUANT", [v("B", True), v("B", False)]) == "KEY_CONFIRMED_CODE"
    assert decide("B", "QUANT", [v("B", False), v("B", None)]) == "KEY_CONFIRMED_DUAL"
    assert decide("B", "REASONING", [v("B", True), v("B", True)]) == "KEY_CONFIRMED_DUAL"


def test_decide_disputes_and_disagreements():
    assert decide("A", "QUANT", [v("B", True), v("B", True)]) == "KEY_DISPUTED"
    assert decide("A", "QUANT", [v("A"), v("B")]) == "SOLVERS_DISAGREE"
    assert decide("A", "QUANT", [v("A"), v("B"), v("C")]) == "UNRESOLVED"
    assert decide("A", "QUANT", [v("A"), v("B"), v("A")]) == "KEY_CONFIRMED_DUAL"
    assert decide("A", "QUANT", [v("A"), v("A", valid=False)]) == "NEEDS_SOLVER"
    assert decide(None, "QUANT", [v("A"), v("A")]) == "NO_KEY"


def test_validate_schema():
    good = {"question_id": "1", "solver_id": "s", "model": "m", "prompt_version": "p", "answer_option": "C",
            "answer_value": "3", "method": "x", "steps": [], "check_code": None, "confidence": 0.9}
    assert validate(good, {"1"}) == []
    assert validate({**good, "answer_option": "E"}, {"1"})
    assert validate({**good, "confidence": 2}, {"1"})
    assert validate({k: good[k] for k in good if k != "steps"}, {"1"})


def test_run_check_sandbox():
    assert run_check("assert 2 + 2 == 4") == (True, "")
    ok, note = run_check("assert 2 + 2 == 5")
    assert ok is False and "AssertionError" in note
    assert run_check(None) == (None, "no check code")
    assert run_check("while True: pass")[1] == "timeout"
