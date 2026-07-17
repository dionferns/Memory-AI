from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from memory_ai.flashcards import (
    MAX_CARDS,
    MODEL,
    AnthropicFlashcardGenerator,
    FlashcardAPIError,
    FlashcardValidationError,
    GeneratedCard,
)


def _tool_use_response(input_data: dict[str, Any]) -> SimpleNamespace:
    """Build a fake Anthropic ``Message`` response with a single tool_use block."""
    block = SimpleNamespace(type="tool_use", input=input_data, name="emit_flashcards")
    return SimpleNamespace(content=[block])


def _text_only_response(text: str = "no tool call here") -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


def _make_client(response: SimpleNamespace | None = None, error: Exception | None = None) -> Any:
    client = MagicMock(spec=anthropic.Anthropic)
    if error is not None:
        client.messages.create.side_effect = error
    else:
        client.messages.create.return_value = response
    return client


def test_generate_returns_valid_cards_from_tool_call() -> None:
    response = _tool_use_response(
        {
            "cards": [
                {"question": "What is the capital of France?", "answer": "Paris"},
                {"question": "What is 2+2?", "answer": "4"},
            ]
        }
    )
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    cards = generator.generate("Some study notes about France and arithmetic.")

    assert cards == [
        GeneratedCard(question="What is the capital of France?", answer="Paris"),
        GeneratedCard(question="What is 2+2?", answer="4"),
    ]


def test_generate_calls_anthropic_with_forced_tool_use_and_expected_params() -> None:
    response = _tool_use_response({"cards": [{"question": "Q", "answer": "A"}]})
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    generator.generate("notes")

    client.messages.create.assert_called_once()
    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == MODEL
    assert kwargs["max_tokens"] == 4096
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_flashcards"}
    assert kwargs["tools"][0]["name"] == "emit_flashcards"
    assert kwargs["messages"] == [{"role": "user", "content": "notes"}]
    assert "temperature" not in kwargs
    assert "spaced-repetition flashcards" in kwargs["system"]


def test_generate_raises_validation_error_when_no_tool_use_block() -> None:
    client = _make_client(response=_text_only_response())
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardValidationError):
        generator.generate("notes")


def test_generate_raises_validation_error_on_missing_answer_field() -> None:
    response = _tool_use_response({"cards": [{"question": "Q only"}]})
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardValidationError):
        generator.generate("notes")


def test_generate_raises_validation_error_on_blank_field() -> None:
    response = _tool_use_response({"cards": [{"question": "   ", "answer": "A"}]})
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardValidationError):
        generator.generate("notes")


def test_generate_raises_validation_error_on_empty_cards_array() -> None:
    response = _tool_use_response({"cards": []})
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardValidationError):
        generator.generate("notes")


def test_generate_raises_validation_error_when_cards_array_exceeds_cap() -> None:
    too_many = [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(MAX_CARDS + 1)]
    response = _tool_use_response({"cards": too_many})
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardValidationError):
        generator.generate("notes")


def test_generate_accepts_exactly_max_cards() -> None:
    exactly_max = [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(MAX_CARDS)]
    response = _tool_use_response({"cards": exactly_max})
    client = _make_client(response=response)
    generator = AnthropicFlashcardGenerator(client=client)

    cards = generator.generate("notes")

    assert len(cards) == MAX_CARDS


def test_generate_wraps_anthropic_api_error() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APIConnectionError(request=request)
    client = _make_client(error=error)
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardAPIError):
        generator.generate("notes")


def test_generate_wraps_rate_limit_error() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=429, request=request)
    error = anthropic.RateLimitError("rate limited", response=response, body=None)
    client = _make_client(error=error)
    generator = AnthropicFlashcardGenerator(client=client)

    with pytest.raises(FlashcardAPIError):
        generator.generate("notes")
