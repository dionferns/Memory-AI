"""Unit tests for the shipped client-side navigation-bounds logic.

Ticket 12 issue #65's PRD/decisions.md explicitly scope client-side JS
internals out of the backend HTTP-seam tests ("navigation/toggle logic is
DOM state, out of scope for backend test seams though worth a light
manual/browser check"). This project has no browser-automation harness, but
the no-wraparound bounds logic (decisions.md #5) is important enough to
verify against the *actual shipped file* rather than only by inspection, so
it's factored out of ``src/memory_ai/static/quiz.js`` into small, DOM-free
pure functions (``clampNext``/``clampPrev``/``isFirst``/``isLast``) and
exercised here directly under Node -- no browser, no jsdom, no new Python
test dependency.

Node ships on GitHub's ``ubuntu-latest`` runners (this project's CI image),
and is commonly present in web-project dev environments; if it's missing
locally, this test is skipped rather than failing the whole suite, since
Node isn't otherwise a dependency of this Python project.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_QUIZ_JS = Path(__file__).resolve().parent.parent / "src" / "memory_ai" / "static" / "quiz.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def _run_node_expression(expression: str) -> str:
    script = f"const m = require({json.dumps(str(_QUIZ_JS))}); {expression}"
    env = {**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0"}
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_quiz_js_file_exists() -> None:
    assert _QUIZ_JS.is_file()


def test_next_advances_by_one_when_not_at_last_index() -> None:
    out = _run_node_expression("console.log(m.clampNext(0, 3));")
    assert out == "1"


def test_next_no_ops_at_the_last_index_no_wraparound() -> None:
    out = _run_node_expression("console.log(m.clampNext(2, 3));")
    assert out == "2"


def test_next_no_ops_on_a_single_question_set() -> None:
    out = _run_node_expression("console.log(m.clampNext(0, 1));")
    assert out == "0"


def test_previous_moves_back_by_one_when_not_at_first_index() -> None:
    out = _run_node_expression("console.log(m.clampPrev(2));")
    assert out == "1"


def test_previous_no_ops_at_the_first_index_no_wraparound() -> None:
    out = _run_node_expression("console.log(m.clampPrev(0));")
    assert out == "0"


def test_is_first_and_is_last_bounds() -> None:
    out = _run_node_expression(
        "console.log(JSON.stringify([m.isFirst(0), m.isFirst(1), m.isLast(2, 3), m.isLast(1, 3)]));"
    )
    assert json.loads(out) == [True, False, True, False]


def test_full_forward_then_backward_traversal_never_goes_out_of_bounds() -> None:
    """Simulates a full Next...Next...Previous...Previous navigation sequence
    over a 4-question set and asserts the index never exceeds the bounds
    (would fail if wraparound were reintroduced, e.g. `(index + 1) % length`)."""
    script = """
    let index = 0;
    const length = 4;
    const seen = [index];
    for (let i = 0; i < 10; i++) {
        index = m.clampNext(index, length);
        seen.push(index);
    }
    for (let i = 0; i < 10; i++) {
        index = m.clampPrev(index);
        seen.push(index);
    }
    console.log(JSON.stringify({ seen, min: Math.min(...seen), max: Math.max(...seen) }));
    """
    out = _run_node_expression(script)
    result = json.loads(out)
    assert result["min"] == 0
    assert result["max"] == 3
    # After 10 "next" clicks past the end, the index should have clamped at
    # the last index (3), not wrapped back to 0.
    assert result["seen"][10] == 3
    # After 10 "previous" clicks past the start, it should have clamped at 0.
    assert result["seen"][-1] == 0
