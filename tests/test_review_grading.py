"""HTTP-seam tests for grading (ticket 09, issue #51).

Covers: "Show answer" reveal (front-only -> back + grade buttons), the
grade happy path (updates ``due_date``/``interval_days``/etc. via ticket
08's ``apply_grade_to_card``, writes a ``reviews`` row), next-card advance
within the same scope, the empty-state transition after grading the last
due card, cross-user rejection, and that grading never touches a card's
front/back content.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Review, Source, Subject, User, UserSettings

TEST_EMAIL = "review-grading-seam-test-user@example.com"
OTHER_EMAIL = "review-grading-seam-other-user@example.com"
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
def other_user(db_session: Session) -> User:
    now = datetime.now(UTC)
    user = User(email=OTHER_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
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
    interval_days: int = 0,
    repetitions: int = 0,
) -> Card:
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


# --- GET /review/{card_id}/reveal ------------------------------------------


def test_reveal_shows_back_and_four_grade_buttons(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    card = _make_card(db_session, my_source.id, my_folder.id, today, "The Q", "The A")

    response = authed_client.get(f"/review/{card.id}/reveal?scope=global")

    assert response.status_code == 200
    text = response.text
    assert f"review-card-{card.id}-back" in text
    assert "The A" in text
    for grade in ("again", "hard", "good", "easy"):
        assert f"grade-{grade}-{card.id}" in text


def test_reveal_other_users_card_returns_404(
    authed_client: TestClient, db_session: Session, other_user: User
) -> None:
    subject = _make_subject(db_session, other_user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)
    card = _make_card(db_session, source.id, folder.id, date.today())

    response = authed_client.get(f"/review/{card.id}/reveal?scope=global")

    assert response.status_code == 404


def test_reveal_invalid_scope_rejected(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.get(f"/review/{card.id}/reveal?scope=bogus")

    assert response.status_code == 422


def test_reveal_subject_scope_missing_subject_id_rejected(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.get(f"/review/{card.id}/reveal?scope=subject")

    assert response.status_code == 422


def test_reveal_subject_scope_with_other_users_subject_id_returns_404(
    authed_client: TestClient,
    db_session: Session,
    other_user: User,
    my_source: Source,
    my_folder: Folder,
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())
    their_subject = _make_subject(db_session, other_user.id, "Theirs")

    response = authed_client.get(
        f"/review/{card.id}/reveal?scope=subject&subject_id={their_subject.id}"
    )

    assert response.status_code == 404


# --- POST /review/grade/{card_id} ------------------------------------------


def test_grade_updates_card_scheduling_state_and_writes_review(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    card = _make_card(
        db_session,
        my_source.id,
        my_folder.id,
        today,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
    )

    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "good", "scope": "global"}
    )

    assert response.status_code == 200

    db_session.expire_all()
    updated = db_session.get(Card, card.id)
    assert updated is not None
    assert updated.repetitions == 1
    assert updated.interval_days == 1
    assert updated.due_date == today + timedelta(days=1)
    assert updated.last_reviewed_at is not None

    reviews = db_session.execute(select(Review).where(Review.card_id == card.id)).scalars().all()
    assert len(reviews) == 1
    assert reviews[0].grade == "good"
    assert reviews[0].prev_interval_days == 0
    assert reviews[0].new_interval_days == 1


def test_grade_does_not_touch_front_or_back_content(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    card = _make_card(db_session, my_source.id, my_folder.id, today, "Unchanged Q", "Unchanged A")

    authed_client.post(f"/review/grade/{card.id}", data={"grade": "again", "scope": "global"})

    db_session.expire_all()
    updated = db_session.get(Card, card.id)
    assert updated is not None
    assert updated.front == "Unchanged Q"
    assert updated.back == "Unchanged A"


def test_grade_global_scope_advances_to_next_most_overdue_card(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    most_overdue = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=10), "Q-most", "A-most"
    )
    next_overdue = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=5), "Q-next", "A-next"
    )

    response = authed_client.post(
        f"/review/grade/{most_overdue.id}", data={"grade": "good", "scope": "global"}
    )

    assert response.status_code == 200
    text = response.text
    assert f"review-card-{next_overdue.id}-front" in text
    assert f"review-card-{most_overdue.id}-front" not in text


def test_grade_last_due_card_transitions_to_global_empty_state(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    only_card = _make_card(db_session, my_source.id, my_folder.id, today)

    response = authed_client.post(
        f"/review/grade/{only_card.id}", data={"grade": "easy", "scope": "global"}
    )

    assert response.status_code == 200
    assert "review-empty-global" in response.text


def test_grade_subject_scope_advances_within_that_subject(
    authed_client: TestClient,
    db_session: Session,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    today = date.today()
    most_overdue = _make_card(db_session, my_source.id, my_folder.id, today - timedelta(days=10))
    next_overdue = _make_card(db_session, my_source.id, my_folder.id, today - timedelta(days=5))

    response = authed_client.post(
        f"/review/grade/{most_overdue.id}",
        data={"grade": "good", "scope": "subject", "subject_id": str(my_subject.id)},
    )

    assert response.status_code == 200
    text = response.text
    assert f"review-card-{next_overdue.id}-front" in text


def test_grade_last_due_card_in_subject_transitions_to_subject_empty_state(
    authed_client: TestClient,
    db_session: Session,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    today = date.today()
    only_card = _make_card(db_session, my_source.id, my_folder.id, today)

    response = authed_client.post(
        f"/review/grade/{only_card.id}",
        data={"grade": "again", "scope": "subject", "subject_id": str(my_subject.id)},
    )

    assert response.status_code == 200
    assert f"review-empty-subject-{my_subject.id}" in response.text


def test_grade_other_users_card_returns_404(
    authed_client: TestClient, db_session: Session, other_user: User
) -> None:
    subject = _make_subject(db_session, other_user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)
    card = _make_card(db_session, source.id, folder.id, date.today())

    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "good", "scope": "global"}
    )

    assert response.status_code == 404

    db_session.expire_all()
    unchanged = db_session.get(Card, card.id)
    assert unchanged is not None
    assert unchanged.repetitions == 0


def test_grade_invalid_grade_value_rejected(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "excellent", "scope": "global"}
    )

    assert response.status_code == 422

    db_session.expire_all()
    unchanged = db_session.get(Card, card.id)
    assert unchanged is not None
    assert unchanged.repetitions == 0


def test_grade_invalid_scope_rejected(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "good", "scope": "bogus"}
    )

    assert response.status_code == 422

    db_session.expire_all()
    unchanged = db_session.get(Card, card.id)
    assert unchanged is not None
    assert unchanged.repetitions == 0


def test_grade_subject_scope_missing_subject_id_rejected(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, date.today())

    response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "good", "scope": "subject"}
    )

    assert response.status_code == 422

    db_session.expire_all()
    unchanged = db_session.get(Card, card.id)
    assert unchanged is not None
    assert unchanged.repetitions == 0


def test_grade_unauthenticated_redirects(client: TestClient) -> None:
    response = client.post(
        "/review/grade/1", data={"grade": "good", "scope": "global"}, follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
