"""HTTP-seam tests for written-answer mode (ticket 11, issue #69).

Covers: the per-review-session toggle (off by default, textarea vs "Show
answer"), submitting an answer -> LLM success reveals gold answer + outcome
badge + feedback + four grade buttons with the outcome-mapped button
pre-highlighted for every outcome, a non-pre-selected button remaining
clickable (including "Hard", never auto-mapped), a simulated LLM failure
falling back to plain flip-and-grade with an inline notice and no
pre-selected button, and that the toggle persists across a card advance
(next card's front is also the written-answer variant).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``), matching ``tests/test_review_grading.py``.
"""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.main import app
from memory_ai.models import Card, Folder, Source, Subject, User, UserSettings
from memory_ai.written_answer import (
    WrittenAnswerGrader,
    WrittenAnswerGradingError,
    WrittenAnswerOutcome,
    get_written_answer_grader,
)

TEST_EMAIL = "review-written-seam-test-user@example.com"
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
) -> Card:
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
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
    """Injected in place of the real Anthropic-backed grader.

    Configured with either a canned ``WrittenAnswerOutcome`` to return or an
    exception to raise, mirroring how ``test_convert.py`` injects a fake
    ``FlashcardGenerator``.
    """

    def __init__(
        self, outcome: WrittenAnswerOutcome | None = None, error: Exception | None = None
    ) -> None:
        self._outcome = outcome
        self._error = error
        self.calls: list[tuple[str, str, str]] = []

    def grade(self, question: str, gold_answer: str, user_answer: str) -> WrittenAnswerOutcome:
        self.calls.append((question, gold_answer, user_answer))
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


# --- per-session toggle ------------------------------------------------


def test_review_global_defaults_to_flip_mode_without_toggle(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.get("/review")

    assert response.status_code == 200
    assert "Show answer" in response.text
    assert f'id="review-card-{card.id}-answer"' not in response.text


def test_review_global_with_written_toggle_shows_textarea(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.get("/review?written=1")

    assert response.status_code == 200
    assert f'id="review-card-{card.id}-answer"' in response.text
    assert "Show answer" not in response.text
    assert f'id="submit-answer-{card.id}"' in response.text


def test_review_subject_with_written_toggle_shows_textarea(
    authed_client: TestClient,
    db_session: Session,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.get(f"/review/subjects/{my_subject.id}?written=1")

    assert response.status_code == 200
    assert f'id="review-card-{card.id}-answer"' in response.text


# --- submit answer: success ---------------------------------------------


@pytest.mark.parametrize(
    "outcome_value,expected_grade",
    [("perfect", "easy"), ("good", "good"), ("wrong", "again")],
)
def test_submit_answer_success_reveals_outcome_and_preselects_mapped_grade(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    outcome_value: str,
    expected_grade: str,
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today(), "Q", "The gold answer")
    grader = _FakeGrader(
        outcome=WrittenAnswerOutcome(outcome=outcome_value, feedback="Some feedback text.")  # type: ignore[arg-type]
    )
    _override_grader(grader)

    response = authed_client.post(
        f"/review/{card.id}/answer",
        data={"user_answer": "my answer", "scope": "global"},
    )

    assert response.status_code == 200
    text = response.text
    assert "The gold answer" in text
    assert f'id="review-card-{card.id}-outcome"' in text
    assert outcome_value in text
    assert "Some feedback text." in text
    for grade in ("again", "hard", "good", "easy"):
        assert f"grade-{grade}-{card.id}" in text

    # Exactly the mapped button carries the pre-selected marker; no other.
    preselected_id = f'id="grade-{expected_grade}-{card.id}" class="grade-preselected"'
    assert preselected_id in text
    for grade in ("again", "hard", "good", "easy"):
        if grade != expected_grade:
            assert f'id="grade-{grade}-{card.id}" class="grade-preselected"' not in text

    assert grader.calls == [("Q", "The gold answer", "my answer")]


def test_submit_answer_confirming_preselected_grade_applies_it(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    card = _make_card(db_session, my_source.id, my_folder.id, today)
    grader = _FakeGrader(outcome=WrittenAnswerOutcome(outcome="perfect", feedback="Nice."))
    _override_grader(grader)

    authed_client.post(f"/review/{card.id}/answer", data={"user_answer": "x", "scope": "global"})
    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "easy", "scope": "global", "written": "1"}
    )

    assert response.status_code == 200
    db_session.expire_all()
    updated = db_session.get(Card, card.id)
    assert updated is not None
    # "easy" maps to quality 5 -> repetitions=1, interval=1 day.
    assert updated.repetitions == 1
    assert updated.due_date == today + timedelta(days=1)


# --- override: a non-pre-selected button remains clickable, including Hard


def test_hard_is_reachable_even_though_never_auto_mapped(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())
    grader = _FakeGrader(outcome=WrittenAnswerOutcome(outcome="perfect", feedback="Nice."))
    _override_grader(grader)

    submit_response = authed_client.post(
        f"/review/{card.id}/answer", data={"user_answer": "x", "scope": "global"}
    )
    assert f'id="grade-hard-{card.id}"' in submit_response.text
    assert f'id="grade-hard-{card.id}" class="grade-preselected"' not in submit_response.text

    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "hard", "scope": "global", "written": "1"}
    )

    assert response.status_code == 200
    db_session.expire_all()
    updated = db_session.get(Card, card.id)
    assert updated is not None
    # "hard" (quality 3) is a passing grade -> repetitions increments, unlike
    # the LLM-mapped "perfect"/"easy" outcome for this same card.
    assert updated.repetitions == 1
    assert updated.ease_factor < 2.5  # hard always lowers ease vs the 2.5 default


