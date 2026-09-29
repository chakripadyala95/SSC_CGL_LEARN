"""Load the pipeline's output files into the database.

Usage: python -m api.load [--data-dir PATH]

Reads data/intake_manifest.json (papers), data/questions/questions.jsonl and review_queue.json (extraction),
and data/solver/verifications/*.jsonl (solver runs). Idempotent: re-running changes nothing unless an input
changed. A question whose stem, options or key changed gets a new version; older versions stay for the
attempts and solver runs that point at them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import settings
from api.db import SessionLocal
from api.models import (
    CONFIRMED,
    SECTIONS,
    AnswerVerification,
    ExamPattern,
    Mock,
    Paper,
    Question,
    QuestionAsset,
    QuestionVersion,
    ReviewItem,
)

# Tier-1: 25 questions per section, +2 / -0.50, 15 min default per section mock.
DEFAULT_PATTERN = {s: dict(questions=25, marks_correct=2, marks_wrong=0.5, default_timer_sec=900) for s in SECTIONS}
TOPIC_FIELDS = ("topic", "subtopic", "topic_source")


def content_hash(q: dict) -> str:
    """What a blind solver sees. Must match pipeline.solve.question_version."""
    payload = json.dumps([q["ssc_question_id"], q["stem_text"], q["stem_image"],
                          [[o["text"], o["image"]] for o in q["options"]]], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def paper_id(date: str, time_slot: str) -> str:
    """'09.09.2024', '0900' -> '2024-09-09_0900'."""
    return f"{datetime.strptime(date, '%d.%m.%Y').date().isoformat()}_{time_slot}"


@dataclass
class Report:
    counts: Counter = field(default_factory=Counter)

    def add(self, what: str, n: int = 1) -> None:
        self.counts[what] += n

    @property
    def changed(self) -> int:
        return sum(self.counts.values())

    def __str__(self) -> str:
        if not self.changed:
            return "No changes."
        return "\n".join(f"{k}: {v}" for k, v in sorted(self.counts.items()))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_exam_pattern(s: Session, r: Report) -> None:
    for section, values in DEFAULT_PATTERN.items():
        if s.get(ExamPattern, section) is None:  # never overwrite values someone configured
            s.add(ExamPattern(section=section, **values))
            r.add("exam_pattern added")


def load_papers(s: Session, manifest: dict, r: Report) -> None:
    for src in manifest["sources"]:
        if not src["accepted"]:
            continue
        pid = paper_id(src["date"], src["time_slot"])
        values = dict(exam_date=datetime.strptime(src["date"], "%d.%m.%Y").date(), time_slot=src["time_slot"],
                      source_filename=src["filename"], stored_path=src["stored_path"], sha256=src["sha256"],
                      key_status=src["key_status"])
        paper = s.get(Paper, pid)
        if paper is None:
            s.add(Paper(id=pid, **values))
            r.add("papers added")
        elif _update(paper, values):
            r.add("papers updated")
    s.flush()


def _update(obj: Any, values: dict) -> bool:
    changed = False
    for k, v in values.items():
        if getattr(obj, k) != v:
            setattr(obj, k, v)
            changed = True
    return changed


def _mock(s: Session, pid: str, section: str, r: Report) -> Mock:
    mid = f"{pid}_{section}"
    mock = s.get(Mock, mid)
    if mock is None:
        timer = s.get(ExamPattern, section).default_timer_sec
        mock = Mock(id=mid, paper_id=pid, section=section, timer_sec=timer, status="DRAFT")
        s.add(mock)
        s.flush()
        r.add("mocks added")
    return mock


def _assets(q: dict) -> dict[str, tuple[str, bool]]:
    assets = {}
    if q["question_crop"]:
        assets["review_crop"] = (q["question_crop"], True)
    if q["stem_image"]:
        assets["stem"] = (q["stem_image"], False)
    for o in q["options"]:
        if o["image"]:
            assets[f"option_{o['label']}"] = (o["image"], False)
    return assets


def load_questions(s: Session, records: list[dict], r: Report) -> None:
    for q in records:
        if q["section"] not in SECTIONS:
            continue
        mock = _mock(s, q["paper_id"], q["section"], r)
        question = s.scalar(select(Question).where(Question.mock_id == mock.id, Question.q_no == q["q_no"]))
        if question is None:
            question = Question(mock_id=mock.id, q_no=q["q_no"], ssc_question_id=q["ssc_question_id"],
                                status=q["status"])
            s.add(question)
            s.flush()
            r.add("questions added")
        elif _update(question, dict(ssc_question_id=q["ssc_question_id"], status=q["status"])):
            r.add("questions updated")

        h = content_hash(q)
        version = s.scalar(select(QuestionVersion).where(
            QuestionVersion.question_id == question.id, QuestionVersion.content_hash == h,
            QuestionVersion.official_answer == q["official_answer"]))
        if version is None:
            n = len(question.versions)
            version = QuestionVersion(
                question_id=question.id, version=n + 1, content_hash=h, stem_text=q["stem_text"],
                stem_text_complete=q["stem_text_complete"], stem_image=q["stem_image"], options=q["options"],
                option_ids=q["option_ids"], official_answer=q["official_answer"],
                answer_text_layer=q["answer_text_layer"], answer_page_image=q["answer_page_image"],
                key_status=q["key_status"], has_visual=q["has_visual"], source_page=q["source_page"],
                source_bbox=q["source_bbox"], question_crop=q["question_crop"],
                **{k: q[k] for k in TOPIC_FIELDS})
            s.add(version)
            s.flush()
            s.refresh(question)
            r.add("question versions added")
            for kind, (path, shows_answer) in _assets(q).items():
                s.add(QuestionAsset(question_version_id=version.id, kind=kind, path=path, shows_answer=shows_answer))
                r.add("assets added")
        elif _update(version, {k: q[k] for k in TOPIC_FIELDS}):  # provisional tags change without a new version
            r.add("topic tags updated")
        if question.current_version_id != version.id:
            question.current_version_id = version.id
            r.add("current versions moved")
    s.flush()


def _question(s: Session, pid: str, section: str, q_no: int) -> Question | None:
    return s.scalar(select(Question).where(Question.mock_id == f"{pid}_{section}", Question.q_no == q_no))


def _queue(s: Session, pid: str, section: str, q_no: int, source: str, reasons: list[str], r: Report) -> None:
    question = _question(s, pid, section, q_no)
    item = s.scalar(select(ReviewItem).where(ReviewItem.paper_id == pid, ReviewItem.section == section,
                                             ReviewItem.q_no == q_no, ReviewItem.source == source))
    values = dict(question_id=question.id if question else None, reasons=reasons)
    if item is None:
        s.add(ReviewItem(paper_id=pid, section=section, q_no=q_no, source=source, status="OPEN", **values))
        r.add("review items added")
    elif item.status == "OPEN" and _update(item, values):
        r.add("review items updated")


def load_review_queue(s: Session, items: list[dict], r: Report) -> None:
    for it in items:
        if it["section"] in SECTIONS:
            _queue(s, it["paper_id"], it["section"], it["q_no"], "extract", it["reasons"], r)
    s.flush()


def load_verifications(s: Session, records: list[dict], r: Report) -> None:
    for rec in records:
        question = _question(s, rec["paper_id"], rec["section"], rec["q_no"])
        if question is None:
            continue
        for v in rec["verifications"]:
            version = s.scalar(select(QuestionVersion).where(
                QuestionVersion.question_id == question.id, QuestionVersion.content_hash == v["question_version"],
                QuestionVersion.official_answer == rec["official_answer"]))
            if version is None:  # the question changed since this run; the run is stale
                r.add("stale solver runs skipped")
                continue
            existing = s.scalar(select(AnswerVerification).where(
                AnswerVerification.question_version_id == version.id,
                AnswerVerification.solver_id == v["solver_id"],
                AnswerVerification.prompt_version == v["prompt_version"]))
            if existing is None:
                s.add(AnswerVerification(
                    question_version_id=version.id, solver_id=v["solver_id"], model=v.get("model"),
                    prompt_version=v["prompt_version"], method=v.get("method"), solver_answer=v.get("solver_answer"),
                    matches_key=v.get("matches_key"), steps=v.get("steps") or [], check_code=v.get("check_code"),
                    check_passed=v.get("check_passed"), check_note=v.get("check_note"),
                    confidence=v.get("confidence"), valid=v.get("valid", True)))
                r.add("solver runs added")
        current = question.current_version
        on_current = any(v["question_version"] == current.content_hash for v in rec["verifications"])
        if on_current and current.official_answer == rec["official_answer"]:
            if current.key_status != rec["status"] and current.key_status != "KEY_CONFIRMED_REVIEW":
                current.key_status = rec["status"]
                r.add("key statuses set")
            if rec["status"] not in CONFIRMED:
                _queue(s, rec["paper_id"], rec["section"], rec["q_no"], "solver", [rec["status"]], r)
    s.flush()


def publish_mocks(s: Session, r: Report) -> None:
    """A section mock is PUBLISHED only when all its questions have a confirmed key."""
    s.expire_all()
    for mock in s.scalars(select(Mock)):
        expected = s.get(ExamPattern, mock.section).questions
        qs = mock.questions
        ready = len(qs) == expected and all(
            q.status != "REJECTED" and q.current_version and q.current_version.key_status in CONFIRMED for q in qs)
        status = "PUBLISHED" if ready else "DRAFT"
        if mock.status != status:
            mock.status = status
            r.add(f"mocks set {status}")


def load_all(s: Session, data_dir: Path) -> Report:
    r = Report()
    load_exam_pattern(s, r)
    s.flush()
    load_papers(s, json.loads((data_dir / "intake_manifest.json").read_text()), r)
    questions = data_dir / "questions" / "questions.jsonl"
    if questions.exists():
        load_questions(s, read_jsonl(questions), r)
    queue = data_dir / "questions" / "review_queue.json"
    if queue.exists():
        load_review_queue(s, json.loads(queue.read_text()), r)
    for path in sorted((data_dir / "solver" / "verifications").glob("*.jsonl")):
        load_verifications(s, read_jsonl(path), r)
    publish_mocks(s, r)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=settings.data_dir)
    args = ap.parse_args()
    with SessionLocal() as s:
        report = load_all(s, args.data_dir)
        s.commit()
    print(report)


if __name__ == "__main__":
    main()
