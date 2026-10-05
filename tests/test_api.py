"""Loader and API tests against a real PostgreSQL database.

Set TEST_DATABASE_URL (default: postgresql+psycopg://ssc:ssc@localhost:5432/ssc_test). The database is wiped.
Skipped when it is not reachable.
"""

import copy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from api.load import content_hash, load_all, paper_id
from api.models import AnswerVerification, Base, Mock, Question, QuestionFormula, QuestionTag, QuestionVersion, ReviewItem

URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://ssc:ssc@localhost:5432/ssc_test")
PAPER = "2024-09-09_0900"

# A real record from data/questions/questions.jsonl; its hash is the one pipeline.solve recorded for it.
REAL_Q1 = {
    "paper_id": PAPER, "mock_id": f"{PAPER}_QUANT", "q_no": 1, "section": "QUANT",
    "ssc_question_id": "630680428862",
    "option_ids": {"A": "6306801673492", "B": "6306801673493", "C": "6306801673494", "D": "6306801673495"},
    "stem_text": "A grocer professes to sell rice at the cost price, but uses a fake weight of 870 g for 1\nkg. "
                 "Find his profit percentage (correct to two decimal places).",
    "stem_text_complete": True, "stem_image": None,
    "options": [{"label": "A", "text": "11.11%", "image": None}, {"label": "B", "text": "14.94%", "image": None},
                {"label": "C", "text": "15.11%", "image": None}, {"label": "D", "text": "18.21%", "image": None}],
    "official_answer": "B", "answer_text_layer": "B", "answer_page_image": "B", "key_status": "UNVERIFIED",
    "source_file": "x.pdf", "source_page": 19, "source_bbox": [{"page": 19, "bbox": [75.9, 293.0, 416.4, 379.5]}],
    "question_crop": f"data/questions/assets/{PAPER}/Q01.png", "has_visual": False, "status": "EXTRACTED",
    "review_reasons": [], "topic": "Profit & Loss", "subtopic": None, "topic_source": "rule",
}


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL)
    try:
        eng.connect().close()
    except OperationalError:
        pytest.skip(f"PostgreSQL not reachable at {URL}")
    return eng


