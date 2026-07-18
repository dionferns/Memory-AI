"""HTTP-seam tests for one-shot quiz generation (ticket 12, issue #64).

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``) -- same pattern as ``test_upload.py``. The Anthropic client
is never touched: ``get_quiz_generator`` is overridden with an in-memory fake
that records every call, so a call-count assertion is a real check on
whether the LLM boundary was invoked, not a trivial mock formality.

Covers issue #64's route contract: happy path (the complete, ordered
question set is embedded in the response), malformed-output failure (clean
error, no DB write), and oversized-note failure (the chunking helper's
overflow is caught before the LLM mock is ever invoked). Issue #65's UI
layer (the "Quiz Me" button and client-side navigation over this same
response) is covered separately once that slice lands.
"""

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.main import app
from memory_ai.models import Card, Folder, Source, Subject, User
from memory_ai.quiz import (
    GENERATION_FAILED_MESSAGE,
    TOO_LONG_MESSAGE,
    QuizQuestion,
    QuizValidationError,
    get_quiz_generator,
)

TEST_EMAIL = "quiz-seam-test-user@example.com"
OTHER_EMAIL = "quiz-seam-other-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


class _FakeQuizGenerator:
    """Records every call; never touches the network."""

    def __init__(
        self,
        questions: list[QuizQuestion] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._questions = questions or []
        self._error = error
        self.call_count = 0
        self.received_text: list[str] = []

    def generate(self, text: str) -> list[QuizQuestion]:
        self.call_count += 1
        self.received_text.append(text)
        if self._error is not None:
            raise self._error
        return self._questions


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


def _make_source(db_session: Session, folder_id: int, raw_text: str) -> Source:
    source = Source(
        folder_id=folder_id,
        filename="notes.txt",
        file_type="txt",
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
    return _make_source(db_session, my_folder.id, "Caching stores frequently accessed data.")


@pytest.fixture
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Theirs")


@pytest.fixture
def their_source(db_session: Session, their_folder: Folder) -> Source:
    return _make_source(db_session, their_folder.id, "Someone else's notes.")


def _extract_embedded_questions(response_text: str, source_id: int) -> list[dict[str, str]]:
    """Pull the ``[{question, answer}, ...]`` payload out of the response's
    embedded ``<script type="application/json">`` block and parse it as real
    JSON, rather than doing raw substring checks against the rendered HTML
    (which Jinja's ``tojson`` filter HTML-escapes -- e.g. apostrophes become
    ``\\u0027`` -- so a plain ``"isn't" in text`` check would be wrong)."""
    pattern = re.compile(
        rf'<script type="application/json" id="quiz-data-{source_id}">(.*?)</script>',
        re.DOTALL,
    )
    match = pattern.search(response_text)
    assert match is not None, "expected an embedded quiz-data script block"
    payload = json.loads(match.group(1))
    assert isinstance(payload, list)
    return payload


def _override_generator(generator: _FakeQuizGenerator) -> None:
    app.dependency_overrides[get_quiz_generator] = lambda: generator


@pytest.fixture(autouse=True)
def _clear_generator_override() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_quiz_generator, None)


def test_generate_quiz_happy_path_returns_full_ordered_question_set(
    authed_client: TestClient, my_source: Source
) -> None:
    questions = [
        QuizQuestion(question="What does a cache store?", answer="Frequently accessed data."),
        QuizQuestion(question="Why use a cache?", answer="To reduce latency."),
        QuizQuestion(question="What is a cache miss?", answer="A lookup that isn't cached."),
    ]
    generator = _FakeQuizGenerator(questions=questions)
    _override_generator(generator)

    response = authed_client.post(f"/sources/{my_source.id}/quiz")

    assert response.status_code == 200
    text = response.text
    # The PRD requires the *complete*, ordered set embedded in the one
    # response -- not just the first question. Parse the embedded JSON
    # structurally (not a substring check) and assert it matches the full,
    # ordered set exactly.
    embedded = _extract_embedded_questions(text, my_source.id)
    assert embedded == [q.model_dump() for q in questions]
    # The question text also appears in the human-readable HTML markup
    # itself is not asserted here (rendering is pure client-side JS,
    # out of scope for this HTTP seam per decisions.md's testing section) --
    # what matters at this seam is that the full set reached the response.
    assert generator.call_count == 1
    assert generator.received_text == [my_source.raw_text]


def test_generate_quiz_malformed_output_fails_clearly_and_writes_nothing(
    authed_client: TestClient, db_session: Session, my_source: Source
) -> None:
    generator = _FakeQuizGenerator(error=QuizValidationError("invalid emit_quiz input"))
    _override_generator(generator)

    response = authed_client.post(f"/sources/{my_source.id}/quiz")

    assert response.status_code == 502
    assert f'<p class="error" id="quiz-error-{my_source.id}">{GENERATION_FAILED_MESSAGE}</p>' in (
        response.text
    )
    # No partial/broken quiz markup leaked into the failure response.
    assert "quiz-question" not in response.text
    assert generator.call_count == 1

    # This ticket creates no new tables and writes nothing on failure --
    # not a new Source, and (this route never touches cards at all) no Card.
    sources = db_session.execute(select(Source)).scalars().all()
    assert len(sources) == 1
    assert sources[0].id == my_source.id
    assert db_session.execute(select(Card)).scalars().all() == []


def test_generate_quiz_oversized_note_fails_before_any_llm_call(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    # Deliberately larger than parsing.DEFAULT_MAX_CHARS (100_000) so
    # chunk_text reports more than one chunk.
    oversized_source = _make_source(db_session, my_folder.id, "x" * 100_001)

    generator = _FakeQuizGenerator(questions=[QuizQuestion(question="Q", answer="A")])
    _override_generator(generator)

    response = authed_client.post(f"/sources/{oversized_source.id}/quiz")

    assert response.status_code == 422
    assert (
        f'<p class="error" id="quiz-error-{oversized_source.id}">{TOO_LONG_MESSAGE}</p>'
        in response.text
    )
    # The whole point of the chunking pre-check: the LLM mock must never be
    # invoked for an oversized note.
    assert generator.call_count == 0
    assert generator.received_text == []

    sources = db_session.execute(select(Source)).scalars().all()
    assert len(sources) == 1
    assert db_session.execute(select(Card)).scalars().all() == []


def test_generate_quiz_exactly_max_chars_note_does_not_trip_the_too_long_path(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    """A note exactly at the chunking boundary still fits in one call."""
    boundary_source = _make_source(db_session, my_folder.id, "x" * 100_000)
    generator = _FakeQuizGenerator(questions=[QuizQuestion(question="Q", answer="A")])
    _override_generator(generator)

    response = authed_client.post(f"/sources/{boundary_source.id}/quiz")

    assert response.status_code == 200
    assert generator.call_count == 1


def test_generate_quiz_requires_authentication(my_source: Source, client: TestClient) -> None:
    response = client.post(f"/sources/{my_source.id}/quiz", follow_redirects=False)
    assert response.status_code in (302, 303, 401)


def test_generate_quiz_on_another_users_source_returns_404(
    authed_client: TestClient, their_source: Source
) -> None:
    generator = _FakeQuizGenerator(questions=[QuizQuestion(question="Q", answer="A")])
    _override_generator(generator)

    response = authed_client.post(f"/sources/{their_source.id}/quiz")

    assert response.status_code == 404
    assert generator.call_count == 0
