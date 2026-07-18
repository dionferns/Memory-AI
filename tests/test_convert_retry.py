"""HTTP-seam tests for failure handling + replace-on-retrigger (ticket 06,
issue #81).

Covers the background job's two failure paths -- a mocked
`FlashcardGenerator` raising `FlashcardValidationError` (malformed output)
or `FlashcardAPIError` (an Anthropic API failure) -- both of which must
leave `status=failed`, a generic `error_message`, and zero `cards` rows
written. Also covers `POST /sources/{id}/convert`'s replace-on-retrigger
behavior: re-clicking convert on an already-`done` source deletes the old
cards before generating a fresh set (no duplicates), and re-clicking on a
`failed` source clears the stale `error_message` and acts as a retry,
landing in `done` or `failed` again depending on what the (re-injected)
generator does this time.

Seam: ticket 21's shared harness (``client`` fixture) + ticket 06's
`FlashcardGenerator` mock seam -- no real Anthropic calls are ever made.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.flashcards import (
    FlashcardAPIError,
    FlashcardValidationError,
    GeneratedCard,
    get_flashcard_generator,
)
from memory_ai.main import app
from memory_ai.models import Card, Folder, Source, Subject, User

TEST_EMAIL = "convert-retry-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


class _ScriptedGenerator:
    """Injectable `FlashcardGenerator` that plays back one behavior per call.

    Each entry in ``behaviors`` is either a `list[GeneratedCard]` (returned)
    or an `Exception` instance (raised). Calling past the end of the script
    raises `AssertionError` so a test can never silently under-specify how
    many generate() calls it expects.
    """

    def __init__(self, behaviors: list[list[GeneratedCard] | Exception]) -> None:
        self._behaviors = list(behaviors)
        self.call_count = 0

    def generate(self, text: str) -> list[GeneratedCard]:
        assert self.call_count < len(self._behaviors), (
            "generate() called more times than the test scripted"
        )
        behavior = self._behaviors[self.call_count]
        self.call_count += 1
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


_CARDS_A = [GeneratedCard(question="Q-A1", answer="A-A1")]
_CARDS_B = [
    GeneratedCard(question="Q-B1", answer="A-B1"),
    GeneratedCard(question="Q-B2", answer="A-B2"),
]


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
def base_client(client: TestClient, seeded_user: User) -> TestClient:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    return client


@contextmanager
def _with_generator(client: TestClient, generator: _ScriptedGenerator) -> Iterator[TestClient]:
    app.dependency_overrides[get_flashcard_generator] = lambda: generator
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_flashcard_generator, None)


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
    status: str = "stored",
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


def _cards_for(db_session: Session, source_id: int) -> list[Card]:
    db_session.expire_all()
    return list(
        db_session.execute(select(Card).where(Card.source_id == source_id).order_by(Card.id))
        .scalars()
        .all()
    )


def _fresh_source_status(db_session: Session, source_id: int) -> Source:
    db_session.expire_all()
    return db_session.execute(select(Source).where(Source.id == source_id)).scalar_one()


# --- Malformed-output / API-failure -> status=failed, zero cards -------------


def test_validation_error_ends_in_failed_with_no_cards(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="stored")
    generator = _ScriptedGenerator([FlashcardValidationError("bad tool-call input")])

    with _with_generator(base_client, generator):
        response = base_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    result = _fresh_source_status(db_session, source.id)
    assert result.status == "failed"
    assert result.error_message is not None
    assert result.error_message != ""
    assert _cards_for(db_session, source.id) == []


def test_api_error_ends_in_failed_with_no_cards(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="stored")
    generator = _ScriptedGenerator([FlashcardAPIError("Anthropic API call failed: timeout")])

    with _with_generator(base_client, generator):
        response = base_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    result = _fresh_source_status(db_session, source.id)
    assert result.status == "failed"
    assert result.error_message is not None
    assert _cards_for(db_session, source.id) == []


def test_failure_error_message_does_not_leak_exception_internals(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """Decision #7/#8: the persisted error is a generic message, not the raw
    exception text (which could leak SDK/validation internals)."""
    source = _make_source(db_session, my_folder.id, status="stored")
    secret_detail = "raw-anthropic-internal-trace-xyz123"
    generator = _ScriptedGenerator([FlashcardAPIError(secret_detail)])

    with _with_generator(base_client, generator):
        base_client.post(f"/sources/{source.id}/convert")

    result = _fresh_source_status(db_session, source.id)
    assert result.error_message is not None
    assert secret_detail not in result.error_message


# --- Replace-on-retrigger: done -> new convert replaces old cards -------------


def test_retrigger_on_done_source_replaces_cards_no_duplication(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(db_session, my_folder.id, status="stored")

    first_gen = _ScriptedGenerator([_CARDS_A])
    with _with_generator(base_client, first_gen):
        base_client.post(f"/sources/{source.id}/convert")

    first_cards = _cards_for(db_session, source.id)
    assert len(first_cards) == 1
    assert first_cards[0].front == "Q-A1"
    first_card_id = first_cards[0].id
    assert _fresh_source_status(db_session, source.id).status == "done"

    second_gen = _ScriptedGenerator([_CARDS_B])
    with _with_generator(base_client, second_gen):
        response = base_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    final_cards = _cards_for(db_session, source.id)
    assert len(final_cards) == 2
    assert {c.front for c in final_cards} == {"Q-B1", "Q-B2"}
    # The old card's id must be gone -- not just outnumbered -- proving a
    # real delete happened rather than an accumulation.
    assert first_card_id not in {c.id for c in final_cards}
    assert _fresh_source_status(db_session, source.id).status == "done"


# --- Retry on a failed source --------------------------------------------


def test_retrigger_on_failed_source_clears_error_and_retries_to_done(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(
        db_session,
        my_folder.id,
        status="failed",
        error_message="Flashcard generation failed. Please try again.",
    )

    generator = _ScriptedGenerator([_CARDS_A])
    with _with_generator(base_client, generator):
        response = base_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    result = _fresh_source_status(db_session, source.id)
    assert result.status == "done"
    assert result.error_message is None
    cards = _cards_for(db_session, source.id)
    assert len(cards) == 1
    assert cards[0].front == "Q-A1"


def test_retrigger_on_failed_source_can_fail_again(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    source = _make_source(
        db_session,
        my_folder.id,
        status="failed",
        error_message="Flashcard generation failed. Please try again.",
    )

    generator = _ScriptedGenerator([FlashcardValidationError("still malformed")])
    with _with_generator(base_client, generator):
        response = base_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    result = _fresh_source_status(db_session, source.id)
    assert result.status == "failed"
    assert result.error_message is not None
    assert _cards_for(db_session, source.id) == []


def test_retrigger_on_failed_source_with_no_prior_cards_deletes_nothing_unexpected(
    base_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """A failed source has no cards to begin with (the failed generation
    wrote none) -- the delete-before-regenerate step must be a no-op, not an
    error, when there's nothing to delete."""
    source = _make_source(db_session, my_folder.id, status="failed", error_message="boom")
    assert _cards_for(db_session, source.id) == []

    generator = _ScriptedGenerator([_CARDS_A])
    with _with_generator(base_client, generator):
        response = base_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    assert len(_cards_for(db_session, source.id)) == 1