@pytest.fixture
def session(engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def question(section: str, q_no: int, answer: str = "A", **extra) -> dict:
    q = copy.deepcopy(REAL_Q1)
    q.update(section=section, q_no=q_no, mock_id=f"{PAPER}_{section}", official_answer=answer,
             ssc_question_id=f"{section[0]}{q_no:011d}", stem_text=f"{section} question {q_no}",
             question_crop=f"data/questions/assets/{PAPER}/{section[0]}{q_no:02d}.png", **extra)
    return q


def verification(q: dict, status: str = "KEY_CONFIRMED_DUAL") -> dict:
    run = {"question_version": content_hash(q), "prompt_version": "solver_v1", "solver_answer": q["official_answer"],
           "matches_key": True, "check_passed": True, "steps": ["step"], "model": "m", "method": "m"}
    return {"paper_id": q["paper_id"], "section": q["section"], "q_no": q["q_no"],
            "official_answer": q["official_answer"], "status": status,
            "verifications": [dict(run, solver_id="a"), dict(run, solver_id="b")]}


def write_data(root: Path, questions: list[dict], verifications: list[dict], queue: list[dict] = (),
               decisions: list[dict] = (), library: dict[str, list[dict]] | None = None,
               tags: list[dict] = ()) -> Path:
    manifest = {"sources": [
        {"date": "09.09.2024", "time_slot": "0900", "filename": "sheet.pdf", "stored_path": "data/raw/sheet.pdf",
         "sha256": "0" * 64, "key_status": "unknown", "accepted": True},
        {"date": "10.09.2024", "time_slot": "0900", "filename": "bad.pdf", "stored_path": "",
         "sha256": "1" * 64, "key_status": "unknown", "accepted": False},
    ]}
    (root / "questions").mkdir(parents=True, exist_ok=True)
    (root / "solver" / "verifications").mkdir(parents=True, exist_ok=True)
    (root / "intake_manifest.json").write_text(json.dumps(manifest))
    (root / "questions" / "questions.jsonl").write_text("".join(json.dumps(q) + "\n" for q in questions))
    (root / "questions" / "review_queue.json").write_text(json.dumps(list(queue)))
    (root / "solver" / "verifications" / f"{PAPER}.jsonl").write_text(
        "".join(json.dumps(v) + "\n" for v in verifications))
    (root / "review").mkdir(exist_ok=True)
    (root / "review" / "decisions.jsonl").write_text("".join(json.dumps(d) + "\n" for d in decisions))
    for name, entries in (library or {}).items():  # "quant/percentage" -> data/library/quant/percentage.json
        (root / "library" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "library" / f"{name}.json").write_text(json.dumps(entries))
    if tags:
        (root / "tags").mkdir(exist_ok=True)
        (root / "tags" / "questions.jsonl").write_text("".join(json.dumps(t) + "\n" for t in tags))
    return root


@pytest.fixture
def bank():
    """One paper: Quant fully confirmed, Reasoning with one disputed key."""
    quant = [question("QUANT", n) for n in range(1, 26)]
    reasoning = [question("REASONING", n, answer="C") for n in range(1, 26)]
    verifs = [verification(q) for q in quant] + [verification(q) for q in reasoning[:24]]
    verifs.append(verification(reasoning[24], status="KEY_DISPUTED"))
    return quant, reasoning, verifs


def test_content_hash_matches_solver_pipeline():
    assert content_hash(REAL_Q1) == "e30f9c228483d581"


def test_paper_id():
    assert paper_id("26.09.2024", "1600") == "2024-09-26_1600"


def test_load_publishes_only_fully_confirmed_mocks(session, tmp_path, bank):
    quant, reasoning, verifs = bank
    report = load_all(session, write_data(tmp_path, quant + reasoning, verifs))
    session.commit()
    assert report.counts["papers added"] == 1  # the rejected sheet is not loaded
    assert report.counts["questions added"] == 50
    assert session.get(Mock, f"{PAPER}_QUANT").status == "PUBLISHED"
    assert session.get(Mock, f"{PAPER}_REASONING").status == "DRAFT"
    item = session.scalar(select(ReviewItem))
    assert (item.section, item.q_no, item.source, item.reasons) == ("REASONING", 25, "solver", ["KEY_DISPUTED"])
    assert session.scalar(select(text("count(*)")).select_from(AnswerVerification)) == 100


def test_reload_changes_nothing(session, tmp_path, bank):
    data = write_data(tmp_path, bank[0] + bank[1], bank[2])
    load_all(session, data)
    session.commit()
    assert load_all(session, data).changed == 0


def test_changed_stem_makes_new_version_and_unpublishes(session, tmp_path, bank):
    quant, reasoning, verifs = bank
    load_all(session, write_data(tmp_path, quant + reasoning, verifs))
    session.commit()
    edited = copy.deepcopy(quant)
    edited[0]["stem_text"] = "corrected stem"
    report = load_all(session, write_data(tmp_path, edited + reasoning, verifs))
    session.commit()
    assert report.counts["question versions added"] == 1
    q = session.scalar(select(Question).where(Question.mock_id == f"{PAPER}_QUANT", Question.q_no == 1))
    assert [v.version for v in q.versions] == [1, 2]
    assert q.current_version.key_status == "UNVERIFIED"  # old solver runs belong to version 1
    assert session.get(Mock, f"{PAPER}_QUANT").status == "DRAFT"


def test_extraction_review_items_are_queued(session, tmp_path, bank):
    quant, reasoning, verifs = bank
    quant[10]["status"] = "REVIEW"
    queue = [{"paper_id": PAPER, "section": "QUANT", "q_no": 11, "reasons": ["Question ID not found"]}]
    load_all(session, write_data(tmp_path, quant + reasoning, verifs, queue))
    session.commit()
    items = session.scalars(select(ReviewItem).where(ReviewItem.source == "extract")).all()
    assert [(i.q_no, i.reasons, i.question_id is not None) for i in items] == [(11, ["Question ID not found"], True)]


@pytest.fixture
def client(engine, session, tmp_path, bank):
    from fastapi.testclient import TestClient

    from api.db import get_session
    from api.main import app

    load_all(session, write_data(tmp_path, bank[0] + bank[1], bank[2]))
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_published_mock_hides_the_key(client):
    rows = client.get(f"/mocks/{PAPER}_QUANT/questions").json()
    assert len(rows) == 25
    assert all("official_answer" not in r and "review_crop_url" not in r for r in rows)


def test_draft_mock_is_not_playable(client):
    assert client.get(f"/mocks/{PAPER}_REASONING/questions").status_code == 409


def test_admin_sees_key_and_solver_runs(client):
    rows = client.get(f"/admin/mocks/{PAPER}_REASONING/questions").json()
    assert rows[24]["official_answer"] == "C"
    assert rows[24]["key_status"] == "KEY_DISPUTED"
    assert {v["solver_id"] for v in rows[24]["verifications"]} == {"a", "b"}
    assert rows[0]["review_crop_url"] == f"/assets/{PAPER}/R01.png"


def test_mock_listing_filters(client):
    assert [m["id"] for m in client.get("/mocks", params={"status": "published"}).json()] == [f"{PAPER}_QUANT"]
    assert len(client.get("/admin/review-queue").json()) == 1


def test_discarded_solver_verdicts_stop_counting(session, tmp_path, bank):
    quant, reasoning, verifs = bank
    load_all(session, write_data(tmp_path, quant + reasoning, verifs))
    session.commit()
    rest = [v for v in verifs if not (v["section"] == "QUANT" and v["q_no"] == 3)]  # pipeline re-solving Q3
    report = load_all(session, write_data(tmp_path, quant + reasoning, rest))
    session.commit()
    assert report.counts["key statuses withdrawn"] == 1
    assert session.get(Mock, f"{PAPER}_QUANT").status == "DRAFT"


def decision(q: dict, action: str, answer: str | None) -> dict:
    return {"paper_id": q["paper_id"], "section": q["section"], "q_no": q["q_no"],
            "question_id": q["ssc_question_id"], "question_version": content_hash(q),
            "official_answer": q["official_answer"], "status_before": "KEY_DISPUTED", "action": action,
            "answer": answer, "note": "", "decided_at": "2026-10-01T00:00:00Z"}


@pytest.mark.parametrize("action,answer", [("approve", "C"), ("edit", "B")])
def test_review_decision_confirms_key_and_publishes(session, tmp_path, bank, action, answer):
    quant, reasoning, verifs = bank
    data = write_data(tmp_path, quant + reasoning, verifs, decisions=[decision(reasoning[24], action, answer)])
    load_all(session, data)
    session.commit()
    assert session.get(Mock, f"{PAPER}_REASONING").status == "PUBLISHED"
    q = session.scalar(select(Question).where(Question.mock_id == f"{PAPER}_REASONING", Question.q_no == 25))
    assert (q.current_version.official_answer, q.current_version.key_status) == (answer, "KEY_CONFIRMED_REVIEW")
    assert len(q.versions) == (2 if action == "edit" else 1)
    item = session.scalar(select(ReviewItem).where(ReviewItem.question_id == q.id))
    assert item.status == {"approve": "APPROVED", "edit": "EDITED"}[action]
    assert load_all(session, data).changed == 0


def test_rejected_question_keeps_mock_unpublished(session, tmp_path, bank):
    quant, reasoning, verifs = bank
    load_all(session, write_data(tmp_path, quant + reasoning, verifs,
                                 decisions=[decision(reasoning[24], "reject", None)]))
    session.commit()
    assert session.get(Mock, f"{PAPER}_REASONING").status == "DRAFT"


def entry(fid: str, topic: str, subtopic: str, status: str = "PASSED") -> dict:
    return {"id": fid, "topic": topic, "subtopic": subtopic, "name": fid.split(".")[1].replace("-", " "),
            "statement": "x", "conditions": [], "derivation": ["d"], "visual_proof": None, "shortcut": None,
            "worked_example": None, "common_traps": ["t"], "related_ids": [], "diagram": None,
            "verification": {"kind": "identity", "code": "pass", "result": {"status": status}}}


LIBRARY = {
    "quant/profit-loss": [entry("profit-loss.false-weight", "Profit & Loss", "False weight"),
                          entry("profit-loss.profit-percent", "Profit & Loss", "Profit & loss basics")],
    "reasoning/series": [entry("series.number-series", "Series", "Number series", status="NEEDS_REVIEW")],
}


def tag(section: str, q_no: int, topic: str, subtopic: str, qtype: str, ids: list[str], difficulty: int = 2,
        **extra) -> dict:
    return {"key": f"{PAPER}_{section[0]}{q_no:02d}", "topic": topic, "subtopic": subtopic, "question_type": qtype,
            "formula_ids": ids, "shortcut_used": "s", "difficulty": difficulty, "expected_time_sec": 40,
            "has_visual": False, "tagger": "tagger-a", "prompt_version": "tagger_v3", **extra}


def bank_tags() -> list[dict]:
    pl = ("Profit & Loss", "False weight", "false weight profit %", ["profit-loss.false-weight",
                                                                      "profit-loss.profit-percent"])
    tags = [tag("QUANT", n, *pl, difficulty=3 if n <= 5 else 2) for n in range(1, 21)]
    tags += [tag("QUANT", n, "Profit & Loss", "Profit & loss basics", "profit % from CP/SP",
                 ["profit-loss.profit-percent"]) for n in range(21, 26)]
    tags[-1]["duplicate_of"] = f"{PAPER}_Q21"  # counted once in the tree
    tags += [tag("REASONING", n, "Series", "Number series", "missing term", ["series.number-series"])
             for n in range(1, 26)]
    return tags


@pytest.fixture
def indexed(engine, session, tmp_path, bank):
    from fastapi.testclient import TestClient

    from api.db import get_session
    from api.main import app

    quant, reasoning, verifs = bank
    quant[6]["stem_text"] = "A train crosses a platform in 20 seconds"
    verifs = [verification(quant[6]) if (v["section"], v["q_no"]) == ("QUANT", 7) else v for v in verifs]
    data = write_data(tmp_path, quant + reasoning, verifs, library=LIBRARY, tags=bank_tags())
    report = load_all(session, data)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app), report, data
    app.dependency_overrides.clear()


