"""HTTP-seam tests for card listing routes (ticket 07, issue #72).

Covers per-source (`GET /sources/{id}/cards`) and per-folder
(`GET /folders/{id}/cards`) listing: happy path (front/back visible,
`created_at` ascending order), empty-list rendering, and cross-user 404s.

Seam: ticket 21's shared harness (`client` fixture: FastAPI `TestClient` +
real Postgres testcontainer + per-test transaction rollback via
`db_session`).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Source, Subject, User

TEST_EMAIL = "cards-view-seam-test-user@example.com"
OTHER_EMAIL = "cards-view-seam-other-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    user = User(
        email=TEST_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session: Session) -> User:
    user = User(
        email=OTHER_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
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
        raw_text="Some notes.",
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
    front: str,
    back: str,
    created_at: datetime,
) -> Card:
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
        due_date=created_at.date(),
        created_at=created_at,
    )
    db_session.add(card)
    db_session.commit()
    db_session.refresh(card)
    return card


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    return _make_subject(db_session, seeded_user.id, "System Design")


@pytest.fixture
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    return _make_folder(db_session, my_subject.id, "Caching")


@pytest.fixture
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Theirs")


# --- GET /sources/{source_id}/cards ----------------------------------------


def test_list_source_cards_shows_front_and_back_in_created_at_order(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id)
    base = datetime.now(UTC)
    first = _make_card(db_session, source.id, my_folder.id, "Q1", "A1", base)
    second = _make_card(
        db_session, source.id, my_folder.id, "Q2", "A2", base + timedelta(seconds=1)
    )

    response = authed_client.get(f"/sources/{source.id}/cards")

    assert response.status_code == 200
    text = response.text
    assert "Q1" in text and "A1" in text
    assert "Q2" in text and "A2" in text
    positions = [text.index(f"card-{c.id}") for c in (first, second)]
    assert positions == sorted(positions)


def test_list_source_cards_empty_source_renders_empty_state_no_error(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id)

    response = authed_client.get(f"/sources/{source.id}/cards")

    assert response.status_code == 200
    assert f"source-{source.id}-cards-empty" in response.text


def test_list_source_cards_for_other_users_source_returns_404(
    authed_client: TestClient, db_session: Session, their_folder: Folder
) -> None:
    theirs = _make_source(db_session, their_folder.id)

    response = authed_client.get(f"/sources/{theirs.id}/cards")

    assert response.status_code == 404


def test_list_source_cards_for_nonexistent_source_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/sources/999999999/cards")

    assert response.status_code == 404


def test_list_source_cards_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/sources/1/cards", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_list_source_cards_only_includes_cards_from_that_source(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source_a = _make_source(db_session, my_folder.id, "a.txt")
    source_b = _make_source(db_session, my_folder.id, "b.txt")
    _make_card(db_session, source_a.id, my_folder.id, "Q-A", "A-A", datetime.now(UTC))
    _make_card(db_session, source_b.id, my_folder.id, "Q-B", "A-B", datetime.now(UTC))

    response = authed_client.get(f"/sources/{source_a.id}/cards")

    assert response.status_code == 200
    assert "Q-A" in response.text
    assert "Q-B" not in response.text


# --- GET /folders/{folder_id}/cards ----------------------------------------


def test_list_folder_cards_aggregates_across_sources_in_created_at_order(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source_a = _make_source(db_session, my_folder.id, "a.txt")
    source_b = _make_source(db_session, my_folder.id, "b.txt")
    base = datetime.now(UTC)
    first = _make_card(db_session, source_a.id, my_folder.id, "Q1", "A1", base)
    second = _make_card(
        db_session, source_b.id, my_folder.id, "Q2", "A2", base + timedelta(seconds=1)
    )

    response = authed_client.get(f"/folders/{my_folder.id}/cards")

    assert response.status_code == 200
    text = response.text
    assert "Q1" in text and "A1" in text
    assert "Q2" in text and "A2" in text
    positions = [text.index(f"card-{c.id}") for c in (first, second)]
    assert positions == sorted(positions)


def test_list_folder_cards_empty_folder_renders_empty_state_no_error(
    authed_client: TestClient, my_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{my_folder.id}/cards")

    assert response.status_code == 200
    assert f"folder-{my_folder.id}-cards-empty" in response.text


def test_list_folder_cards_for_other_users_folder_returns_404(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{their_folder.id}/cards")

    assert response.status_code == 404


def test_list_folder_cards_for_nonexistent_folder_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/folders/999999999/cards")

    assert response.status_code == 404


def test_list_folder_cards_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/folders/1/cards", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_list_folder_cards_excludes_cards_from_other_folders(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder_a = _make_folder(db_session, my_subject.id, "Folder A")
    folder_b = _make_folder(db_session, my_subject.id, "Folder B")
    source_a = _make_source(db_session, folder_a.id, "a.txt")
    source_b = _make_source(db_session, folder_b.id, "b.txt")
    _make_card(db_session, source_a.id, folder_a.id, "Q-A", "A-A", datetime.now(UTC))
    _make_card(db_session, source_b.id, folder_b.id, "Q-B", "A-B", datetime.now(UTC))

    response = authed_client.get(f"/folders/{folder_a.id}/cards")

    assert response.status_code == 200
    assert "Q-A" in response.text
    assert "Q-B" not in response.text


# --- GET /cards/{card_id} (single-card display fragment) --------------------


def test_view_card_returns_row_fragment_for_owner(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id)
    card = _make_card(db_session, source.id, my_folder.id, "Front Q", "Back A", datetime.now(UTC))

    response = authed_client.get(f"/cards/{card.id}")

    assert response.status_code == 200
    assert f"card-{card.id}" in response.text
    assert "Front Q" in response.text
    assert "Back A" in response.text


def test_view_card_for_other_users_card_returns_404_not_403(
    authed_client: TestClient, db_session: Session, their_folder: Folder
) -> None:
    """A card owned (via the source->folder->subject chain) by another user
    must be indistinguishable from a nonexistent one: a plain 404, never 403."""
    their_source = _make_source(db_session, their_folder.id)
    their_card = _make_card(
        db_session, their_source.id, their_folder.id, "Secret", "Answer", datetime.now(UTC)
    )

    response = authed_client.get(f"/cards/{their_card.id}")

    assert response.status_code == 404
    assert response.status_code != 403
    assert "Secret" not in response.text


def test_view_nonexistent_card_returns_404(authed_client: TestClient) -> None:
    response = authed_client.get("/cards/999999999")

    assert response.status_code == 404


def test_view_card_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/cards/1", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
