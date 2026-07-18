"""End-to-end grading integration tests for written-answer mode (ticket 11, issue #71).

Proves the written-answer confirm action (issue #69) produces scheduling
outcomes byte-for-byte identical to grading the same starting card state
manually, by calling ticket 08's ``apply_grade_to_card`` directly as the
oracle rather than reimplementing SM-2 math here. Also covers the override
path (a grade other than the LLM-mapped one is what actually gets applied),
the LLM-failure fallback path continuing the session normally, and that no
new schema/columns exist to leak the LLM's ``outcome``/``feedback`` into the
database -- only the resulting grade and the ``reviews`` row ticket 08's
helper already writes are ever persisted.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``), matching ``tests/test_review_written_answer.py`` and
``tests/test_review_grading.py``. Confirms the actual grading route/
persistence call from ticket 09, not a reimplementation.
"""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.main import app
from memory_ai.models import Card, Folder, Review, Source, Subject, User, UserSettings
from memory_ai.scheduling import Grade, apply_grade_to_card
from memory_ai.written_answer import (
    WrittenAnswerGradingError,
    WrittenAnswerOutcome,
    get_written_answer_grader,
)

TEST_EMAIL = "review-written-e2e-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"

_CAP = 20


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    now = datetime.now(UTC)
    user = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=user.id,
            daily_review_cap=_CAP,
            timezone="UTC",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authed_client(client: TestClient, seeded_user: User) -> TestClient:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    return client


def _make_subject(db_session: Session, user_id: int, name: str = "Subject") -> Subject:
    subject = Subject(user_id=user_id, name=name, created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)
    return subject


def _make_folder(db_session: Session, subject_id: int, name: str = "Folder") -> Folder:
    folder = Folder(subject_id=subject_id, name=name, created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


def _make_source(db_session: Session, folder_id: int, filename: str = "notes.txt") -> Source:
    source = Source(
        folder_id=folder_id,
        filename=filename,
        file_type="txt",
        raw_text="notes",
        status="done",
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_card(
    db_session: Session,
    source_id: int,
    folder_id: int,
    due_date: date,
    front: str = "front",
    back: str = "back",
    ease_factor: float = 2.5,
    interval_days: int = 3,
    repetitions: int = 2,
) -> Card:
    """A card with a non-trivial prior schedule state (repetitions=2), so a
    passing grade's ``new_interval_days`` actually depends on ``ease_factor``
    (``round_half_up(interval_days * new_ease)``) rather than hitting one of
    SM-2's fixed 1-day/6-day early steps -- a stronger equivalence check than
    a freshly-created card would give.
    """
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=ease_factor,
        interval_days=interval_days,
        repetitions=repetitions,
        due_date=due_date,
        created_at=datetime.now(UTC),
    )
    db_session.add(card)
    db_session.commit()
    db_session.refresh(card)
    return card


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    return _make_subject(db_session, seeded_user.id, "Mine")


@pytest.fixture
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    return _make_folder(db_session, my_subject.id)


@pytest.fixture
def my_source(db_session: Session, my_folder: Folder) -> Source:
    return _make_source(db_session, my_folder.id)


class _FakeGrader:
    def __init__(
        self, outcome: WrittenAnswerOutcome | None = None, error: Exception | None = None
    ) -> None:
        self._outcome = outcome
        self._error = error

    def grade(self, question: str, gold_answer: str, user_answer: str) -> WrittenAnswerOutcome:
        if self._error is not None:
            raise self._error
        assert self._outcome is not None
        return self._outcome


@pytest.fixture(autouse=True)
def _clear_grader_override() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_written_answer_grader, None)


def _override_grader(grader: _FakeGrader) -> None:
    app.dependency_overrides[get_written_answer_grader] = lambda: grader


_REVIEW_COLUMNS = {
    "id",
    "card_id",
    "grade",
    "reviewed_at",
    "prev_interval_days",
    "new_interval_days",
}


# --- equivalence: written-answer confirm == apply_grade_to_card directly ---


@pytest.mark.parametrize(
    "outcome_value,mapped_grade",
    [("perfect", "easy"), ("good", "good"), ("wrong", "again")],
)
def test_written_answer_confirm_matches_apply_grade_to_card_oracle(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    outcome_value: str,
    mapped_grade: str,
) -> None:
    today = date.today()

    # Card A: graded via the written-answer HTTP seam end-to-end.
    card_a = _make_card(db_session, my_source.id, my_folder.id, today)
    grader = _FakeGrader(
        outcome=WrittenAnswerOutcome(outcome=outcome_value, feedback="feedback")  # type: ignore[arg-type]
    )
    _override_grader(grader)

    submit_response = authed_client.post(
        f"/review/{card_a.id}/answer", data={"user_answer": "my answer", "scope": "global"}
    )
    assert submit_response.status_code == 200
    confirm_response = authed_client.post(
        f"/review/grade/{card_a.id}",
        data={"grade": mapped_grade, "scope": "global", "written": "1"},
    )
    assert confirm_response.status_code == 200

    # Card B (oracle): identical starting state, graded by calling ticket
    # 08's `apply_grade_to_card` directly with the same mapped grade -- no
    # SM-2 math reimplemented in this test.
    card_b = _make_card(db_session, my_source.id, my_folder.id, today)
    now_utc = datetime.now(UTC)
    apply_grade_to_card(db_session, card_b, cast(Grade, mapped_grade), now_utc, ZoneInfo("UTC"))
    db_session.commit()

    db_session.expire_all()
    updated_a = db_session.get(Card, card_a.id)
    updated_b = db_session.get(Card, card_b.id)
    assert updated_a is not None
    assert updated_b is not None

    assert updated_a.ease_factor == pytest.approx(updated_b.ease_factor)
    assert updated_a.interval_days == updated_b.interval_days
    assert updated_a.repetitions == updated_b.repetitions
    assert updated_a.due_date == updated_b.due_date

    review_a = db_session.execute(select(Review).where(Review.card_id == card_a.id)).scalars().one()
    review_b = db_session.execute(select(Review).where(Review.card_id == card_b.id)).scalars().one()
    assert review_a.grade == review_b.grade == mapped_grade
    assert review_a.prev_interval_days == review_b.prev_interval_days
    assert review_a.new_interval_days == review_b.new_interval_days


