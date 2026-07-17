"""LLM client boundary for flashcard generation.

Establishes the injectable, always-mocked-in-tests seam described in
``tickets/06-ai-flashcards/decisions.md`` (decisions #1, #2, #3, #6, #7, #8,
#10, #11, #15). The background job (a later ticket) depends only on the
``FlashcardGenerator`` protocol; tickets 11 and 12 reuse this same seam rather
than inventing their own.

The real implementation calls the Anthropic SDK's sync client with forced
tool use so the model's response is always a structured ``emit_flashcards``
tool call rather than free text. The tool call's ``input`` is validated with
Pydantic in one all-or-nothing step; any validation failure raises
``FlashcardValidationError`` and any Anthropic API failure (timeout, rate
limit, network error) is wrapped in ``FlashcardAPIError`` — both are
catchable, distinct exception types so a caller never has to treat a bad
generation as a silent success.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

import anthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from pydantic import BaseModel, ValidationError, field_validator

from memory_ai.config import get_settings

MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096
MAX_CARDS = 100

_SYSTEM_PROMPT = (
    "You are generating spaced-repetition flashcards from study notes. Produce "
    "clear, atomic question/answer pairs covering the key facts and concepts in "
    "the text. Do not pad with trivial or duplicate cards."
)

_TOOL_NAME = "emit_flashcards"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "Emit the generated flashcards as structured question/answer pairs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CARDS,
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
        "required": ["cards"],
    },
}


class FlashcardGenerationError(Exception):
    """Base exception for the flashcard-generation LLM boundary."""


class FlashcardValidationError(FlashcardGenerationError):
    """Raised when the model's ``emit_flashcards`` tool-call output is malformed.

    Covers a missing tool call, a missing/blank ``question`` or ``answer``
    field, an empty ``cards`` array, and an over-100-entry ``cards`` array.
    """


class FlashcardAPIError(FlashcardGenerationError):
    """Raised when the Anthropic API call itself fails.

    Wraps timeouts, rate limits, and other network/API errors raised by the
    Anthropic SDK so callers never need to catch SDK-specific exception types.
    """


class GeneratedCard(BaseModel):
    """A single validated question/answer pair produced by the LLM."""

    question: str
    answer: str

    @field_validator("question", "answer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class _EmitFlashcardsInput(BaseModel):
    """Validates the raw ``emit_flashcards`` tool-call input in one step."""

    cards: list[GeneratedCard]

    @field_validator("cards")
    @classmethod
    def _non_empty_and_capped(cls, value: list[GeneratedCard]) -> list[GeneratedCard]:
        if not value:
            raise ValueError("cards must not be empty")
        if len(value) > MAX_CARDS:
            raise ValueError(f"cards must not exceed {MAX_CARDS} entries")
        return value


class FlashcardGenerator(Protocol):
    """Boundary the flashcard-generation job depends on.

    Tests inject a fake/mock implementation of this protocol; the real
    implementation (``AnthropicFlashcardGenerator``) calls the Anthropic API.
    """

    def generate(self, text: str) -> list[GeneratedCard]:
        """Generate flashcards from ``text``, raising on any malformed output."""
        ...


class AnthropicFlashcardGenerator:
    """Real ``FlashcardGenerator`` backed by the Anthropic SDK's sync client.

    The Anthropic client is injectable (constructor parameter, defaulting to
    a real client built from ``memory_ai.config.get_settings()``) so tests can
    substitute a fake/mock client and never make a real network call.
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    def generate(self, text: str) -> list[GeneratedCard]:
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
            raise FlashcardAPIError(f"Anthropic API call failed: {exc}") from exc

        tool_use = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_use is None:
            raise FlashcardValidationError("model response contained no tool_use block")

        try:
            parsed = _EmitFlashcardsInput.model_validate(tool_use.input)
        except ValidationError as exc:
            raise FlashcardValidationError(f"invalid emit_flashcards input: {exc}") from exc

        return parsed.cards
