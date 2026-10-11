"""Database tables for papers, section mocks, versioned questions, answer verification, the formula and method
library and question tags.

Later phases add solutions, attempts and analytics tables in their own migrations.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Json = JSON().with_variant(JSONB(), "postgresql")

SECTIONS = ("QUANT", "REASONING")
CONFIRMED = ("KEY_CONFIRMED_CODE", "KEY_CONFIRMED_DUAL", "KEY_CONFIRMED_REVIEW")


class Base(DeclarativeBase):
    pass


class ExamPattern(Base):
    """Marking and timing per section; the app reads these, never hardcoded numbers."""

    __tablename__ = "exam_pattern"

    section: Mapped[str] = mapped_column(String(16), primary_key=True)
    questions: Mapped[int] = mapped_column(Integer)
    marks_correct: Mapped[float] = mapped_column(Numeric(4, 2))
    marks_wrong: Mapped[float] = mapped_column(Numeric(4, 2))
    default_timer_sec: Mapped[int] = mapped_column(Integer)


class Paper(Base):
    """One official 2024 shift, from data/intake_manifest.json."""

    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 2024-09-09_0900
    exam_date: Mapped[date] = mapped_column(Date)
    time_slot: Mapped[str] = mapped_column(String(4))
    source_filename: Mapped[str] = mapped_column(Text)
    stored_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    key_status: Mapped[str] = mapped_column(String(16), default="unknown")

    mocks: Mapped[list[Mock]] = relationship(back_populates="paper", order_by="Mock.section")


class Mock(Base):
    """A 25-question section test: each paper has one QUANT and one REASONING mock."""

    __tablename__ = "mocks"
    __table_args__ = (
        UniqueConstraint("paper_id", "section"),
        CheckConstraint(f"section IN {SECTIONS}", name="mock_section"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)  # 2024-09-09_0900_QUANT
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"))
    section: Mapped[str] = mapped_column(String(16))
    timer_sec: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT | PUBLISHED

    paper: Mapped[Paper] = relationship(back_populates="mocks")
    questions: Mapped[list[Question]] = relationship(back_populates="mock", order_by="Question.q_no")


class Question(Base):
    """A question slot in a mock; its content lives in question_versions."""

    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("mock_id", "q_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mock_id: Mapped[str] = mapped_column(ForeignKey("mocks.id"))
    q_no: Mapped[int] = mapped_column(Integer)
    ssc_question_id: Mapped[str | None] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16))  # EXTRACTED | REVIEW | REJECTED
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_versions.id", use_alter=True, name="fk_questions_current_version")
    )

    mock: Mapped[Mock] = relationship(back_populates="questions")
    versions: Mapped[list[QuestionVersion]] = relationship(
        back_populates="question", foreign_keys="QuestionVersion.question_id", order_by="QuestionVersion.version"
    )
    current_version: Mapped[QuestionVersion | None] = relationship(foreign_keys=[current_version_id], post_update=True)


class QuestionVersion(Base):
    """Immutable content of a question. Attempts and solver runs point at a version, never at a question."""

    __tablename__ = "question_versions"
    __table_args__ = (
        UniqueConstraint("question_id", "version"),
        UniqueConstraint("question_id", "content_hash", "official_answer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    version: Mapped[int] = mapped_column(Integer)
    # Same hash as pipeline.solve.question_version, so solver runs attach to the version they solved.
    content_hash: Mapped[str] = mapped_column(String(16))
    stem_text: Mapped[str] = mapped_column(Text)
    stem_text_complete: Mapped[bool] = mapped_column(Boolean)
    stem_image: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list[dict[str, Any]]] = mapped_column(Json)  # [{label, text, image}] x4
    option_ids: Mapped[dict[str, str]] = mapped_column(Json)
    official_answer: Mapped[str | None] = mapped_column(String(1))
    answer_text_layer: Mapped[str | None] = mapped_column(String(1))
    answer_page_image: Mapped[str | None] = mapped_column(String(1))
    key_status: Mapped[str] = mapped_column(String(24), default="UNVERIFIED")
    has_visual: Mapped[bool] = mapped_column(Boolean)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_bbox: Mapped[list[dict[str, Any]]] = mapped_column(Json)
    question_crop: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text)
    subtopic: Mapped[str | None] = mapped_column(Text)
    topic_source: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[Question] = relationship(back_populates="versions", foreign_keys=[question_id])
    assets: Mapped[list[QuestionAsset]] = relationship(back_populates="question_version")
    verifications: Mapped[list[AnswerVerification]] = relationship(back_populates="question_version")


class QuestionAsset(Base):
    """Image files for a version: the review crop (shows the answer mark) and the blind stem/option crops."""

    __tablename__ = "question_assets"
    __table_args__ = (UniqueConstraint("question_version_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_version_id: Mapped[int] = mapped_column(ForeignKey("question_versions.id"))
    kind: Mapped[str] = mapped_column(String(16))  # review_crop | stem | option_A..option_D
    path: Mapped[str] = mapped_column(Text)
    shows_answer: Mapped[bool] = mapped_column(Boolean, default=False)

    question_version: Mapped[QuestionVersion] = relationship(back_populates="assets")


class AnswerVerification(Base):
    """One blind solver run on one question version."""

    __tablename__ = "answer_verifications"
    __table_args__ = (UniqueConstraint("question_version_id", "solver_id", "prompt_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_version_id: Mapped[int] = mapped_column(ForeignKey("question_versions.id"))
    solver_id: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    method: Mapped[str | None] = mapped_column(Text)
    solver_answer: Mapped[str | None] = mapped_column(String(1))
    matches_key: Mapped[bool | None] = mapped_column(Boolean)
    steps: Mapped[list[str]] = mapped_column(Json, default=list)
    check_code: Mapped[str | None] = mapped_column(Text)
    check_passed: Mapped[bool | None] = mapped_column(Boolean)
    check_note: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question_version: Mapped[QuestionVersion] = relationship(back_populates="verifications")


class ReviewItem(Base):
    """Anything that failed a check. Nothing here is published until a person approves, edits or rejects it."""

    __tablename__ = "review_queue"
    __table_args__ = (UniqueConstraint("paper_id", "section", "q_no", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"))
    section: Mapped[str] = mapped_column(String(16))
    q_no: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # extract | solver
    reasons: Mapped[list[str]] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN | APPROVED | EDITED | REJECTED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Formula(Base):
    """A formula (Quant) or method (Reasoning) library entry from data/library/. IDs never change once published."""

    __tablename__ = "formulas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # percentage.successive-change
    section: Mapped[str] = mapped_column(String(16))
    topic: Mapped[str] = mapped_column(Text)
    topic_slug: Mapped[str] = mapped_column(String(48), index=True)
    subtopic: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    statement: Mapped[str] = mapped_column(Text)
    shortcut: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(16))  # PASSED | FAILED | NEEDS_REVIEW
    entry: Mapped[dict[str, Any]] = mapped_column(Json)  # the full library entry


class QuestionTag(Base):
    """Phase 3c tags for a question (data/tags/questions.jsonl): one row per question, LLM-proposed and
    sample-checked by a second blind tagger."""

    __tablename__ = "question_tags"

    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    topic: Mapped[str] = mapped_column(Text, index=True)
    subtopic: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(Text)
    shortcut_used: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer)
    expected_time_sec: Mapped[int] = mapped_column(Integer)
    has_visual: Mapped[bool] = mapped_column(Boolean)
    tagger: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str] = mapped_column(String(32))
    # A near-identical question from an earlier shift; analytics count the pair once.
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))

    formulas: Mapped[list[QuestionFormula]] = relationship(
        order_by="QuestionFormula.rank", viewonly=True,
        primaryjoin="QuestionTag.question_id == foreign(QuestionFormula.question_id)")


class QuestionFormula(Base):
    """Formulas or methods a question's fastest solution uses; rank 0 is the primary one."""

    __tablename__ = "question_formulas"

    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.id"), primary_key=True, index=True)
    rank: Mapped[int] = mapped_column(Integer)

    formula: Mapped[Formula] = relationship()