# --- override: the confirmed grade, not the LLM-mapped one, is applied -----


def test_override_applies_confirmed_grade_not_llm_mapped_grade(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    card = _make_card(db_session, my_source.id, my_folder.id, today)
    # LLM says "good" (maps to "good"), but the user overrides to "again".
    grader = _FakeGrader(outcome=WrittenAnswerOutcome(outcome="good", feedback="Close."))
    _override_grader(grader)

    authed_client.post(f"/review/{card.id}/answer", data={"user_answer": "x", "scope": "global"})
    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "again", "scope": "global", "written": "1"}
    )
    assert response.status_code == 200

    db_session.expire_all()
    updated = db_session.get(Card, card.id)
    assert updated is not None
    # "again" (quality 0) always resets repetitions to 0 and interval to 1
    # day -- the opposite of what "good" (a passing grade) would have done
    # to this card (repetitions=2 -> 3). If the override were ignored and
    # the LLM-mapped "good" applied instead, repetitions would be 3, not 0.
    assert updated.repetitions == 0
    assert updated.interval_days == 1

    review = db_session.execute(select(Review).where(Review.card_id == card.id)).scalars().one()
    assert review.grade == "again"
    assert review.grade != "good"


# --- fallback: LLM failure mid-session, next card proceeds normally -------


def test_fallback_does_not_lose_session_and_persists_only_the_manual_grade(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    failing_card = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=10), "Q1", "A1"
    )
    next_card = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=1), "Q2", "A2"
    )
    grader = _FakeGrader(error=WrittenAnswerGradingError("simulated timeout"))
    _override_grader(grader)

    submit_response = authed_client.post(
        f"/review/{failing_card.id}/answer", data={"user_answer": "x", "scope": "global"}
    )
    assert submit_response.status_code == 200
    text = submit_response.text
    for grade in ("again", "hard", "good", "easy"):
        assert f'id="grade-{grade}-{failing_card.id}" class="grade-preselected"' not in text

    # Session continues: the user grades the fallback-rendered card manually.
    grade_response = authed_client.post(
        f"/review/grade/{failing_card.id}",
        data={"grade": "hard", "scope": "global", "written": "1"},
    )
    assert grade_response.status_code == 200
    assert f"review-card-{next_card.id}-front" in grade_response.text

    db_session.expire_all()
    updated_failing = db_session.get(Card, failing_card.id)
    assert updated_failing is not None
    assert updated_failing.repetitions == 3  # "hard" is a passing grade: 2 -> 3

    reviews = (
        db_session.execute(select(Review).where(Review.card_id == failing_card.id)).scalars().all()
    )
    assert len(reviews) == 1
    assert reviews[0].grade == "hard"


# --- no new schema: outcome/feedback are never persisted -------------------


def test_reviews_table_has_no_outcome_or_feedback_columns() -> None:
    """Schema-level guarantee (decisions.md: "no new schema"): the `reviews`
    table only ever has the columns ticket 08 already defined -- no
    `outcome`/`feedback` column was added to smuggle the LLM's ephemeral
    grading result into the database.
    """
    columns = {column.name for column in Review.__table__.columns}
    assert columns == _REVIEW_COLUMNS


def test_written_answer_confirm_writes_exactly_one_review_row_with_no_outcome_data(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())
    grader = _FakeGrader(outcome=WrittenAnswerOutcome(outcome="perfect", feedback="Spot on!"))
    _override_grader(grader)

    authed_client.post(f"/review/{card.id}/answer", data={"user_answer": "x", "scope": "global"})
    authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "easy", "scope": "global", "written": "1"}
    )

    reviews = db_session.execute(select(Review).where(Review.card_id == card.id)).scalars().all()
    assert len(reviews) == 1
    review = reviews[0]
    assert review.grade == "easy"
    # The only columns available are the fixed ticket-08 set asserted above;
    # nothing on this row can carry "perfect" or "Spot on!" anywhere.
    assert {c.name for c in review.__table__.columns} == _REVIEW_COLUMNS
