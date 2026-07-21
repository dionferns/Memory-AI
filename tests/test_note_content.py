"""HTTP-seam tests for the note-content pane (ticket 14, issue #142).

Covers this slice's own scope: `GET /sources/{id}/content` (the right-pane
fragment swapped in by the sidebar's note rows), `GET /sources/{id}` (the
full-page direct/deep-link variant with the tree pre-expanded), Markdown
rendering being format-agnostic (PDF/TXT/MD all go through the same
`markdown.markdown()` call over `raw_text`, no per-format branching), and
ownership scoping (404, never 403).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Folder, Source, Subject, User

TEST_EMAIL = "note-content-seam-test-user@example.com"
OTHER_EMAIL = "note-content-seam-other-user@example.com"
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


def _make_source(
    db_session: Session,
    folder_id: int,
    filename: str = "note.txt",
    file_type: str = "txt",
    raw_text: str = "# Heading\n\nSome *text*.",
) -> Source:
    source = Source(
        folder_id=folder_id,
        filename=filename,
        file_type=file_type,
        raw_text=raw_text,
        status="stored",
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


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
    return _make_folder(db_session, their_subject.id, "Their Folder")


@pytest.fixture
def their_source(db_session: Session, their_folder: Folder) -> Source:
    return _make_source(db_session, their_folder.id, "theirs.txt")


# --- GET /sources/{id}/content -----------------------------------------------


def test_source_content_renders_markdown_to_html(
    authed_client: TestClient, my_source: Source
) -> None:
    response = authed_client.get(f"/sources/{my_source.id}/content")
    text = response.text

    assert response.status_code == 200
    assert "<h1>Heading</h1>" in text
    assert "<em>text</em>" in text
    assert f'id="note-content-{my_source.id}"' in text
    assert my_source.filename in text


def test_source_content_does_not_render_full_page_shell(
    authed_client: TestClient, my_source: Source
) -> None:
    """This is the swap-target fragment, not the full page -- no <html>/
    sidebar markup."""
    response = authed_client.get(f"/sources/{my_source.id}/content")
    text = response.text

    assert response.status_code == 200
    assert "<html" not in text
    assert 'id="sidebar"' not in text


@pytest.mark.parametrize("file_type", ["md", "pdf", "txt"])
def test_source_content_renders_identically_regardless_of_original_format(
    authed_client: TestClient, db_session: Session, my_folder: Folder, file_type: str
) -> None:
    """Decision #6: the exact same raw_text renders through the exact same
    Markdown path no matter what the source's original format was -- no
    per-format special-casing visible in the output."""
    source = _make_source(
        db_session,
        my_folder.id,
        filename=f"note.{file_type}",
        file_type=file_type,
        raw_text="# Title\n\nBody paragraph.",
    )

    response = authed_client.get(f"/sources/{source.id}/content")
    text = response.text

    assert response.status_code == 200
    assert '<div id="note-content-body-' in text
    assert "<h1>Title</h1>" in text
    assert "<p>Body paragraph.</p>" in text


def test_source_content_for_other_users_source_returns_404_not_403(
    authed_client: TestClient, their_source: Source
) -> None:
    response = authed_client.get(f"/sources/{their_source.id}/content")

    assert response.status_code == 404
    assert response.status_code != 403


def test_source_content_for_nonexistent_source_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/sources/999999999/content")

    assert response.status_code == 404


def test_source_content_nonexistent_and_not_owned_are_identical_404(
    authed_client: TestClient, their_source: Source
) -> None:
    nonexistent_response = authed_client.get("/sources/999999999/content")
    not_owned_response = authed_client.get(f"/sources/{their_source.id}/content")

    assert nonexistent_response.status_code == not_owned_response.status_code == 404


def test_source_content_unauthenticated_redirects_to_login(
    client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    response = client.get(f"/sources/{source.id}/content", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


# --- GET /sources/{id} (full page) -------------------------------------------


def test_view_source_page_renders_full_shell_with_note_selected(
    authed_client: TestClient, my_source: Source
) -> None:
    response = authed_client.get(f"/sources/{my_source.id}")
    text = response.text

    assert response.status_code == 200
    assert "<html" in text
    assert 'id="sidebar"' in text
    assert f'id="note-content-{my_source.id}"' in text
    assert "<h1>Heading</h1>" in text


def test_view_source_page_pre_expands_the_owning_subject_and_folder(
    authed_client: TestClient, my_source: Source, my_subject: Subject, my_folder: Folder
) -> None:
    response = authed_client.get(f"/sources/{my_source.id}")
    text = response.text

    assert response.status_code == 200
    assert f'<details class="tree-node" id="subject-{my_subject.id}-details" open>' in text
    assert f'<details class="tree-node" id="folder-{my_folder.id}-details" open>' in text


def test_view_source_page_shows_sibling_notes_in_the_same_folder(
    authed_client: TestClient, db_session: Session, my_folder: Folder, my_source: Source
) -> None:
    """The owning folder's notes list is preloaded (not left to the usual
    lazy fetch) since the response already needs it to reveal the selected
    note in the tree."""
    sibling = _make_source(db_session, my_folder.id, filename="sibling.txt")

    response = authed_client.get(f"/sources/{my_source.id}")
    text = response.text

    assert response.status_code == 200
    assert f"note-{sibling.id}" in text
    assert "sibling.txt" in text


def test_view_source_page_does_not_expand_other_subjects_or_folders(
    authed_client: TestClient, db_session: Session, seeded_user: User, my_source: Source
) -> None:
    other_subject = _make_subject(db_session, seeded_user.id, "Other Subject")
    other_folder = _make_folder(db_session, other_subject.id, "Other Folder")

    response = authed_client.get(f"/sources/{my_source.id}")
    text = response.text

    assert response.status_code == 200
    assert f'<details class="tree-node" id="subject-{other_subject.id}-details">' in text
    assert f'<details class="tree-node" id="folder-{other_folder.id}-details">' in text


def test_view_source_page_marks_the_selected_note_link(
    authed_client: TestClient, my_source: Source
) -> None:
    response = authed_client.get(f"/sources/{my_source.id}")
    text = response.text

    assert response.status_code == 200
    assert f'id="note-{my_source.id}-link"' in text
    assert "note-link note-link-selected" in text


def test_view_source_page_for_other_users_source_returns_404_not_403(
    authed_client: TestClient, their_source: Source
) -> None:
    response = authed_client.get(f"/sources/{their_source.id}")

    assert response.status_code == 404
    assert response.status_code != 403


def test_view_source_page_for_nonexistent_source_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/sources/999999999")

    assert response.status_code == 404


def test_view_source_page_unauthenticated_redirects_to_login(
    client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    response = client.get(f"/sources/{source.id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


# --- Sidebar note rows wire the HTMX click-to-select behavior ---------------


def test_folder_notes_fragment_wires_click_to_select_with_push_url(
    authed_client: TestClient, my_folder: Folder, my_source: Source
) -> None:
    response = authed_client.get(f"/folders/{my_folder.id}/notes")
    text = response.text

    assert response.status_code == 200
    assert f'hx-get="/sources/{my_source.id}/content"' in text
    assert 'hx-target="#content-pane"' in text
    assert f'hx-push-url="/sources/{my_source.id}"' in text
    assert f'href="/sources/{my_source.id}"' in text


def test_folder_notes_fragment_does_not_mark_any_note_selected_when_lazy_loaded(
    authed_client: TestClient, my_folder: Folder, my_source: Source
) -> None:
    """The plain lazy-load fragment (no `selected_source_id` in its
    context) must not accidentally highlight a note as selected."""
    response = authed_client.get(f"/folders/{my_folder.id}/notes")

    assert "note-link-selected" not in response.text


# --- /subjects (no selection) is unaffected ----------------------------------


def test_subjects_page_still_shows_placeholder_when_no_note_selected(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    assert "content-pane-placeholder" in text
    assert "note-content-" not in text