def test_tags_and_formulas_load_idempotently(indexed, session):
    _, report, data = indexed
    assert (report.counts["formulas added"], report.counts["question tags added"]) == (3, 50)
    links = session.scalars(select(QuestionFormula).order_by(QuestionFormula.question_id, QuestionFormula.rank))
    assert [f.formula_id for f in links][:2] == ["profit-loss.false-weight", "profit-loss.profit-percent"]
    dup = session.scalar(select(QuestionTag).where(QuestionTag.duplicate_of_id.is_not(None)))
    assert dup.duplicate_of_id == session.scalar(
        select(Question.id).where(Question.mock_id == f"{PAPER}_QUANT", Question.q_no == 21))
    assert load_all(session, data).changed == 0


def test_retag_replaces_formula_links(indexed, session):
    client, _, data = indexed
    tags = bank_tags()
    tags[0]["formula_ids"] = ["profit-loss.profit-percent"]
    (data / "tags" / "questions.jsonl").write_text("".join(json.dumps(t) + "\n" for t in tags))
    report = load_all(session, data)
    session.commit()
    assert report.counts["question formula links set"] == 1
    assert client.get("/formulas/profit-loss.false-weight").json()["question_count"] == 19


def test_index_tree_counts_and_frequency(indexed):
    client = indexed[0]
    tree = client.get("/index/tree", params={"section": "quant"}).json()
    assert [(t["topic"], t["slug"], t["count"], t["per_shift"]) for t in tree] == [
        ("Profit & Loss", "profit-loss", 24, 24.0)]  # one paper; the repeat is not counted
    subs = {s["name"]: s for s in tree[0]["subtopics"]}
    assert subs["False weight"]["count"] == 20
    assert subs["Profit & loss basics"]["question_types"] == [{"name": "profit % from CP/SP", "count": 4}]


