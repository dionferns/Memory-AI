"""HTTP-seam tests for the convert-to-flashcards trigger + background job
(ticket 06, issue #76).

Covers the happy path only: a `stored` source with no cards -> `POST
/sources/{id}/convert` -> `status=processing` -> the background job (run
synchronously by Starlette's `TestClient` as part of the same
request/response cycle, per ticket 06's testing decisions) -> `status=done`
with cards persisted using the correct FK/SM-2-default fields. Ownership
enforcement (404 for another user's source) is covered here too since it's
the same pattern as the rest of the app's owned-resource routes. Failure-path
persistence and replace-on-retrigger coverage lives in test_convert_retry.py
(issue #81); polling-fragment content lives in test_convert_status.py
(issue #78).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``), plus ticket 06's `FlashcardGenerator` mock seam -- no real
Anthropic calls are ever made.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.flashcards import GeneratedCard, get_flashcard_generator
from memory_ai.main import app
from memory_ai.models import Card, Folder, Source, Subject, User

TEST_EMAIL = "convert-seam-test-user@example.com"
OTHER_EMAIL = "convert-seam-other-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


class _FakeGenerator:
    """Injectable `FlashcardGenerator` returning canned cards per call.

    Records every `text` argument it was called with, so tests can assert
    chunking behavior without depending on prompt-string internals.
    """

    def __init__(self, cards: list[GeneratedCard]) -> None:
        self._cards = cards
        self.calls: list[str] = []

    def generate(self, text: str) -> list[GeneratedCard]:
        self.calls.append(text)
        return self._cards


@pytest.fixture
def fake_generator() -> _FakeGenerator:
    return _FakeGenerator(
        [
            GeneratedCard(question="What is the capital of France?", answer="Paris"),
            GeneratedCard(question="What is 2+2?", answer="4"),
        ]
    )


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
def authed_client(
    client: TestClient, seeded_user: User, fake_generator: _FakeGenerator
) -> Iterator[TestClient]:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    app.dependency_overrides[get_flashcard_generator] = lambda: fake_generator
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
    db_session: Session, folder_id: int, *, status: str = "stored", raw_text: str = "Some notes."
) -> Source:
    source = Source(
        folder_id=folder_id,
        filename="notes.txt",
        file_type="txt",
        raw_text=raw_text,
        status=status,
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
    return _make_folder(db_session, their_subject.id, "Theirs")


@pytest.fixture
def their_source(db_session: Session, their_folder: Folder) -> Source:
    return _make_source(db_session, their_folder.id)


def test_convert_stored_source_ends_in_done_with_cards(
    authed_client: TestClient,
    db_session: Session,
    my_source: Source,
    fake_generator: _FakeGenerator,
) -> None:
    response = authed_client.post(f"/sources/{my_source.id}/convert")

    assert response.status_code == 200

    db_session.expire_all()
    source = db_session.execute(select(Source).where(Source.id == my_source.id)).scalar_one()
    assert source.status == "done"
    assert source.error_message is None

    cards = (
        db_session.execute(select(Card).where(Card.source_id == my_source.id).order_by(Card.id))
        .scalars()
        .all()
    )
    assert len(cards) == 2
    assert cards[0].front == "What is the capital of France?"
    assert cards[0].back == "Paris"
    assert cards[1].front == "What is 2+2?"
    assert cards[1].back == "4"

    for card in cards:
        assert card.source_id == my_source.id
        assert card.folder_id == my_source.folder_id
        assert card.ease_factor == 2.5
        assert card.interval_days == 0
        assert card.repetitions == 0
        assert card.due_date == date.today()
        assert card.last_reviewed_at is None


def test_convert_calls_generator_with_raw_text(
    authed_client: TestClient,
    db_session: Session,
    my_folder: Folder,
    fake_generator: _FakeGenerator,
) -> None:
    source = _make_source(db_session, my_folder.id, raw_text="Specific unique study content.")

    authed_client.post(f"/sources/{source.id}/convert")

    assert fake_generator.calls == ["Specific unique study content."]


def test_convert_chunks_long_text_and_calls_generator_once_per_chunk(
    authed_client: TestClient,
    db_session: Session,
    my_folder: Folder,
    fake_generator: _FakeGenerator,
) -> None:
    long_text = "a" * 250_000  # exceeds parsing.DEFAULT_MAX_CHARS (100_000)
    source = _make_source(db_session, my_folder.id, raw_text=long_text)

    response = authed_client.post(f"/sources/{source.id}/convert")

    assert response.status_code == 200
    # 250_000 chars split at 100_000 chars/chunk with 500-char overlap -> 3 chunks.
    assert len(fake_generator.calls) == 3

    db_session.expire_all()
    cards = db_session.execute(select(Card).where(Card.source_id == source.id)).scalars().all()
    # Two cards generated per chunk call (the fake always returns the same
    # two), concatenated across all three chunks with no dedup (decision #9).
    assert len(cards) == 6


def test_convert_other_users_source_returns_404_and_does_not_run(
    authed_client: TestClient,
    db_session: Session,
    their_source: Source,
    fake_generator: _FakeGenerator,
) -> None:
    response = authed_client.post(f"/sources/{their_source.id}/convert")

    assert response.status_code == 404
    assert fake_generator.calls == []

    db_session.expire_all()
    source = db_session.execute(select(Source).where(Source.id == their_source.id)).scalar_one()
    assert source.status == "stored"


def test_convert_nonexistent_source_returns_404(authed_client: TestClient) -> None:
    response = authed_client.post("/sources/999999999/convert")

    assert response.status_code == 404


def test_convert_unauthenticated_is_rejected(client: TestClient, my_source: Source) -> None:
    response = client.post(
        f"/sources/{my_source.id}/convert",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
