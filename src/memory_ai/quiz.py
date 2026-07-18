"""Notes-quiz feature: one-shot LLM quiz generation and its HTTP route.

Ticket 12 (see ``tickets/12-notes-quiz/PRD.md`` and ``decisions.md``). Reuses
ticket 06's injectable/mockable Anthropic client boundary pattern (decision
#9) rather than inventing a second client abstraction -- only the prompt and
response schema differ (quiz Q&A vs. flashcard Q&A). The generated quiz set
is never persisted (decision #8): this module creates no new DB table and
writes nothing to ``cards``.

The quiz-generation route lives in this same module (rather than
``hierarchy.py``) since it is a distinct, self-contained feature slice: a
Pydantic schema, an LLM boundary, and a single synchronous route, with no
shared mutable state with the subject/folder/source CRUD routes beyond
read-only ownership lookups.

This is issue #64's slice only: the route makes exactly one LLM call and
returns the complete, ordered question set embedded in the response (a
``<script type="application/json">`` block per decisions.md #3). It
deliberately renders no interactive markup yet -- the "Quiz Me" trigger
button and the client-side Next/Previous/Show Answer navigation over this
embedded set are issue #65's slice, layered on top of this same response
fragment without changing this route's contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

import anthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai import parsing
from memory_ai.auth import current_user
from memory_ai.config import get_settings
from memory_ai.database import get_db
from memory_ai.models import Folder, Source, Subject, User

MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096
MAX_QUESTIONS = 100

_SYSTEM_PROMPT = (
    "You are generating a short comprehension quiz from a user's study note. "
    "Produce clear, self-contained question/answer pairs covering the key "
    "facts and concepts in the text, in the same order they appear. Do not "
    "pad with trivial or duplicate questions. This quiz is a disposable, "
    "one-off comprehension check -- not a spaced-repetition flashcard deck."
)

_TOOL_NAME = "emit_quiz"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "Emit the generated quiz as a structured, ordered list of Q&A pairs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_QUESTIONS,
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "required": ["question", "answer"],
                },
            }
        },
        "required": ["questions"],
    },
}

# User-facing messages. Exact strings, not derived at call sites, so both the
# route and its tests reference the same constant instead of independently
# retyped prose that could drift apart.
TOO_LONG_MESSAGE = "note too long for quiz generation"
GENERATION_FAILED_MESSAGE = "quiz generation failed -- please try again."
EMPTY_NOTE_MESSAGE = "this note has no text to quiz on yet."


class QuizGenerationError(Exception):
    """Base exception for the quiz-generation LLM boundary."""


class QuizValidationError(QuizGenerationError):
    """Raised when the model's ``emit_quiz`` tool-call output is malformed.

    Covers a missing tool call, a missing/blank ``question`` or ``answer``
    field, an empty ``questions`` array, and an over-cap ``questions`` array.
    """


class QuizAPIError(QuizGenerationError):
    """Raised when the Anthropic API call itself fails.

    Wraps timeouts, rate limits, and other network/API errors raised by the
    Anthropic SDK so callers never need to catch SDK-specific exception
    types.
    """


class QuizQuestion(BaseModel):
    """A single validated question/answer pair produced by the LLM."""

    question: str
    answer: str

    @field_validator("question", "answer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class _EmitQuizInput(BaseModel):
    """Validates the raw ``emit_quiz`` tool-call input in one all-or-nothing step."""

    questions: list[QuizQuestion]

    @field_validator("questions")
    @classmethod
    def _non_empty_and_capped(cls, value: list[QuizQuestion]) -> list[QuizQuestion]:
        if not value:
            raise ValueError("questions must not be empty")
        if len(value) > MAX_QUESTIONS:
            raise ValueError(f"questions must not exceed {MAX_QUESTIONS} entries")
        return value


class QuizGenerator(Protocol):
    """Boundary the quiz-generation route depends on.

    Tests inject a fake/mock implementation of this protocol; the real
    implementation (``AnthropicQuizGenerator``) calls the Anthropic API.
    """

    def generate(self, text: str) -> list[QuizQuestion]:
        """Generate a quiz from ``text``, raising on any malformed output."""
        ...


class AnthropicQuizGenerator:
    """Real ``QuizGenerator`` backed by the Anthropic SDK's sync client.

    The Anthropic client is injectable (constructor parameter, defaulting to
    a real client built from ``memory_ai.config.get_settings()``) so tests
    can substitute a fake/mock client and never make a real network call --
    the exact same pattern ``AnthropicFlashcardGenerator`` (ticket 06)
    already establishes.
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    def generate(self, text: str) -> list[QuizQuestion]:
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[cast(ToolParam, _TOOL_SCHEMA)],
                tool_choice=cast(ToolChoiceToolParam, {"type": "tool", "name": _TOOL_NAME}),
                messages=[cast(MessageParam, {"role": "user", "content": text})],
            )
        except anthropic.APIError as exc:
            raise QuizAPIError(f"Anthropic API call failed: {exc}") from exc

        tool_use = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_use is None:
            raise QuizValidationError("model response contained no tool_use block")

        try:
            parsed = _EmitQuizInput.model_validate(tool_use.input)
        except ValidationError as exc:
            raise QuizValidationError(f"invalid emit_quiz input: {exc}") from exc

        return parsed.questions


