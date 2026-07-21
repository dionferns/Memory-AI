"""HTTP-seam tests for per-note actions relocated into the right pane
(ticket 14, issue #143).

Covers this slice's own scope: the Convert-to-Flashcards status widget (all
four `sources.status` states), the Quiz Me button/result container, and a
View Cards link, all scoped to the currently-selected note and rendered from
`GET /sources/{id}/content` (the HTMX click-to-select fragment) and
`GET /sources/{id}` (the full-page direct/deep-link variant) -- not from any
new route or changed underlying logic.

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

TEST_EMAIL = "note-actions-seam-test-user@example.com"
OTHER_EMAIL = "note-actions-seam-other-user@example.com"
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
    *,
    filename: str = "note.txt",
    status: str,
    error_message: str | None = None,
) -> Source:
    source = Source(
        folder_id=folder_id,
        filename=filename,
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


def _make_card(db_session: Session, source_id: int, folder_id: int, front: str, back: str) -> Card:
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
        due_date=datetime.now(UTC).date(),
        created_at=datetime.now(UTC),
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


@pytest.mark.parametrize("route_kind", ["content", "full_page"])
class TestConvertStatusWidgetPerState:
    """Both the fragment route and the full-page route render the exact
    same _note_content.html -- run every status assertion against both."""

    def _get(self, authed_client: TestClient, source: Source, route_kind: str) -> str:
        if route_kind == "content":
            response = authed_client.get(f"/sources/{source.id}/content")
        else:
            response = authed_client.get(f"/sources/{source.id}")
        assert response.status_code == 200
        return str(response.text)

    def test_stored_shows_convert_button(
        self, authed_client: TestClient, db_session: Session, my_folder: Folder, route_kind: str
    ) -> None:
        source = _make_source(db_session, my_folder.id, status="stored")

        text = self._get(authed_client, source, route_kind)

        assert f'hx-post="/sources/{source.id}/convert"' in text
        assert ">Convert to Flashcards<" in text
        # Scoped to the actual polling attribute, not a bare "hx-trigger"
        # substring -- the full-page route's sidebar tree markup has its own
        # unrelated HTML comment mentioning "hx-trigger" for the lazy-load
        # feature, which a loose substring check would false-positive on.
        assert 'hx-trigger="every 2s"' not in text

    def test_processing_shows_polling_popup(
        self, authed_client: TestClient, db_session: Session, my_folder: Folder, route_kind: str
    ) -> None:
        source = _make_source(db_session, my_folder.id, status="processing")

        text = self._get(authed_client, source, route_kind)

        assert 'hx-trigger="every 2s"' in text
        assert f'hx-get="/sources/{source.id}/status"' in text
        assert f"source-{source.id}-processing" in text
        # Tag-boundary match, not a bare substring: this template's own
        # explanatory HTML comment mentions the phrase "Convert to
        # Flashcards" in prose, so a loose substring check would pass even
        # if the button itself were wrongly still rendered while
        # processing.
        assert ">Convert to Flashcards<" not in text

    def test_done_shows_cards_and_convert_button(
        self, authed_client: TestClient, db_session: Session, my_folder: Folder, route_kind: str
    ) -> None:
        source = _make_source(db_session, my_folder.id, status="done")
        card = _make_card(db_session, source.id, my_folder.id, "Q", "A")

        text = self._get(authed_client, source, route_kind)

        assert f"card-{card.id}" in text
        assert "Q" in text and "A" in text
        assert f'hx-post="/sources/{source.id}/convert"' in text
        assert ">Convert to Flashcards<" in text

    def test_failed_shows_error_and_retry_button(
        self, authed_client: TestClient, db_session: Session, my_folder: Folder, route_kind: str
    ) -> None:
        source = _make_source(db_session, my_folder.id, status="failed", error_message="It broke.")

        text = self._get(authed_client, source, route_kind)

        assert f"source-{source.id}-error" in text
        assert "It broke." in text
        assert ">Retry<" in text


def test_quiz_me_button_present_in_right_pane_content(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="stored")

    response = authed_client.get(f"/sources/{source.id}/content")
    text = response.text

    assert response.status_code == 200
    assert f'id="quiz-me-{source.id}"' in text
    assert f'hx-post="/sources/{source.id}/quiz"' in text
    assert f'hx-target="#quiz-result-{source.id}"' in text
    assert f'id="quiz-result-{source.id}"' in text


def test_view_cards_link_present_and_correct(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="done")

    response = authed_client.get(f"/sources/{source.id}/content")
    text = response.text

    assert response.status_code == 200
    assert f'id="view-cards-{source.id}"' in text
    assert f'href="/sources/{source.id}/cards"' in text


def test_view_cards_link_target_route_still_works(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """The relocated link points at ticket 07's existing, unchanged route."""
    source = _make_source(db_session, my_folder.id, status="done")
    card = _make_card(db_session, source.id, my_folder.id, "Q", "A")

    response = authed_client.get(f"/sources/{source.id}/cards")

    assert response.status_code == 200
    assert f"card-{card.id}" in response.text


def test_switching_selected_note_does_not_leak_stale_ids_from_previous_note(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """Selecting note B's fragment must contain none of note A's
    per-note-action ids (quiz-me, view-cards, status), and vice versa."""
    first = _make_source(db_session, my_folder.id, filename="a.txt", status="stored")
    second = _make_source(db_session, my_folder.id, filename="b.txt", status="done")
    card = _make_card(db_session, second.id, my_folder.id, "Q", "A")

    first_response = authed_client.get(f"/sources/{first.id}/content")
    second_response = authed_client.get(f"/sources/{second.id}/content")

    assert first_response.status_code == second_response.status_code == 200
    first_text = first_response.text
    second_text = second_response.text

    # Each fragment is scoped to exactly its own note's action ids.
    assert f"quiz-me-{first.id}" in first_text
    assert f"quiz-me-{second.id}" not in first_text
    assert f"quiz-me-{second.id}" in second_text
    assert f"quiz-me-{first.id}" not in second_text

    assert f"view-cards-{first.id}" in first_text
    assert f"view-cards-{second.id}" not in first_text
    assert f"view-cards-{second.id}" in second_text
    assert f"view-cards-{first.id}" not in second_text

    # The "done" note's generated card must never appear on the "stored"
    # note's fragment (they're a different note's cards) -- matched by its
    # row id, not the bare front-text "Q" (which would false-positive
    # against this template's own "Quiz Me" button/comment text).
    assert f"card-{card.id}" not in first_text
    assert f"card-{card.id}" in second_text


def test_note_content_fragment_does_not_render_folder_sources_section(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """As of this slice, the old inline per-note-actions list
    (_folder_sources_section.html) is no longer the source of these
    controls -- they come from _note_content.html directly."""
    source = _make_source(db_session, my_folder.id, status="stored")

    response = authed_client.get(f"/sources/{source.id}/content")

    assert response.status_code == 200
    assert "upload-form-" not in response.text