def test_index_filters(indexed):
    client = indexed[0]
    get = lambda **p: client.get("/index/questions", params=p).json()  # noqa: E731
    assert get()["total"] == 50
    assert get(section="reasoning")["total"] == 25
    assert get(topic="Profit & Loss", subtopic="False weight", difficulty=3)["total"] == 5
    assert get(formula="profit-loss.profit-percent")["total"] == 25
    assert get(status="confirmed")["total"] == 49  # Reasoning Q25 is disputed
    assert get(status="KEY_DISPUTED")["rows"][0]["q_no"] == 25
    row = get(q="trains")["rows"]  # full-text search matches "train"
    assert [(r["section"], r["q_no"]) for r in row] == [("QUANT", 7)]
    assert get(q="20 seconds")["total"] == 1
    first = get(limit=1)["rows"][0]
    assert [f["id"] for f in first["formulas"]] == ["profit-loss.false-weight", "profit-loss.profit-percent"]
    assert first["crop_url"] == f"/assets/{PAPER}/Q01.png"
    assert "official_answer" not in first and "answer" not in first


def test_study_page_shows_only_verified_answers(indexed):
    client = indexed[0]
    ids = {(r["section"], r["q_no"]): r["id"] for r in client.get("/index/questions", params={"limit": 50}).json()["rows"]}
    q = client.get(f"/study/questions/{ids['QUANT', 1]}").json()
    assert (q["answer"], q["tag"]["subtopic"], q["working"]) == ("A", "False weight", ["step"])
    assert client.get(f"/study/questions/{ids['REASONING', 25]}").status_code == 409
    assert client.get("/study/questions/999999").status_code == 404


def test_formula_library_routes(indexed):
    client = indexed[0]
    rows = client.get("/formulas", params={"topic_slug": "profit-loss"}).json()
    assert [(f["id"], f["question_count"]) for f in rows] == [("profit-loss.false-weight", 20),
                                                               ("profit-loss.profit-percent", 25)]
    series = client.get("/formulas/series.number-series").json()
    assert (series["verification_status"], series["question_count"], series["section"]) == ("NEEDS_REVIEW", 25,
                                                                                            "REASONING")
    assert client.get("/formulas/nope.nope").status_code == 404