def get_quiz_generator() -> QuizGenerator:
    """FastAPI dependency returning the real generator; overridden in tests."""
    return AnthropicQuizGenerator()


# --- POST /sources/{source_id}/quiz ------------------------------------------

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_owned_source(db: Session, source_id: int, user_id: int) -> Source:
    """Fetch a source scoped to ``user_id`` via a join through folder -> subject.

    Same ownership pattern as ``hierarchy._get_owned_folder``: a source that
    doesn't exist, or whose owning folder/subject belongs to another user,
    raises a plain 404 -- never a 403 -- so ownership can't be probed for.
    """
    source = db.execute(
        select(Source)
        .join(Folder, Source.folder_id == Folder.id)
        .join(Subject, Folder.subject_id == Subject.id)
        .where(Source.id == source_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404)
    return source


@router.post("/sources/{source_id}/quiz")
def generate_quiz(
    source_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    generator: QuizGenerator = Depends(get_quiz_generator),  # noqa: B008
) -> Response:
    """Generate a one-shot quiz over a source's full ``raw_text``.

    Synchronous, single-call, stateless (decisions #2/#4/#8): no
    BackgroundTasks, no polling, no persistence -- the full question set is
    rendered directly into the response. If ticket 05's chunking helper
    reports the note doesn't fit in one LLM call, this fails clearly
    *before* the LLM is ever invoked. On malformed LLM output or an
    Anthropic API failure, this fails clearly with nothing written to the
    DB (this route creates no rows at all, success or failure).
    """
    source = _get_owned_source(db, source_id, user.id)

    # Guard against an empty/whitespace-only note (e.g. a source that hasn't
    # been parsed yet, or parsed to nothing): `chunk_text("")` returns `[""]`
    # (length 1), which would otherwise slip past the too-long check below and
    # burn an LLM call on blank input, surfacing as an opaque 502. Fail clearly
    # and cheaply here instead, before the LLM is ever invoked (issue #124).
    if not source.raw_text.strip():
        return templates.TemplateResponse(
            request,
            "_quiz_result.html",
            {"source": source, "error": EMPTY_NOTE_MESSAGE},
            status_code=422,
        )

    chunks = parsing.chunk_text(source.raw_text)
    if len(chunks) > 1:
        return templates.TemplateResponse(
            request,
            "_quiz_result.html",
            {"source": source, "error": TOO_LONG_MESSAGE},
            status_code=422,
        )

    try:
        questions = generator.generate(source.raw_text)
    except QuizGenerationError:
        return templates.TemplateResponse(
            request,
            "_quiz_result.html",
            {"source": source, "error": GENERATION_FAILED_MESSAGE},
            status_code=502,
        )

    return templates.TemplateResponse(
        request,
        "_quiz_result.html",
        {"source": source, "questions": [q.model_dump() for q in questions]},
    )
