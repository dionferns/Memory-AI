"""HTTP-seam tests for the unified `GET /subjects` hierarchy page (ticket 04,
issue #88).

This slice ties subject CRUD (#85) and folder CRUD (#86) together into one
cohesive, performant page rather than adding new CRUD behavior: it proves
the page issues a single query shape for subjects + folders (no N+1), and
that it renders correctly across the various combinations of subjects with
and without folders, including the fully-empty case.

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
from memory_ai.models import Folder, Subject, User

TEST_EMAIL = "hierarchy-page-seam-test-user@example.com"
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


def _captured_statements(db_session: Session, run: object) -> list[str]:
    """Run ``run()`` while capturing every SQL statement executed on the
    session's underlying connection, and return them."""
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
        run()  # type: ignore[operator]
    finally:
        sa.event.remove(engine, "before_cursor_execute", _capture)
    return statements


def test_subjects_page_issues_one_query_for_subjects_and_one_for_folders(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    """No N+1: with 4 subjects, folders must be fetched in one follow-up
    query (`selectinload`), not once per subject."""
    base = datetime.now(UTC)
    for i in range(4):
        subject = _make_subject(
            db_session, seeded_user.id, f"Subject {i}", base + timedelta(seconds=i)
        )
        _make_folder(db_session, subject.id, f"Folder {i}-a", base)
        _make_folder(db_session, subject.id, f"Folder {i}-b", base + timedelta(seconds=1))

    result = {}

    def _do_request() -> None:
        result["response"] = authed_client.get("/subjects")

    statements = _captured_statements(db_session, _do_request)

    assert result["response"].status_code == 200

    subject_queries = [s for s in statements if "FROM subjects" in s]
    folder_queries = [s for s in statements if "FROM folders" in s]

    assert len(subject_queries) == 1
    assert len(folder_queries) == 1


def test_subjects_page_renders_multiple_subjects_each_with_multiple_folders_in_order(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    base = datetime.now(UTC)
    subject_a = _make_subject(db_session, seeded_user.id, "Alpha", base)
    subject_b = _make_subject(db_session, seeded_user.id, "Beta", base + timedelta(seconds=1))

    a1 = _make_folder(db_session, subject_a.id, "A1", base)
    a2 = _make_folder(db_session, subject_a.id, "A2", base + timedelta(seconds=1))
    b1 = _make_folder(db_session, subject_b.id, "B1", base)
    b2 = _make_folder(db_session, subject_b.id, "B2", base + timedelta(seconds=1))

    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200

    # Subjects appear in creation order.
    subject_positions = [text.index(f"subject-{s.id}-name") for s in (subject_a, subject_b)]
    assert subject_positions == sorted(subject_positions)

    # Each subject's own folders appear in creation order.
    a_positions = [text.index(f"folder-{f.id}-name") for f in (a1, a2)]
    assert a_positions == sorted(a_positions)
    b_positions = [text.index(f"folder-{f.id}-name") for f in (b1, b2)]
    assert b_positions == sorted(b_positions)

    # Folders render nested under their own subject, not the other one.
    assert text.index(f"subject-{subject_a.id}-name") < text.index(f"folder-{a1.id}-name")
    assert text.index(f"folder-{a2.id}-name") < text.index(f"subject-{subject_b.id}-name")


def test_subjects_page_combines_a_subject_with_folders_and_one_without(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    base = datetime.now(UTC)
    populated = _make_subject(db_session, seeded_user.id, "Populated", base)
    empty = _make_subject(db_session, seeded_user.id, "Empty", base + timedelta(seconds=1))
    folder = _make_folder(db_session, populated.id, "Only Folder", base)

    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    # No top-level empty state, since the user does have subjects.
    assert "subjects-empty-state" not in text

    # The populated subject shows its folder and no folder-empty-state.
    assert f"folder-{folder.id}-name" in text
    assert f"folders-empty-state-{populated.id}" not in text

    # The empty subject shows its own folder-empty-state and create form,
    # not any folder rows.
    assert f"folders-empty-state-{empty.id}" in text
    assert f'id="create-folder-form-{empty.id}"' in text


def test_subjects_page_with_zero_subjects_shows_only_top_level_empty_state(
    authed_client: TestClient,
) -> None:
    response = authed_client.get("/subjects")
    text = response.text

    assert response.status_code == 200
    assert "subjects-empty-state" in text
    # No subject exists, so no per-subject folder-empty-state markup should
    # be present at all (there's no subject id to scope one to).
    assert "folders-empty-state-" not in text
    assert "create-folder-form-" not in text
