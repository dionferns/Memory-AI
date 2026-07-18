"""HTTP-seam + DB-level tests for per-folder filename uniqueness (ticket 05,
issue #60).

Covers: a case-insensitive duplicate filename within the same folder is
rejected with a 422 naming the conflicting filename and creates no extra
`sources` row; the same filename in a *different* folder succeeds (the
constraint is scoped per-folder, not global); and the constraint itself
lives at the DB level (a direct `INSERT` that bypasses the app entirely
still raises `IntegrityError`), not only in application code.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Folder, Source, Subject, User

TEST_EMAIL = "upload-uniqueness-seam-test-user@example.com"
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
def authed_client(client: TestClient, seeded_user: User) -> TestClient:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    return client


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    subject = Subject(user_id=seeded_user.id, name="System Design", created_at=datetime.now(UTC))
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
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    return _make_folder(db_session, my_subject.id, "Caching")


@pytest.fixture
def my_other_folder(db_session: Session, my_subject: Subject) -> Folder:
    return _make_folder(db_session, my_subject.id, "Consistency")


def _upload(
    client: TestClient, folder_id: int, filename: str, content: bytes = b"content"
) -> Response:
    response: Response = client.post(
        f"/folders/{folder_id}/sources",
        files={"file": (filename, content, "text/plain")},
    )
    return response


def test_exact_duplicate_filename_in_same_folder_rejected(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    first = _upload(authed_client, my_folder.id, "notes.txt")
    assert first.status_code == 200

    second = _upload(authed_client, my_folder.id, "notes.txt")

    assert second.status_code == 422
    # The (unchanged) sources list from the first upload also shows
    # "notes.txt", so assert on the actual error-paragraph text -- not a
    # loose substring the existing list would satisfy regardless of what
    # the route's rejection message says.
    expected_error = (
        '<p class="error">a file named &#39;notes.txt&#39; already exists in this folder.</p>'
    )
    assert expected_error in second.text
    sources = (
        db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalars().all()
    )
    assert len(sources) == 1


def test_case_insensitive_duplicate_filename_rejected(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    # Seed the existing lowercase-named source directly (bypassing the HTTP
    # route) so the second upload's content can be ordinary, successfully
    # parseable text -- this test is only exercising the uniqueness check,
    # not PDF parsing.
    db_session.add(
        Source(
            folder_id=my_folder.id,
            filename="notes.txt",
            file_type="txt",
            raw_text="existing text",
            status="stored",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    response = _upload(authed_client, my_folder.id, "Notes.TXT")

    assert response.status_code == 422
    assert "Notes.TXT" in response.text
    sources = (
        db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalars().all()
    )
    assert len(sources) == 1
    assert sources[0].filename == "notes.txt"


def test_same_filename_in_different_folder_succeeds(
    authed_client: TestClient,
    db_session: Session,
    my_folder: Folder,
    my_other_folder: Folder,
) -> None:
    first = _upload(authed_client, my_folder.id, "notes.txt")
    assert first.status_code == 200

    second = _upload(authed_client, my_other_folder.id, "notes.txt")

    assert second.status_code == 200
    sources_in_first = (
        db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalars().all()
    )
    sources_in_second = (
        db_session.execute(select(Source).where(Source.folder_id == my_other_folder.id))
        .scalars()
        .all()
    )
    assert len(sources_in_first) == 1
    assert len(sources_in_second) == 1


def test_constraint_enforced_at_db_level_not_only_in_app_code(
    db_session: Session, my_folder: Folder
) -> None:
    """A raw INSERT that bypasses the app's upload route entirely must
    still be rejected by the DB itself, proving the uniqueness constraint
    is a real schema-level constraint (from the migration), not just a
    check the route happens to perform."""
    now = datetime.now(UTC)
    db_session.execute(
        insert(Source).values(
            folder_id=my_folder.id,
            filename="direct-insert.txt",
            file_type="txt",
            raw_text="a",
            status="stored",
            created_at=now,
        )
    )
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(Source).values(
                folder_id=my_folder.id,
                filename="DIRECT-INSERT.txt",
                file_type="txt",
                raw_text="b",
                status="stored",
                created_at=now,
            )
        )
        db_session.commit()
