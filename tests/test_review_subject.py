"""HTTP-seam tests for the per-subject review route (ticket 09, issue #48).

Every test here proves the subject route reuses the *same*
``get_due_cards`` function the global route uses (via a monkeypatch spy for
the wiring assertion) and that it is genuinely uncapped, unlike the global
route.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Source, Subject, User, UserSettings

TEST_EMAIL = "review-subject-seam-test-user@example.com"
OTHER_EMAIL = "review-subject-seam-other-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"

_LOW_CAP = 2


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    now = datetime.now(UTC)
    user = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=user.id,
            daily_review_cap=_LOW_CAP,
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
            daily_review_cap=20,
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


def test_review_subject_shows_most_overdue_card_in_that_subject(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    my_subject: Subject,
) -> None:
    today = date.today()
    less_overdue = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=1), "Q-less", "A-less"
    )
    most_overdue = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=10), "Q-most", "A-most"
    )

    response = authed_client.get(f"/review/subjects/{my_subject.id}")

    assert response.status_code == 200
    text = response.text
    assert f"review-card-{most_overdue.id}-front" in text
    assert f"review-card-{less_overdue.id}-front" not in text


def test_review_subject_uncapped_reuses_get_due_cards_with_no_limit(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    my_subject: Subject,
    seeded_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """seeded_user's daily_review_cap is 2 -- seed more due cards than that
    in this one subject and assert the subject route calls the shared
    ``get_due_cards`` with ``limit=None`` (uncapped), not the user's cap.
    This is the mechanism (ticket 09 decision #4) that makes subject review
    genuinely uncapped rather than merely "happens to return enough"."""
    today = date.today()
    for i in range(_LOW_CAP + 3):
        _make_card(db_session, my_source.id, my_folder.id, today - timedelta(days=i))

    captured: dict[str, object] = {}
    import memory_ai.reviews.routes as routes_module

    original = routes_module.get_due_cards  # type: ignore[attr-defined]

    def _spy(session: Session, user_id: int, subject_id=None, limit=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["subject_id"] = subject_id
        captured["limit"] = limit
        return original(session, user_id, subject_id, limit, **kwargs)

    monkeypatch.setattr(routes_module, "get_due_cards", _spy)

    response = authed_client.get(f"/review/subjects/{my_subject.id}")

    assert response.status_code == 200
    assert captured["subject_id"] == my_subject.id
    assert captured["limit"] is None


def test_review_subject_no_due_cards_renders_subject_scoped_empty_state(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    my_subject: Subject,
) -> None:
    today = date.today()
    _make_card(db_session, my_source.id, my_folder.id, today + timedelta(days=1))

    response = authed_client.get(f"/review/subjects/{my_subject.id}")

    assert response.status_code == 200
    assert f"review-empty-subject-{my_subject.id}" in response.text
    assert "review-empty-global" not in response.text


def test_review_subject_for_other_users_subject_returns_404(
    authed_client: TestClient, db_session: Session, other_user: User
) -> None:
    their_subject = _make_subject(db_session, other_user.id, "Theirs")

    response = authed_client.get(f"/review/subjects/{their_subject.id}")

    assert response.status_code == 404


def test_review_subject_for_nonexistent_subject_returns_404(authed_client: TestClient) -> None:
    response = authed_client.get("/review/subjects/999999999")

    assert response.status_code == 404


def test_review_subject_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/review/subjects/1", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_review_subject_excludes_cards_from_other_subjects(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject_a = _make_subject(db_session, seeded_user.id, "Subject A")
    subject_b = _make_subject(db_session, seeded_user.id, "Subject B")
    _make_folder(db_session, subject_a.id, "Folder A")
    folder_b = _make_folder(db_session, subject_b.id, "Folder B")
    source_b = _make_source(db_session, folder_b.id, "b.txt")
    today = date.today()
    _make_card(db_session, source_b.id, folder_b.id, today, "Q-B", "A-B")

    response = authed_client.get(f"/review/subjects/{subject_a.id}")

    assert response.status_code == 200
    assert "Q-B" not in response.text
    assert f"review-empty-subject-{subject_a.id}" in response.text
