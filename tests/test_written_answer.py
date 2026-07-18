"""Unit tests for the written-answer grading LLM boundary (ticket 11, issue #68).

Mirrors ``tests/test_flashcards.py``'s pattern: a mocked ``anthropic.Anthropic``
client injected into the real grader, never a live network call. Covers the
three canned outcomes plus all three failure modes decisions.md #3 requires
to be classified identically as ``WrittenAnswerGradingError``: unparseable
(missing tool_use) response, a schema-valid-but-out-of-enum ``outcome``, and
a simulated timeout.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from memory_ai.written_answer import (
    MODEL,
    TIMEOUT_SECONDS,
    AnthropicWrittenAnswerGrader,
    WrittenAnswerGradingError,
    WrittenAnswerOutcome,
    grade_written_answer,
)


def _tool_use_response(input_data: dict[str, Any]) -> SimpleNamespace:
    """Build a fake Anthropic ``Message`` response with a single tool_use block."""
    block = SimpleNamespace(type="tool_use", input=input_data, name="emit_grading")
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


# --- canned outcomes ---------------------------------------------------


@pytest.mark.parametrize("outcome_value", ["perfect", "good", "wrong"])
def test_grade_returns_valid_outcome_from_tool_call(outcome_value: str) -> None:
    response = _tool_use_response({"outcome": outcome_value, "feedback": "Some feedback."})
    client = _make_client(response=response)

    result = grade_written_answer(client, "Q?", "gold", "user answer")

    assert result == WrittenAnswerOutcome(outcome=outcome_value, feedback="Some feedback.")  # type: ignore[arg-type]


def test_grader_class_delegates_to_grade_written_answer() -> None:
    response = _tool_use_response({"outcome": "good", "feedback": "Close, but missing X."})
    client = _make_client(response=response)
    grader = AnthropicWrittenAnswerGrader(client=client)

    result = grader.grade("Q?", "gold", "user answer")

    assert result.outcome == "good"
    assert result.feedback == "Close, but missing X."


def test_grade_calls_anthropic_with_forced_tool_use_and_timeout() -> None:
    response = _tool_use_response({"outcome": "perfect", "feedback": "Correct."})
    client = _make_client(response=response)

    grade_written_answer(client, "What is 2+2?", "4", "4")

    client.messages.create.assert_called_once()
    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == MODEL
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_grading"}
    assert kwargs["tools"][0]["name"] == "emit_grading"
    assert kwargs["timeout"] == TIMEOUT_SECONDS
    assert "What is 2+2?" in kwargs["messages"][0]["content"]
    assert "4" in kwargs["messages"][0]["content"]


# --- failure classification (decisions.md #3): must all raise the same type


def test_grade_raises_on_unparseable_response_missing_tool_use() -> None:
    client = _make_client(response=_text_only_response())

    with pytest.raises(WrittenAnswerGradingError):
        grade_written_answer(client, "Q?", "gold", "answer")


def test_grade_raises_on_out_of_enum_outcome() -> None:
    response = _tool_use_response({"outcome": "excellent", "feedback": "Nice."})
    client = _make_client(response=response)

    with pytest.raises(WrittenAnswerGradingError):
        grade_written_answer(client, "Q?", "gold", "answer")


def test_grade_raises_on_missing_feedback_field() -> None:
    response = _tool_use_response({"outcome": "good"})
    client = _make_client(response=response)

    with pytest.raises(WrittenAnswerGradingError):
        grade_written_answer(client, "Q?", "gold", "answer")


def test_grade_raises_on_simulated_timeout() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APITimeoutError(request=request)
    client = _make_client(error=error)

    with pytest.raises(WrittenAnswerGradingError):
        grade_written_answer(client, "Q?", "gold", "answer")


def test_grade_raises_on_generic_api_connection_error() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APIConnectionError(request=request)
    client = _make_client(error=error)

    with pytest.raises(WrittenAnswerGradingError):
        grade_written_answer(client, "Q?", "gold", "answer")


def test_all_three_failure_modes_raise_the_identical_exception_type() -> None:
    """Decisions.md #3: timeout, unparseable JSON, and out-of-enum outcome
    must be indistinguishable to the caller -- exactly one exception type,
    not three."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    timeout_client = _make_client(error=anthropic.APITimeoutError(request=request))
    unparseable_client = _make_client(response=_text_only_response())
    out_of_enum_client = _make_client(
        response=_tool_use_response({"outcome": "not-a-real-band", "feedback": "x"})
    )

    exception_types = set()
    for client in (timeout_client, unparseable_client, out_of_enum_client):
        try:
            grade_written_answer(client, "Q?", "gold", "answer")
        except Exception as exc:  # noqa: BLE001
            exception_types.add(type(exc))

    assert exception_types == {WrittenAnswerGradingError}
