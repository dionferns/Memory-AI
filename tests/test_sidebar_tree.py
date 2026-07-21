"""HTTP-seam tests for the sidebar tree shell (ticket 14, issue #141).

Covers this slice's own scope: the `/subjects` page rendering the new
two-pane shell (sidebar tree + placeholder right pane) instead of the old
flat inline list, the new lazy `GET /folders/{folder_id}/notes` fragment
route (name+id only, ownership-scoped, fetched only on folder expand), and
empty states at every level (no subjects / a subject with no folders / a
folder with no notes).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Folder, Source, Subject, User

TEST_EMAIL = "sidebar-tree-seam-test-user@example.com"
OTHER_EMAIL = "sidebar-tree-seam-other-user@example.com"
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
    db_session: Session, folder_id: int, filename: str, created_at: datetime
) -> Source:
    source = Source(
        folder_id=folder_id,
        filename=filename,
        file_type="txt",
        raw_text="Some raw text.",
        status="stored",
        created_at=created_at,
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
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Their Folder")


# --- GET /subjects: two-pane shell -----------------------------------------


def test_subjects_page_renders_sidebar_and_placeholder_right_pane(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    assert 'id="sidebar"' in text
    assert 'id="content-pane"' in text
    assert 'id="content-pane-placeholder"' in text
    assert "Select a note to view it." in text


def test_subjects_page_includes_responsive_sidebar_toggle_button(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")

    assert response.status_code == 200
    assert 'id="sidebar-toggle"' in response.text


def test_subjects_page_no_longer_eager_loads_sources(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """As of ticket 14, `GET /subjects` still issues one query for subjects
    and one follow-up query for folders (unchanged from ticket 04), but must
    no longer join/eager-load `sources` at all -- notes are lazy-loaded per
    folder via a separate request only once that folder is expanded."""
    _make_source(db_session, my_folder.id, "note.txt", datetime.now(UTC))

    statements: list[str] = []
    engine = db_session.get_bind()

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", _capture)
    try:
        response = authed_client.get("/subjects")
    finally:
        sa.event.remove(engine, "before_cursor_execute", _capture)

    assert response.status_code == 200
    source_queries = [s for s in statements if "FROM sources" in s]
    assert source_queries == []


def test_subjects_page_folder_row_no_longer_inlines_notes(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, "note.txt", datetime.now(UTC))

    response = authed_client.get("/subjects")

    assert response.status_code == 200
    # The note's filename must not appear anywhere on the initial page load
    # -- it's only revealed once the folder is expanded (a separate request
    # to GET /folders/{id}/notes, covered below).
    assert "note.txt" not in response.text
    assert f"note-{source.id}" not in response.text


def test_subjects_page_folder_row_wires_lazy_notes_fetch_on_expand(
    authed_client: TestClient, my_folder: Folder
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    assert f'hx-get="/folders/{my_folder.id}/notes"' in text
    assert "toggle once" in text


# --- GET /folders/{id}/notes -------------------------------------------------


def test_list_folder_notes_returns_notes_in_creation_order(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    base = datetime.now(UTC)
    first = _make_source(db_session, my_folder.id, "a.txt", base)
    second = _make_source(db_session, my_folder.id, "b.txt", base + timedelta(seconds=1))

    response = authed_client.get(f"/folders/{my_folder.id}/notes")
    text = response.text

    assert response.status_code == 200
    assert "notes-empty-state" not in text
    positions = [text.index(f"note-{s.id}") for s in (first, second)]
    assert positions == sorted(positions)
    assert "a.txt" in text
    assert "b.txt" in text


def test_list_folder_notes_only_returns_notes_no_actions(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """Per decisions.md #5, this fragment is name+id only -- no convert/quiz/
    view-cards controls (those stay scoped to a later slice's note-content
    route)."""
    source = _make_source(db_session, my_folder.id, "note.txt", datetime.now(UTC))

    response = authed_client.get(f"/folders/{my_folder.id}/notes")
    text = response.text

    assert response.status_code == 200
    assert f"quiz-me-{source.id}" not in text
    assert "Convert to Flashcards" not in text
    assert "Quiz Me" not in text


def test_list_folder_notes_empty_state(authed_client: TestClient, my_folder: Folder) -> None:
    response = authed_client.get(f"/folders/{my_folder.id}/notes")
    text = response.text

    assert response.status_code == 200
    assert f"notes-empty-state-{my_folder.id}" in text
    assert "No notes yet." in text


def test_list_folder_notes_only_shows_current_users_notes(
    authed_client: TestClient, db_session: Session, my_folder: Folder, their_folder: Folder
) -> None:
    mine = _make_source(db_session, my_folder.id, "mine.txt", datetime.now(UTC))
    _make_source(db_session, their_folder.id, "theirs.txt", datetime.now(UTC))

    response = authed_client.get(f"/folders/{my_folder.id}/notes")

    assert f"note-{mine.id}" in response.text
    assert "theirs.txt" not in response.text


def test_list_folder_notes_for_other_users_folder_returns_404_not_403(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{their_folder.id}/notes")

    assert response.status_code == 404
    assert response.status_code != 403


def test_list_folder_notes_for_nonexistent_folder_returns_404(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/folders/999999999/notes")

    assert response.status_code == 404


def test_list_folder_notes_nonexistent_and_not_owned_are_identical_404(
    authed_client: TestClient, their_folder: Folder
) -> None:
    nonexistent_response = authed_client.get("/folders/999999999/notes")
    not_owned_response = authed_client.get(f"/folders/{their_folder.id}/notes")

    assert nonexistent_response.status_code == not_owned_response.status_code == 404


def test_list_folder_notes_unauthenticated_redirects_to_login(
    client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id)
    folder = _make_folder(db_session, subject.id)

    response = client.get(f"/folders/{folder.id}/notes", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


# --- Empty states across all three levels -----------------------------------


def test_subjects_page_top_level_empty_state_when_no_subjects(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    assert "subjects-empty-state" in text


def test_subjects_page_folder_level_empty_state_for_subject_with_no_folders(
    authed_client: TestClient, my_subject: Subject
) -> None:
    response = authed_client.get("/subjects")

    assert f"folders-empty-state-{my_subject.id}" in response.text


def test_folders_notes_level_empty_state_for_folder_with_no_notes(
    authed_client: TestClient, my_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{my_folder.id}/notes")

    assert f"notes-empty-state-{my_folder.id}" in response.text


# --- Tree nodes collapsed by default -----------------------------------------


def test_subject_and_folder_tree_nodes_are_collapsed_by_default(
    authed_client: TestClient, my_folder: Folder, my_subject: Subject
) -> None:
    """Neither the subject's nor the folder's `<details>` carries the `open`
    attribute -- both start collapsed, expanding only on click (decisions.md
    summary / issue #141 acceptance criteria)."""
    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    assert f'<details class="tree-node" id="subject-{my_subject.id}-details">' in text
    assert f'<details class="tree-node" id="folder-{my_folder.id}-details">' in text