# --- submit answer: failure fallback -------------------------------------


def test_submit_answer_llm_failure_falls_back_to_plain_flip_and_grade(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today(), "Q", "The gold answer")
    grader = _FakeGrader(error=WrittenAnswerGradingError("simulated timeout"))
    _override_grader(grader)

    response = authed_client.post(
        f"/review/{card.id}/answer", data={"user_answer": "my answer", "scope": "global"}
    )

    assert response.status_code == 200
    text = response.text
    assert "The gold answer" in text
    assert f'id="review-card-{card.id}-outcome"' not in text
    assert f'id="review-card-{card.id}-written-notice"' in text
    for grade in ("again", "hard", "good", "easy"):
        assert f'id="grade-{grade}-{card.id}"' in text
        assert f'id="grade-{grade}-{card.id}" class="grade-preselected"' not in text


def test_fallback_session_continues_normally_to_next_card(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    failed_card = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=5), "Q1", "A1"
    )
    next_card = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=1), "Q2", "A2"
    )
    grader = _FakeGrader(error=WrittenAnswerGradingError("simulated failure"))
    _override_grader(grader)

    authed_client.post(
        f"/review/{failed_card.id}/answer", data={"user_answer": "x", "scope": "global"}
    )
    # Grade the fallback-rendered card manually (no pre-selection was given).
    response = authed_client.post(
        f"/review/grade/{failed_card.id}",
        data={"grade": "good", "scope": "global", "written": "1"},
    )

    assert response.status_code == 200
    text = response.text
    assert f"review-card-{next_card.id}-front" in text
    # Written-answer mode carried forward onto the next card too.
    assert f'id="review-card-{next_card.id}-answer"' in text


# --- validation ------------------------------------------------------------


def test_submit_answer_invalid_scope_rejected(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.post(
        f"/review/{card.id}/answer", data={"user_answer": "x", "scope": "bogus"}
    )

    assert response.status_code == 422


def test_submit_answer_other_users_card_returns_404(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    other = User(
        email="review-written-other@example.com",
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(other)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=other.id,
            daily_review_cap=_CAP,
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    db_session.refresh(other)

    subject = _make_subject(db_session, other.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)
    card = _make_card(db_session, source.id, folder.id, date.today())

    response = authed_client.post(
        f"/review/{card.id}/answer", data={"user_answer": "x", "scope": "global"}
    )

    assert response.status_code == 404


def test_grader_protocol_is_satisfied_by_fake() -> None:
    """Sanity check the fake used above actually satisfies the real protocol."""
    grader: WrittenAnswerGrader = _FakeGrader(
        outcome=WrittenAnswerOutcome(outcome="good", feedback="x")
    )
    result = grader.grade("q", "g", "u")
    assert result.outcome == "good"
