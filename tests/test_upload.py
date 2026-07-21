"""HTTP-seam tests for uploading notes into a folder (ticket 05, issue #52).

Covers the happy path only: a valid PDF/MD/TXT upload creates a `sources`
row and swaps in the refreshed sources list, ownership is enforced the same
way ticket 04's folder routes enforce it, and unauthenticated requests are
rejected by the existing `current_user` dependency. Rejection-path coverage
(unsupported type, oversized, no-text, corrupt) lives in test_upload_rejection.py
(issue #55); per-folder filename-uniqueness coverage lives in
test_upload_uniqueness.py (issue #60).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Folder, Source, Subject, User

TEST_EMAIL = "upload-seam-test-user@example.com"
OTHER_EMAIL = "upload-seam-other-user@example.com"
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


def _make_subject(db_session: Session, user_id: int, name: str) -> Subject:
    subject = Subject(user_id=user_id, name=name, created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)
    return subject


def _make_folder(db_session: Session, subject_id: int, name: str) -> Folder:
    folder = Folder(subject_id=subject_id, name=name, created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


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


def test_upload_valid_txt_creates_stored_source_row(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.txt", b"Some plain text notes.", "text/plain")},
    )

    assert response.status_code == 200

    source = db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalar_one()
    assert source.filename == "notes.txt"
    assert source.file_type == "txt"
    assert source.raw_text == "Some plain text notes."
    assert source.status == "stored"


def test_upload_valid_markdown_creates_stored_source_row(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.md", b"# Heading\n\nBody text.", "text/markdown")},
    )

    assert response.status_code == 200
    source = db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalar_one()
    assert source.filename == "notes.md"
    assert source.file_type == "md"
    assert source.raw_text == "# Heading\n\nBody text."
    assert source.status == "stored"


def test_upload_success_swaps_in_updated_notes_list(
    authed_client: TestClient, my_folder: Folder
) -> None:
    """Ticket 14: the upload form now lives in, and swaps back into, the
    sidebar tree's notes-list fragment (``_folder_notes_list.html``) rather
    than the old, now-deleted ``_folder_sources_section.html``."""
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.txt", b"content", "text/plain")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    text = response.text
    assert "notes.txt" in text
    assert f'id="folder-{my_folder.id}-notes-list-section"' in text
    assert f'id="notes-list-{my_folder.id}"' in text
    # No error fragment on a successful upload.
    assert '<p class="error">' not in text


def test_upload_does_not_persist_original_binary_anywhere(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """Only extracted text should be stored -- the `sources` row has no
    binary/blob column at all, so we assert the extracted text is exactly
    the decoded content (not, say, still-encoded raw bytes)."""
    raw_bytes = b"Exact text content."
    authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.txt", raw_bytes, "text/plain")},
    )

    source = db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalar_one()
    assert source.raw_text == raw_bytes.decode("utf-8")
    # The ORM model has no binary-storing column beyond `raw_text`.
    assert not hasattr(source, "raw_bytes")
    assert not hasattr(source, "file_data")


def test_upload_into_other_users_folder_returns_404_and_creates_no_row(
    authed_client: TestClient, db_session: Session, their_folder: Folder
) -> None:
    response = authed_client.post(
        f"/folders/{their_folder.id}/sources",
        files={"file": ("notes.txt", b"sneaky", "text/plain")},
    )

    assert response.status_code == 404
    rows = db_session.execute(select(Source).where(Source.folder_id == their_folder.id)).all()
    assert rows == []


def test_upload_into_nonexistent_folder_returns_404(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/folders/999999999/sources",
        files={"file": ("notes.txt", b"content", "text/plain")},
    )

    assert response.status_code == 404


def test_upload_unauthenticated_is_rejected(client: TestClient, my_folder: Folder) -> None:
    response = client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.txt", b"content", "text/plain")},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_upload_unauthenticated_creates_no_row(
    client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.txt", b"content", "text/plain")},
        follow_redirects=False,
    )

    rows = db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).all()
    assert rows == []
