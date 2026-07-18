"""HTTP-seam tests for the global daily review route (ticket 09, issue #44).

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

TEST_EMAIL = "review-global-seam-test-user@example.com"
OTHER_EMAIL = "review-global-seam-other-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    now = datetime.now(UTC)
    user = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=user.id,
            daily_review_cap=2,
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


def test_review_global_shows_most_overdue_card_front(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    less_overdue = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=1), "Q-less", "A-less"
    )
    most_overdue = _make_card(
        db_session, my_source.id, my_folder.id, today - timedelta(days=10), "Q-most", "A-most"
    )

    response = authed_client.get("/review")

    assert response.status_code == 200
    text = response.text
    assert f"review-card-{most_overdue.id}-front" in text
    assert "Q-most" in text
    assert f"review-card-{less_overdue.id}-front" not in text
    # Only the front is shown -- the back must not leak before "Show answer".
    assert "A-most" not in text


def test_review_global_no_due_cards_renders_empty_state(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    today = date.today()
    _make_card(db_session, my_source.id, my_folder.id, today + timedelta(days=1))

    response = authed_client.get("/review")

    assert response.status_code == 200
    assert "review-empty-global" in response.text
    assert "You&#39;re all caught up" in response.text or "You're all caught up" in response.text


def test_review_global_zero_cards_at_all_renders_empty_state(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/review")

    assert response.status_code == 200
    assert "review-empty-global" in response.text


def test_review_global_route_passes_users_daily_cap_as_limit(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    seeded_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """seeded_user's ``daily_review_cap`` is 2 -- assert the route passes it
    straight through to ``get_due_cards`` as ``limit`` (uncapped grading
    isn't wired until issue #51, so a full "exactly N cards over a session"
    drain test isn't possible yet; this directly proves the route wires the
    cap it read from the DB into the shared query's ``limit`` -- the actual
    LIMIT enforcement itself is covered at the query level in
    ``test_review_queries.py``)."""
    today = date.today()
    for i in range(4):
        _make_card(db_session, my_source.id, my_folder.id, today - timedelta(days=i))

    captured: dict[str, object] = {}
    import memory_ai.reviews.routes as routes_module

    original = routes_module.get_due_cards  # type: ignore[attr-defined]

    def _spy(session: Session, user_id: int, subject_id: int | None = None, limit=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["user_id"] = user_id
        captured["subject_id"] = subject_id
        captured["limit"] = limit
        return original(session, user_id, subject_id, limit, **kwargs)

    monkeypatch.setattr(routes_module, "get_due_cards", _spy)

    response = authed_client.get("/review")

    assert response.status_code == 200
    assert captured["user_id"] == seeded_user.id
    assert captured["subject_id"] is None
    assert captured["limit"] == 2


def test_review_global_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/review", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_review_global_only_shows_current_users_cards(
    authed_client: TestClient,
    db_session: Session,
    other_user: User,
) -> None:
    other_subject = _make_subject(db_session, other_user.id, "Theirs")
    other_folder = _make_folder(db_session, other_subject.id)
    other_source = _make_source(db_session, other_folder.id)
    today = date.today()
    _make_card(
        db_session, other_source.id, other_folder.id, today, "Not-mine-front", "Not-mine-back"
    )

    response = authed_client.get("/review")

    assert response.status_code == 200
    assert "Not-mine-front" not in response.text
    assert "review-empty-global" in response.text
