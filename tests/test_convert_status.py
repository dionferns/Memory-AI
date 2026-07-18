"""HTTP-seam tests for the processing-popup polling UI (ticket 06, issue #78).

Covers the "Convert to Flashcards" button and the `_source_status.html`
fragment (returned both by `POST /sources/{id}/convert` and `GET
/sources/{id}/status`) across all four `sources.status` values, asserting
the fragment's content and the presence/absence of the `hx-trigger="every
2s"` polling attribute for each -- not just that a 200 came back. The
convert-trigger's happy-path job-completion behavior is covered by
test_convert.py (#76); this file is about the *rendered fragment shape* per
status, independent of whether the status was reached via a real job run.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Source, Subject, User

TEST_EMAIL = "convert-status-seam-test-user@example.com"
OTHER_EMAIL = "convert-status-seam-other-user@example.com"
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


def _make_source(
    db_session: Session,
    folder_id: int,
    *,
    status: str,
    error_message: str | None = None,
) -> Source:
    source = Source(
        folder_id=folder_id,
        filename="notes.txt",
        file_type="txt",
        raw_text="Some notes.",
        status=status,
        error_message=error_message,
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
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Theirs")


# --- GET /sources/{id}/status per status value -------------------------------


def test_status_stored_shows_convert_button_no_popup_no_cards(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="stored")

    response = authed_client.get(f"/sources/{source.id}/status")

    assert response.status_code == 200
    text = response.text
    assert f'hx-post="/sources/{source.id}/convert"' in text
    assert ">Convert to Flashcards<" in text
    assert "hx-trigger" not in text
    assert f"source-{source.id}-processing" not in text
    assert f"source-{source.id}-cards" not in text
    assert f"source-{source.id}-error" not in text


def test_status_processing_includes_polling_trigger_no_cards_no_button(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="processing")

    response = authed_client.get(f"/sources/{source.id}/status")

    assert response.status_code == 200
    text = response.text
    assert 'hx-trigger="every 2s"' in text
    assert f'hx-get="/sources/{source.id}/status"' in text
    assert f"source-{source.id}-processing" in text
    assert "Convert to Flashcards" not in text
    assert "hx-post" not in text


def test_status_done_renders_cards_no_trigger_and_convert_button_present(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="done")
    db_session.add_all(
        [
            Card(
                source_id=source.id,
                folder_id=my_folder.id,
                front="Q1",
                back="A1",
                ease_factor=2.5,
                interval_days=0,
                repetitions=0,
                due_date=datetime.now(UTC).date(),
                created_at=datetime.now(UTC),
            ),
            Card(
                source_id=source.id,
                folder_id=my_folder.id,
                front="Q2",
                back="A2",
                ease_factor=2.5,
                interval_days=0,
                repetitions=0,
                due_date=datetime.now(UTC).date(),
                created_at=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()

    response = authed_client.get(f"/sources/{source.id}/status")

    assert response.status_code == 200
    text = response.text
    assert "hx-trigger" not in text
    assert "Q1" in text and "A1" in text
    assert "Q2" in text and "A2" in text
    # The convert button re-appears on `done` so the user can re-trigger
    # (regenerate) per user story 6/7 -- it's the same convert action, not a
    # distinct "regenerate" endpoint.
    assert f'hx-post="/sources/{source.id}/convert"' in text
    assert ">Convert to Flashcards<" in text


def test_status_failed_renders_error_and_retry_button_no_trigger(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(
        db_session, my_folder.id, status="failed", error_message="Flashcard generation failed."
    )

    response = authed_client.get(f"/sources/{source.id}/status")

    assert response.status_code == 200
    text = response.text
    assert "hx-trigger" not in text
    assert "Flashcard generation failed." in text
    assert f'hx-post="/sources/{source.id}/convert"' in text
    assert ">Retry<" in text
    assert ">Convert to Flashcards<" not in text
    assert f"source-{source.id}-cards" not in text


# --- Ownership + fragment-shape sanity on the trigger route -------------------


def test_status_other_users_source_returns_404(
    authed_client: TestClient, db_session: Session, their_folder: Folder
) -> None:
    source = _make_source(db_session, their_folder.id, status="stored")

    response = authed_client.get(f"/sources/{source.id}/status")

    assert response.status_code == 404


def test_status_nonexistent_source_returns_404(authed_client: TestClient) -> None:
    response = authed_client.get("/sources/999999999/status")

    assert response.status_code == 404


def test_status_unauthenticated_is_rejected(client: TestClient) -> None:
    # No auth cookie set at all -- the `current_user` dependency must reject
    # before any ownership lookup on a (nonexistent) source ever runs.
    response = client.get("/sources/1/status", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_convert_response_fragment_is_not_a_full_page(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """The convert route swaps a fragment via HTMX, not a full page reload."""
    source = _make_source(db_session, my_folder.id, status="stored")

    response = authed_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    assert "<html" not in response.text.lower()
    assert f'id="source-{source.id}-status"' in response.text
