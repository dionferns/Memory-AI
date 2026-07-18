"""HTTP-seam tests for inline card edit (ticket 07, issue #75).

Covers `GET /cards/{id}/edit` (edit-form swap), `PATCH /cards/{id}`
(front/back update), empty/whitespace-only field rejection, the
byte-for-byte-unchanged guarantee on every SM-2 scheduling column, and
cross-user/nonexistent-id 404s.

Seam: ticket 21's shared harness (`client` fixture: FastAPI `TestClient` +
real Postgres testcontainer + per-test transaction rollback via
`db_session`).
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Source, Subject, User

TEST_EMAIL = "cards-edit-seam-test-user@example.com"
OTHER_EMAIL = "cards-edit-seam-other-user@example.com"
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


_SCHEDULING_COLUMNS = (
    "ease_factor",
    "interval_days",
    "repetitions",
    "due_date",
    "last_reviewed_at",
)


def _make_card(
    db_session: Session,
    source_id: int,
    folder_id: int,
    front: str = "Original front",
    back: str = "Original back",
) -> Card:
    # Deliberately non-default scheduling values so a byte-for-byte diff
    # after edit actually proves the route left them alone, rather than
    # coincidentally matching fresh defaults.
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=2.3,
        interval_days=6,
        repetitions=3,
        due_date=date(2026, 8, 1),
        last_reviewed_at=datetime(2026, 7, 10, 12, 30, tzinfo=UTC),
        created_at=datetime.now(UTC) - timedelta(days=1),
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
def my_source(db_session: Session, my_folder: Folder) -> Source:
    return _make_source(db_session, my_folder.id)


@pytest.fixture
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Theirs")


@pytest.fixture
def their_source(db_session: Session, their_folder: Folder) -> Source:
    return _make_source(db_session, their_folder.id)


def _fresh_card(db_session: Session, card_id: int) -> Card:
    db_session.expire_all()
    return db_session.execute(select(Card).where(Card.id == card_id)).scalar_one()


# --- GET /cards/{id}/edit ---------------------------------------------------


def test_edit_card_form_renders_current_front_and_back(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, "Q?", "A!")

    response = authed_client.get(f"/cards/{card.id}/edit")

    assert response.status_code == 200
    assert "Q?" in response.text
    assert "A!" in response.text
    assert f'hx-patch="/cards/{card.id}"' in response.text


def test_edit_card_form_for_other_users_card_returns_404(
    authed_client: TestClient, db_session: Session, their_source: Source, their_folder: Folder
) -> None:
    theirs = _make_card(db_session, their_source.id, their_folder.id)

    response = authed_client.get(f"/cards/{theirs.id}/edit")

    assert response.status_code == 404


def test_edit_card_form_for_nonexistent_card_returns_404(authed_client: TestClient) -> None:
    response = authed_client.get("/cards/999999999/edit")

    assert response.status_code == 404


# --- PATCH /cards/{id} -------------------------------------------------------


def test_update_card_with_valid_front_back_persists_and_returns_display_partial(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, "Old front", "Old back")

    response = authed_client.patch(
        f"/cards/{card.id}", data={"front": "New front", "back": "New back"}
    )

    assert response.status_code == 200
    assert "New front" in response.text
    assert "New back" in response.text
    # Returned partial should be the display row, not the edit form.
    assert f'hx-get="/cards/{card.id}/edit"' in response.text
    assert f'hx-patch="/cards/{card.id}"' not in response.text

    updated = _fresh_card(db_session, card.id)
    assert updated.front == "New front"
    assert updated.back == "New back"


def test_update_card_trims_whitespace(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id)

    authed_client.patch(f"/cards/{card.id}", data={"front": "  Padded  ", "back": "  Also  "})

    updated = _fresh_card(db_session, card.id)
    assert updated.front == "Padded"
    assert updated.back == "Also"


@pytest.mark.parametrize(
    "front,back",
    [
        ("", "Valid back"),
        ("   ", "Valid back"),
        ("Valid front", ""),
        ("Valid front", "   "),
        ("", ""),
    ],
)
def test_update_card_empty_or_whitespace_field_rejected_and_not_persisted(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    my_folder: Folder,
    front: str,
    back: str,
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, "Keep front", "Keep back")

    response = authed_client.patch(f"/cards/{card.id}", data={"front": front, "back": back})

    assert response.status_code == 200
    assert "required" in response.text.lower()
    # Rejected submission re-renders the edit form (not the display row), so
    # the user can fix the input without losing their in-progress edit.
    assert f'hx-patch="/cards/{card.id}"' in response.text

    unchanged = _fresh_card(db_session, card.id)
    assert unchanged.front == "Keep front"
    assert unchanged.back == "Keep back"


def test_update_card_leaves_every_scheduling_column_byte_for_byte_unchanged(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id)
    before = {col: getattr(card, col) for col in _SCHEDULING_COLUMNS}

    response = authed_client.patch(
        f"/cards/{card.id}", data={"front": "Edited front", "back": "Edited back"}
    )

    assert response.status_code == 200
    after = _fresh_card(db_session, card.id)
    for col in _SCHEDULING_COLUMNS:
        assert getattr(after, col) == before[col], (
            f"{col} changed: {before[col]!r} -> {getattr(after, col)!r}"
        )
    # Sanity: front/back themselves *did* change, proving this isn't a
    # no-op update that trivially "preserves" everything.
    assert after.front == "Edited front"
    assert after.back == "Edited back"


def test_update_other_users_card_returns_404_and_leaves_it_unchanged(
    authed_client: TestClient, db_session: Session, their_source: Source, their_folder: Folder
) -> None:
    theirs = _make_card(db_session, their_source.id, their_folder.id, "Theirs front", "Theirs back")

    response = authed_client.patch(
        f"/cards/{theirs.id}", data={"front": "Hijacked", "back": "Hijacked"}
    )

    assert response.status_code == 404

    unchanged = _fresh_card(db_session, theirs.id)
    assert unchanged.front == "Theirs front"
    assert unchanged.back == "Theirs back"


def test_update_nonexistent_card_returns_404(authed_client: TestClient) -> None:
    response = authed_client.patch("/cards/999999999", data={"front": "X", "back": "Y"})

    assert response.status_code == 404


def test_update_card_unauthenticated_redirects(client: TestClient) -> None:
    response = client.patch("/cards/1", data={"front": "X", "back": "Y"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_edit_card_form_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/cards/1/edit", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
