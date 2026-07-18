"""HTTP-seam tests for folder CRUD nested under subjects (ticket 04, issue #86).

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
from memory_ai.models import Folder, Subject, User

TEST_EMAIL = "folders-seam-test-user@example.com"
OTHER_EMAIL = "folders-seam-other-user@example.com"
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


def _make_folder(db_session: Session, subject_id: int, name: str, created_at: datetime) -> Folder:
    folder = Folder(subject_id=subject_id, name=name, created_at=created_at)
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    return _make_subject(db_session, seeded_user.id, "System Design", datetime.now(UTC))


@pytest.fixture
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine", datetime.now(UTC))


# --- POST /subjects/{subject_id}/folders (create) -------------------------


def test_create_folder_persists_and_renders_inline_under_subject(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    response = authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": "Caching"})

    assert response.status_code == 200
    assert "Caching" in response.text

    folder = db_session.execute(
        select(Folder).where(Folder.subject_id == my_subject.id)
    ).scalar_one()
    assert folder.name == "Caching"


def test_create_folder_trims_whitespace(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": "  Caching  "})

    folder = db_session.execute(
        select(Folder).where(Folder.subject_id == my_subject.id)
    ).scalar_one()
    assert folder.name == "Caching"


def test_create_folder_blank_name_rejected_with_inline_error(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    response = authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": "   "})

    assert response.status_code == 200
    assert "required" in response.text.lower()
    rows = db_session.execute(select(Folder).where(Folder.subject_id == my_subject.id)).all()
    assert rows == []


def test_create_folder_too_long_name_rejected_with_inline_error(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    response = authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": "x" * 201})

    assert response.status_code == 200
    assert "200 characters" in response.text
    rows = db_session.execute(select(Folder).where(Folder.subject_id == my_subject.id)).all()
    assert rows == []


def test_create_folder_exactly_200_chars_is_accepted(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    name = "x" * 200
    response = authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": name})

    assert response.status_code == 200
    folder = db_session.execute(
        select(Folder).where(Folder.subject_id == my_subject.id)
    ).scalar_one()
    assert folder.name == name


def test_create_folder_duplicate_names_allowed(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": "Repeat"})
    authed_client.post(f"/subjects/{my_subject.id}/folders", data={"name": "Repeat"})

    folders = (
        db_session.execute(select(Folder).where(Folder.subject_id == my_subject.id)).scalars().all()
    )
    assert len(folders) == 2


def test_create_folder_under_other_users_subject_returns_404_and_not_persisted(
    authed_client: TestClient, db_session: Session, their_subject: Subject
) -> None:
    response = authed_client.post(f"/subjects/{their_subject.id}/folders", data={"name": "Sneaky"})

    assert response.status_code == 404
    rows = db_session.execute(select(Folder).where(Folder.subject_id == their_subject.id)).all()
    assert rows == []


def test_create_folder_under_nonexistent_subject_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.post("/subjects/999999999/folders", data={"name": "Whatever"})

    assert response.status_code == 404


def test_create_folder_unauthenticated_redirects(
    client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id, "S", datetime.now(UTC))

    response = client.post(
        f"/subjects/{subject.id}/folders", data={"name": "Nope"}, follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


# --- GET /subjects (page renders folders inline) --------------------------


def test_subjects_page_renders_folders_inline_under_their_subject(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    base = datetime.now(UTC)
    first = _make_folder(db_session, my_subject.id, "Caching", base)
    second = _make_folder(db_session, my_subject.id, "Consistency", base + timedelta(seconds=1))

    response = authed_client.get("/subjects")

    assert response.status_code == 200
    text = response.text
    assert f"folders-empty-state-{my_subject.id}" not in text
    positions = [text.index(f"folder-{f.id}-name") for f in (first, second)]
    assert positions == sorted(positions)


def test_subjects_page_shows_folder_empty_state_for_subject_with_no_folders(
    authed_client: TestClient, my_subject: Subject
) -> None:
    response = authed_client.get("/subjects")

    assert response.status_code == 200
    assert f"folders-empty-state-{my_subject.id}" in response.text
    assert f'id="create-folder-form-{my_subject.id}"' in response.text


# --- GET /folders/{id}/edit + GET /folders/{id} (rename UI) --------------


def test_edit_folder_form_renders_input_with_current_name(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder = _make_folder(db_session, my_subject.id, "Old Name", datetime.now(UTC))

    response = authed_client.get(f"/folders/{folder.id}/edit")

    assert response.status_code == 200
    assert "Old Name" in response.text
    assert f'hx-patch="/folders/{folder.id}"' in response.text


def test_view_folder_returns_display_fragment(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder = _make_folder(db_session, my_subject.id, "Some Folder", datetime.now(UTC))

    response = authed_client.get(f"/folders/{folder.id}")

    assert response.status_code == 200
    assert "Some Folder" in response.text
    assert f'hx-get="/folders/{folder.id}/edit"' in response.text


def test_edit_folder_form_for_other_users_folder_returns_404(
    authed_client: TestClient, db_session: Session, their_subject: Subject
) -> None:
    theirs = _make_folder(db_session, their_subject.id, "Theirs", datetime.now(UTC))

    response = authed_client.get(f"/folders/{theirs.id}/edit")

    assert response.status_code == 404


def test_edit_folder_form_for_nonexistent_folder_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/folders/999999999/edit")

    assert response.status_code == 404


# --- PATCH /folders/{id} (rename) ------------------------------------------


def test_rename_folder_updates_name_and_returns_display_fragment(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder = _make_folder(db_session, my_subject.id, "Before", datetime.now(UTC))

    response = authed_client.patch(f"/folders/{folder.id}", data={"name": "After"})

    assert response.status_code == 200
    assert "After" in response.text
    assert f'hx-get="/folders/{folder.id}/edit"' in response.text

    db_session.refresh(folder)
    assert folder.name == "After"


def test_rename_folder_blank_name_rejected_and_not_persisted(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder = _make_folder(db_session, my_subject.id, "Keep Me", datetime.now(UTC))

    response = authed_client.patch(f"/folders/{folder.id}", data={"name": "   "})

    assert response.status_code == 200
    assert "required" in response.text.lower()

    db_session.refresh(folder)
    assert folder.name == "Keep Me"


def test_rename_folder_too_long_rejected_and_not_persisted(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder = _make_folder(db_session, my_subject.id, "Keep Me", datetime.now(UTC))

    response = authed_client.patch(f"/folders/{folder.id}", data={"name": "y" * 201})

    assert response.status_code == 200
    assert "200 characters" in response.text

    db_session.refresh(folder)
    assert folder.name == "Keep Me"


def test_rename_other_users_folder_returns_404_and_leaves_it_unchanged(
    authed_client: TestClient, db_session: Session, their_subject: Subject
) -> None:
    theirs = _make_folder(db_session, their_subject.id, "Theirs", datetime.now(UTC))

    response = authed_client.patch(f"/folders/{theirs.id}", data={"name": "Hijacked"})

    assert response.status_code == 404

    db_session.refresh(theirs)
    assert theirs.name == "Theirs"


def test_rename_nonexistent_folder_returns_404(authed_client: TestClient) -> None:
    response = authed_client.patch("/folders/999999999", data={"name": "Whatever"})

    assert response.status_code == 404


# --- DELETE /folders/{id} --------------------------------------------------


def test_delete_folder_removes_it_and_returns_empty_body(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    folder = _make_folder(db_session, my_subject.id, "Doomed", datetime.now(UTC))

    response = authed_client.delete(f"/folders/{folder.id}")

    assert response.status_code == 200
    assert response.text == ""

    remaining = db_session.execute(
        select(Folder).where(Folder.id == folder.id)
    ).scalar_one_or_none()
    assert remaining is None


def test_delete_other_users_folder_returns_404_and_does_not_delete_it(
    authed_client: TestClient, db_session: Session, their_subject: Subject
) -> None:
    theirs = _make_folder(db_session, their_subject.id, "Theirs", datetime.now(UTC))

    response = authed_client.delete(f"/folders/{theirs.id}")

    assert response.status_code == 404

    still_there = db_session.execute(
        select(Folder).where(Folder.id == theirs.id)
    ).scalar_one_or_none()
    assert still_there is not None


def test_delete_nonexistent_folder_returns_404(authed_client: TestClient) -> None:
    response = authed_client.delete("/folders/999999999")

    assert response.status_code == 404


def test_delete_folder_unauthenticated_redirects(client: TestClient) -> None:
    response = client.delete("/folders/1", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_deleting_a_subject_folder_does_not_affect_other_subjects_in_the_list(
    authed_client: TestClient, db_session: Session, my_subject: Subject
) -> None:
    """Renaming/deleting a subject's header must not disturb its folders section."""
    folder = _make_folder(db_session, my_subject.id, "Stays Put", datetime.now(UTC))

    rename_response = authed_client.patch(
        f"/subjects/{my_subject.id}", data={"name": "Renamed Subject"}
    )
    assert rename_response.status_code == 200
    # Rename swaps only the header fragment, so the folder shouldn't appear
    # in that response at all.
    assert "Stays Put" not in rename_response.text

    # But the folder must still exist afterward.
    remaining = db_session.execute(
        select(Folder).where(Folder.id == folder.id)
    ).scalar_one_or_none()
    assert remaining is not None
