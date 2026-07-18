"""HTTP-seam tests for subject CRUD + the `GET /subjects` hierarchy page
(ticket 04, issue #85).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Subject, User

TEST_EMAIL = "subjects-seam-test-user@example.com"
OTHER_EMAIL = "subjects-seam-other-user@example.com"
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


def _make_subject(db_session: Session, user_id: int, name: str, created_at: datetime) -> Subject:
    subject = Subject(user_id=user_id, name=name, created_at=created_at)
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)
    return subject


# --- GET /subjects (page) -------------------------------------------------


def test_get_subjects_unauthenticated_redirects_to_login(client: TestClient) -> None:
    response = client.get("/subjects", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_get_subjects_empty_state_shows_message_and_create_form(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")

    assert response.status_code == 200
    assert "subjects-empty-state" in response.text
    assert 'id="create-subject-form"' in response.text


def test_get_subjects_lists_subjects_in_creation_order(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    base = datetime.now(UTC)
    first = _make_subject(db_session, seeded_user.id, "Alpha", base)
    second = _make_subject(db_session, seeded_user.id, "Beta", base + timedelta(seconds=1))
    third = _make_subject(db_session, seeded_user.id, "Gamma", base + timedelta(seconds=2))

    response = authed_client.get("/subjects")

    assert response.status_code == 200
    text = response.text
    assert "subjects-empty-state" not in text
    positions = [text.index(f"subject-{s.id}-name") for s in (first, second, third)]
    assert positions == sorted(positions)


def test_get_subjects_only_shows_current_users_subjects(
    authed_client: TestClient, db_session: Session, seeded_user: User, other_user: User
) -> None:
    mine = _make_subject(db_session, seeded_user.id, "Mine", datetime.now(UTC))
    _make_subject(db_session, other_user.id, "Not Mine", datetime.now(UTC))

    response = authed_client.get("/subjects")

    assert f"subject-{mine.id}-name" in response.text
    assert "Not Mine" not in response.text


# --- POST /subjects (create) ----------------------------------------------


def test_create_subject_persists_and_appears_in_list(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = authed_client.post("/subjects", data={"name": "System Design"})

    assert response.status_code == 200
    assert "System Design" in response.text

    subject = db_session.execute(
        select(Subject).where(Subject.user_id == seeded_user.id)
    ).scalar_one()
    assert subject.name == "System Design"


def test_create_subject_trims_whitespace(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    authed_client.post("/subjects", data={"name": "  Caching  "})

    subject = db_session.execute(
        select(Subject).where(Subject.user_id == seeded_user.id)
    ).scalar_one()
    assert subject.name == "Caching"


def test_create_subject_blank_name_rejected_with_inline_error(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = authed_client.post("/subjects", data={"name": "   "})

    assert response.status_code == 200
    assert "required" in response.text.lower()
    count = db_session.execute(select(Subject).where(Subject.user_id == seeded_user.id)).all()
    assert count == []


def test_create_subject_too_long_name_rejected_with_inline_error(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = authed_client.post("/subjects", data={"name": "x" * 201})

    assert response.status_code == 200
    assert "200 characters" in response.text
    count = db_session.execute(select(Subject).where(Subject.user_id == seeded_user.id)).all()
    assert count == []


def test_create_subject_exactly_200_chars_is_accepted(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    name = "x" * 200
    response = authed_client.post("/subjects", data={"name": name})

    assert response.status_code == 200
    subject = db_session.execute(
        select(Subject).where(Subject.user_id == seeded_user.id)
    ).scalar_one()
    assert subject.name == name


def test_create_subject_duplicate_names_allowed(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    authed_client.post("/subjects", data={"name": "Repeat"})
    authed_client.post("/subjects", data={"name": "Repeat"})

    subjects = (
        db_session.execute(select(Subject).where(Subject.user_id == seeded_user.id)).scalars().all()
    )
    assert len(subjects) == 2


def test_create_subject_unauthenticated_redirects(client: TestClient) -> None:
    response = client.post("/subjects", data={"name": "Nope"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


# --- GET /subjects/{id}/edit + GET /subjects/{id} (rename UI) ------------


def test_edit_subject_form_renders_input_with_current_name(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "Old Name", datetime.now(UTC))

    response = authed_client.get(f"/subjects/{subject.id}/edit")

    assert response.status_code == 200
    assert "Old Name" in response.text
    assert f'hx-patch="/subjects/{subject.id}"' in response.text


def test_view_subject_returns_display_fragment(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "Some Subject", datetime.now(UTC))

    response = authed_client.get(f"/subjects/{subject.id}")

    assert response.status_code == 200
    assert "Some Subject" in response.text
    assert f'hx-get="/subjects/{subject.id}/edit"' in response.text


def test_edit_subject_form_for_nonexistent_subject_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects/999999999/edit")

    assert response.status_code == 404


def test_edit_subject_form_for_other_users_subject_returns_404(
    authed_client: TestClient, db_session: Session, other_user: User
) -> None:
    theirs = _make_subject(db_session, other_user.id, "Theirs", datetime.now(UTC))

    response = authed_client.get(f"/subjects/{theirs.id}/edit")

    assert response.status_code == 404


# --- PATCH /subjects/{id} (rename) ----------------------------------------


def test_rename_subject_updates_name_and_returns_display_fragment(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "Before", datetime.now(UTC))

    response = authed_client.patch(f"/subjects/{subject.id}", data={"name": "After"})

    assert response.status_code == 200
    assert "After" in response.text
    assert f'hx-get="/subjects/{subject.id}/edit"' in response.text

    db_session.refresh(subject)
    assert subject.name == "After"


def test_rename_subject_blank_name_rejected_and_not_persisted(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "Keep Me", datetime.now(UTC))

    response = authed_client.patch(f"/subjects/{subject.id}", data={"name": "   "})

    assert response.status_code == 200
    assert "required" in response.text.lower()

    db_session.refresh(subject)
    assert subject.name == "Keep Me"


def test_rename_subject_too_long_rejected_and_not_persisted(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "Keep Me", datetime.now(UTC))

    response = authed_client.patch(f"/subjects/{subject.id}", data={"name": "y" * 201})

    assert response.status_code == 200
    assert "200 characters" in response.text

    db_session.refresh(subject)
    assert subject.name == "Keep Me"


def test_rename_other_users_subject_returns_404_and_leaves_it_unchanged(
    authed_client: TestClient, db_session: Session, other_user: User
) -> None:
    theirs = _make_subject(db_session, other_user.id, "Theirs", datetime.now(UTC))

    response = authed_client.patch(f"/subjects/{theirs.id}", data={"name": "Hijacked"})

    assert response.status_code == 404

    db_session.refresh(theirs)
    assert theirs.name == "Theirs"


def test_rename_nonexistent_subject_returns_404(authed_client: TestClient) -> None:
    response = authed_client.patch("/subjects/999999999", data={"name": "Whatever"})

    assert response.status_code == 404


# --- DELETE /subjects/{id} -------------------------------------------------


def test_delete_subject_removes_it_and_returns_empty_body(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "Doomed", datetime.now(UTC))

    response = authed_client.delete(f"/subjects/{subject.id}")

    assert response.status_code == 200
    assert response.text == ""

    remaining = db_session.execute(
        select(Subject).where(Subject.id == subject.id)
    ).scalar_one_or_none()
    assert remaining is None


def test_delete_other_users_subject_returns_404_and_does_not_delete_it(
    authed_client: TestClient, db_session: Session, other_user: User
) -> None:
    theirs = _make_subject(db_session, other_user.id, "Theirs", datetime.now(UTC))

    response = authed_client.delete(f"/subjects/{theirs.id}")

    assert response.status_code == 404

    still_there = db_session.execute(
        select(Subject).where(Subject.id == theirs.id)
    ).scalar_one_or_none()
    assert still_there is not None


def test_delete_nonexistent_subject_returns_404(authed_client: TestClient) -> None:
    response = authed_client.delete("/subjects/999999999")

    assert response.status_code == 404


def test_delete_subject_unauthenticated_redirects(client: TestClient) -> None:
    response = client.delete("/subjects/1", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
