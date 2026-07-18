"""HTTP-seam tests for the quiz UI layer (ticket 12, issue #65).

Issue #64's tests (``test_quiz_route.py``) cover the generation route's own
contract. This file covers #65's server-observable guarantees on top of
that: the "Quiz Me" trigger is present on the folder view (the current
main-editor surface for sources, per ``src/memory_ai/quiz.py``'s module
docstring) regardless of any flashcard-generation state, the initial markup
renders the first question with its answer hidden (client-side JS then
takes over from there -- see ``test_quiz_nav_js.py`` for the navigation
logic itself), there is no second HTTP route for Next/Previous/Show Answer,
and a generation failure never leaves partial/broken quiz markup behind.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.main import app
from memory_ai.models import Folder, Source, Subject, User
from memory_ai.quiz import QuizQuestion, QuizValidationError, get_quiz_generator

TEST_EMAIL = "quiz-ui-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


class _FakeQuizGenerator:
    def __init__(
        self,
        questions: list[QuizQuestion] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._questions = questions or []
        self._error = error
        self.call_count = 0

    def generate(self, text: str) -> list[QuizQuestion]:
        self.call_count += 1
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


@pytest.fixture
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    folder = Folder(subject_id=my_subject.id, name="Caching", created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


@pytest.fixture
def my_source(db_session: Session, my_folder: Folder) -> Source:
    source = Source(
        folder_id=my_folder.id,
        filename="notes.txt",
        file_type="txt",
        raw_text="Caching stores frequently accessed data.",
        status="stored",
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _override_generator(generator: _FakeQuizGenerator) -> None:
    app.dependency_overrides[get_quiz_generator] = lambda: generator


@pytest.fixture(autouse=True)
def _clear_generator_override() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_quiz_generator, None)


def test_quiz_me_button_appears_on_the_folder_view_for_every_source(
    authed_client: TestClient, my_folder: Folder, my_source: Source
) -> None:
    """The folder view is the current main-editor surface for sources (no
    dedicated per-note detail page exists yet -- see quiz.py's module
    docstring). The "Quiz Me" trigger must appear there for every source,
    with no dependency on any flashcard-generation state (this app has no
    such state wired up yet either, so this is trivially satisfied -- the
    button is unconditional)."""
    response = authed_client.get(f"/folders/{my_folder.id}")

    assert response.status_code == 200
    assert f'id="quiz-me-{my_source.id}"' in response.text
    assert f'hx-post="/sources/{my_source.id}/quiz"' in response.text


def test_quiz_js_static_asset_is_served(authed_client: TestClient) -> None:
    response = authed_client.get("/static/quiz.js")

    assert response.status_code == 200
    assert "MemoryAIQuiz" in response.text
    assert "clampNext" in response.text


def test_generate_quiz_renders_first_question_with_answer_hidden_and_wires_navigation(
    authed_client: TestClient, my_source: Source
) -> None:
    questions = [
        QuizQuestion(question="What does a cache store?", answer="Frequently accessed data."),
        QuizQuestion(question="Why use a cache?", answer="To reduce latency."),
    ]
    generator = _FakeQuizGenerator(questions=questions)
    _override_generator(generator)

    response = authed_client.post(f"/sources/{my_source.id}/quiz")

    assert response.status_code == 200
    text = response.text
    # Server-rendered starting state: the answer paragraph is present but
    # marked `hidden` by default -- client-side JS (quiz.js) is what reveals
    # it on "Show Answer" and re-hides it on navigation (out of scope for
    # this HTTP seam; see test_quiz_nav_js.py for that logic itself).
    assert f'id="quiz-answer-{my_source.id}" hidden' in text
    assert f'id="quiz-question-{my_source.id}"' in text
    assert f'id="quiz-show-answer-{my_source.id}"' in text
    assert f'id="quiz-prev-{my_source.id}"' in text
    assert f'id="quiz-next-{my_source.id}"' in text
    # The navigation script is included and initialized for this source.
    assert '<script src="/static/quiz.js"></script>' in text
    assert f'MemoryAIQuiz.init("{my_source.id}")' in text


def test_no_navigation_route_exists_and_generator_is_called_exactly_once(
    authed_client: TestClient, my_source: Source
) -> None:
    """Encodes decisions.md #3: Next/Previous/Show Answer never reach the
    server at all -- they're pure client-side JS over the array embedded by
    the single "Quiz Me" response. Verified here the way this ticket's own
    testing decisions prescribe: (a) no HTTP route exists that a "Next" or
    "Previous" click could even hit, and (b) the mocked LLM client is
    invoked exactly once for the one "Quiz Me" click and no more -- the
    backend-observable equivalent of "network-request count stays at one
    across a full navigation sequence" (there is nothing left to request).
    """
    generator = _FakeQuizGenerator(questions=[QuizQuestion(question="Q", answer="A")])
    _override_generator(generator)

    response = authed_client.post(f"/sources/{my_source.id}/quiz")
    assert response.status_code == 200
    assert generator.call_count == 1

    nav_like_paths = [
        route.path
        for route in app.routes
        if hasattr(route, "path")
        and (
            "next" in route.path.lower()
            or "previous" in route.path.lower()
            or "show-answer" in route.path.lower()
            or "show_answer" in route.path.lower()
        )
    ]
    assert nav_like_paths == []
    # Nothing else could have called the generator -- the count from the
    # single "Quiz Me" click is unchanged.
    assert generator.call_count == 1


def test_generation_failure_renders_error_with_no_partial_quiz_markup(
    authed_client: TestClient, my_source: Source
) -> None:
    generator = _FakeQuizGenerator(error=QuizValidationError("invalid emit_quiz input"))
    _override_generator(generator)

    response = authed_client.post(f"/sources/{my_source.id}/quiz")

    assert response.status_code == 502
    assert f'id="quiz-error-{my_source.id}"' in response.text
    # No broken/partial quiz UI leaks into the failure response.
    assert f'id="quiz-app-{my_source.id}"' not in response.text
    assert f'id="quiz-question-{my_source.id}"' not in response.text
    assert "MemoryAIQuiz.init" not in response.text
