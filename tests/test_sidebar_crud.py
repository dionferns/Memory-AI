"""HTTP-seam tests for structural CRUD relocated into the sidebar tree
(ticket 14, issue #144).

Create/rename/delete subject and folder already render inside the sidebar
tree as of #141 (this slice's own PR notes explicitly point that out --
their routes/templates already live at the tree's subject/folder levels).
What actually changes in this slice is upload-a-note moving from the old,
now-deleted `_folder_sources_section.html` into the sidebar's lazy notes-list
fragment (`_folder_notes_list.html`), and the retirement of that old file.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Folder, Source, Subject, User

TEST_EMAIL = "sidebar-crud-seam-test-user@example.com"
OTHER_EMAIL = "sidebar-crud-seam-other-user@example.com"
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


# --- _folder_sources_section.html is fully retired ---------------------------


def test_folder_sources_section_template_file_no_longer_exists() -> None:
    templates_dir = Path(__file__).resolve().parent.parent / "src" / "memory_ai" / "templates"
    assert not (templates_dir / "_folder_sources_section.html").exists()


def test_no_source_file_references_folder_sources_section_template_by_name() -> None:
    """Only comments/docstrings mentioning it historically are allowed --
    the actual Jinja ``{% include "_folder_sources_section.html" %}`` /
    ``TemplateResponse(..., "_folder_sources_section.html", ...)`` call must
    be gone everywhere."""
    src_dir = Path(__file__).resolve().parent.parent / "src"
    candidates = [*src_dir.rglob("*.py"), *src_dir.rglob("*.html")]
    offending = [
        path
        for path in candidates
        if '"_folder_sources_section.html"' in path.read_text(encoding="utf-8")
    ]
    assert offending == []


# --- Sidebar tree already hosts subject/folder CRUD (established in #141) --


def test_subjects_page_sidebar_includes_create_subject_form(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")

    assert 'id="create-subject-form"' in response.text
    assert 'hx-post="/subjects"' in response.text


def test_subjects_page_sidebar_includes_rename_and_delete_subject_controls(
    authed_client: TestClient, my_subject: Subject
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert f'hx-get="/subjects/{my_subject.id}/edit"' in text
    assert f'hx-delete="/subjects/{my_subject.id}"' in text


def test_subjects_page_sidebar_includes_create_folder_form_per_subject(
    authed_client: TestClient, my_subject: Subject
) -> None:
    response = authed_client.get("/subjects")

    assert f'id="create-folder-form-{my_subject.id}"' in response.text
    assert f'hx-post="/subjects/{my_subject.id}/folders"' in response.text


def test_subjects_page_sidebar_includes_rename_and_delete_folder_controls(
    authed_client: TestClient, my_folder: Folder
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert f'hx-get="/folders/{my_folder.id}/edit"' in text
    assert f'hx-delete="/folders/{my_folder.id}"' in text


# --- Upload-a-note now lives in the sidebar's lazy notes-list fragment ------


def test_folder_notes_fragment_includes_upload_form(
    authed_client: TestClient, my_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{my_folder.id}/notes")
    text = response.text

    assert response.status_code == 200
    assert f'id="upload-form-{my_folder.id}"' in text
    assert f'hx-post="/folders/{my_folder.id}/sources"' in text
    assert f'hx-target="#folder-{my_folder.id}-notes-list-section"' in text


def test_upload_from_sidebar_appends_new_note_into_lazy_loaded_list(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    # Start with one existing note, then upload a second -- the response
    # must show both, proving the swap refreshes the whole notes list
    # rather than only appending blindly.
    existing = Source(
        folder_id=my_folder.id,
        filename="existing.txt",
        file_type="txt",
        raw_text="Existing.",
        status="stored",
        created_at=datetime.now(UTC),
    )
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("new-note.txt", b"Fresh content.", "text/plain")},
        headers={"HX-Request": "true"},
    )
    text = response.text

    assert response.status_code == 200
    assert f'id="folder-{my_folder.id}-notes-list-section"' in text
    assert "existing.txt" in text
    assert "new-note.txt" in text
    assert "notes-empty-state" not in text

    new_source = db_session.execute(
        select(Source).where(Source.folder_id == my_folder.id, Source.filename == "new-note.txt")
    ).scalar_one()
    assert new_source.raw_text == "Fresh content."


def test_upload_from_sidebar_into_other_users_folder_returns_404_not_403(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.post(
        f"/folders/{their_folder.id}/sources",
        files={"file": ("sneaky.txt", b"nope", "text/plain")},
    )

    assert response.status_code == 404
    assert response.status_code != 403


def test_folder_notes_list_transitions_from_empty_to_populated_after_upload(
    authed_client: TestClient, my_folder: Folder
) -> None:
    before = authed_client.get(f"/folders/{my_folder.id}/notes")
    assert f"notes-empty-state-{my_folder.id}" in before.text

    authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("note.txt", b"content", "text/plain")},
    )

    after = authed_client.get(f"/folders/{my_folder.id}/notes")
    assert f"notes-empty-state-{my_folder.id}" not in after.text
    assert "note.txt" in after.text
