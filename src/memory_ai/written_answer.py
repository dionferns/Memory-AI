"""LLM client boundary for written-answer grading (ticket 11, issue #68).

Reuses the exact structured/tool-JSON client-boundary pattern ticket 06
establishes in ``memory_ai.flashcards`` (forced tool use, one-step Pydantic
validation of the tool call's ``input``) rather than inventing a second
LLM-calling convention -- see ``tickets/11-written-answer-feedback/decisions.md``
#1/#2.

Grades a learner's free-text ``user_answer`` against a card's ``gold_answer``
for a given ``question`` into one of three bands (``perfect``/``good``/
``wrong``) plus 1-2 sentences of ``feedback``. Per decisions.md #3, a
network/timeout error, an unparseable/missing tool-call response, and a
schema-shaped-but-out-of-enum ``outcome`` are all classified identically as
``WrittenAnswerGradingError`` -- there is exactly one failure path, so the
caller (ticket 11's review UI, a later slice) has exactly one fallback to
implement, not several.

No DB/HTTP/UI code lives here -- purely the LLM boundary + its Pydantic
output model, mirroring ``memory_ai.flashcards``.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, cast

import anthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from pydantic import BaseModel, ValidationError

from memory_ai.config import get_settings

MODEL = "claude-sonnet-5"
MAX_TOKENS = 1024

# Client-side timeout on the grading call (decisions.md #8). The review flow
# is synchronous/interactive, so this bounds how long a single card's
# "Grading..." state can hang before the caller's fallback kicks in.
TIMEOUT_SECONDS = 30.0

_SYSTEM_PROMPT = (
    "You are grading a learner's written answer to a flashcard question against "
    "the gold answer. Use exactly three bands: 'perfect' (fully correct, nothing "
    "material missing or wrong), 'good' (substantially correct, minor omission or "
    "imprecision), 'wrong' (materially incorrect, missing the key point, or "
    "off-topic/empty). Write 1-2 sentences of feedback addressed to the learner "
    "explaining the gap, or affirming correctness -- never a bare restatement of "
    "the gold answer."
)

_TOOL_NAME = "emit_grading"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "Emit the grading outcome and feedback for the learner's written answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": ["perfect", "good", "wrong"]},
            "feedback": {"type": "string"},
        },
        "required": ["outcome", "feedback"],
    },
}


class WrittenAnswerGradingError(Exception):
    """Raised for any failure grading a written answer.

    Covers a network/timeout error, any other Anthropic API failure, a
    missing/unparseable tool-call response, and a schema-shaped tool call
    whose ``outcome`` falls outside ``{perfect, good, wrong}`` -- decisions.md
    #3 treats all of these identically as "call failed" so callers have
    exactly one fallback path (manual flip-and-grade), not several.
    """


class WrittenAnswerOutcome(BaseModel):
    """Validated grading result: a three-way outcome band + short feedback."""

    outcome: Literal["perfect", "good", "wrong"]
    feedback: str


def grade_written_answer(
    client: anthropic.Anthropic, question: str, gold_answer: str, user_answer: str
) -> WrittenAnswerOutcome:
    """Grade ``user_answer`` against ``gold_answer`` for ``question`` via the LLM.

    ``client`` is an injectable Anthropic SDK client (constructor-injected in
    tests with a mock so no test ever makes a real network call), matching
    ticket 06's ``AnthropicFlashcardGenerator`` seam. Raises
    ``WrittenAnswerGradingError`` for any of the failure modes described on
    the class docstring; never returns a partially-valid result.
    """
    user_content = (
        f"Question: {question}\n\nGold answer: {gold_answer}\n\nLearner's answer: {user_answer}"
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=[cast(ToolParam, _TOOL_SCHEMA)],
            tool_choice=cast(ToolChoiceToolParam, {"type": "tool", "name": _TOOL_NAME}),
            messages=[cast(MessageParam, {"role": "user", "content": user_content})],
            timeout=TIMEOUT_SECONDS,
        )
    except anthropic.APIError as exc:
        # Covers network errors, non-2xx responses, and timeouts:
        # `anthropic.APITimeoutError` is itself an `anthropic.APIError`
        # subclass, so a timed-out call lands in this same branch.
        raise WrittenAnswerGradingError(f"Anthropic API call failed: {exc}") from exc

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise WrittenAnswerGradingError("model response contained no tool_use block")

    try:
        return WrittenAnswerOutcome.model_validate(tool_use.input)
    except ValidationError as exc:
        # Covers both an unparseable/missing field and a schema-shaped-but-
        # out-of-enum `outcome` value (Pydantic's `Literal` validation
        # rejects it the same way it would reject a missing field).
        raise WrittenAnswerGradingError(f"invalid emit_grading input: {exc}") from exc


class WrittenAnswerGrader(Protocol):
    """Boundary a caller (ticket 11's review UI, a later slice) depends on.

    Tests inject a fake/mock implementation of this protocol; the real
    implementation (``AnthropicWrittenAnswerGrader``) calls the Anthropic
    API via ``grade_written_answer``. Mirrors ``memory_ai.flashcards``'s
    ``FlashcardGenerator`` protocol so there is one DI pattern for LLM
    boundaries across the codebase.
    """

    def grade(self, question: str, gold_answer: str, user_answer: str) -> WrittenAnswerOutcome:
        """Grade ``user_answer``, raising ``WrittenAnswerGradingError`` on any failure."""
        ...


class AnthropicWrittenAnswerGrader:
    """Real ``WrittenAnswerGrader`` backed by the Anthropic SDK's sync client.

    The Anthropic client is injectable (constructor parameter, defaulting to
    a real client built from ``memory_ai.config.get_settings()``) so tests can
    substitute a fake/mock client and never make a real network call.
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    def grade(self, question: str, gold_answer: str, user_answer: str) -> WrittenAnswerOutcome:
        return grade_written_answer(self._client, question, gold_answer, user_answer)


def get_written_answer_grader() -> WrittenAnswerGrader:
    """FastAPI dependency providing the real ``WrittenAnswerGrader``.

    Overridden in tests with a fake/mock implementation so no test ever
    makes a real Anthropic API call.
    """
    return AnthropicWrittenAnswerGrader()
