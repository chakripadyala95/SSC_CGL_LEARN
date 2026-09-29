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


def test_report_rolls_up_and_queues_unconfirmed(tmp_path):
    import json
    from pipeline.solve import report
    (tmp_path / "data" / "questions").mkdir(parents=True)
    (tmp_path / "data" / "solver" / "verifications").mkdir(parents=True)
    qs = [{"paper_id": "p", "ssc_question_id": str(i), "section": "QUANT", "q_no": i, "review_reasons": [],
           "question_crop": f"Q{i}.png"} for i in (1, 2)]
    (tmp_path / "data" / "questions" / "questions.jsonl").write_text("".join(json.dumps(q) + "\n" for q in qs))
    rows = [{"paper_id": "p", "section": "QUANT", "q_no": 1, "question_id": "1", "official_answer": "A",
             "status": "KEY_CONFIRMED_CODE", "solver_answers": {"quant-a": "A", "quant-b": "A"}},
            {"paper_id": "p", "section": "QUANT", "q_no": 2, "question_id": "2", "official_answer": "A",
             "status": "KEY_DISPUTED", "solver_answers": {"quant-a": "B", "quant-b": "B"}}]
    (tmp_path / "data" / "solver" / "verifications" / "p.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    res = report(tmp_path)
    assert res["agree"] == res["both"] == 2
    assert [q["question_id"] for q in res["queue"]] == ["2"]
    assert "| p | QUANT | 2 | 1 | 0 | 1 |" in (tmp_path / "data" / "solver" / "SUMMARY.md").read_text()
