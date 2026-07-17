# PRD: Ticket 12 — Notes Quiz Mode

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

As a user reading through a note, I have no lightweight way to test my recall of its content
without first converting it into permanent flashcards. Turning a note into `cards` commits it to
the spaced-repetition pipeline (SM-2 scheduling, ongoing review) — sometimes I just want a quick,
disposable read-through quiz over what I just uploaded, independent of whether I ever build a
flashcard deck from it. Without this, the only self-testing tool is flashcard generation, which is
heavier-weight than a one-off comprehension check.

## Solution

A **"Quiz Me"** button on the note view (the same main-editor surface as ticket 06's "Convert to
Flashcards" button), independent of flashcard generation. Clicking it makes exactly **one**
structured/tool-JSON LLM call — reusing the injectable/mockable client boundary from ticket
06 — over the source's full `raw_text`, returning the entire question set at once:
`[{question, answer}]`. The full set is rendered directly into the response with no server-side
session/cache: Next, Previous, and Show Answer are pure client-side JS operating on the
already-fetched array, with no further HTTP round-trips and no further LLM calls. Navigation has
no wraparound past the first or last question. The quiz set is never persisted — no `cards` row,
no SM-2 scheduling — it is a distinct, disposable artifact that exists only for the current page
view.

## User Stories

1. As a user viewing a note, I want a "Quiz Me" button independent of "Convert to Flashcards", so that I can self-test a note's content without committing it to my flashcard deck.
2. As a user, I want to quiz a note I've already converted to flashcards (or vice versa), so that the two features don't block or interfere with each other.
3. As a user, I want clicking "Quiz Me" to generate a full question set in one action, so that I don't wait through multiple LLM round-trips before I can start.
4. As a user, I want a clear loading indicator while the quiz generates, so that I know the click registered and the app isn't frozen.
5. As a user, I want to see one question at a time, so that I'm not spoiled by seeing all answers up front.
6. As a user, I want a "Show Answer" button that reveals the current question's answer, so that I can check my recall before moving on.
7. As a user, I want the answer hidden again when I navigate to a new question, so that I'm not accidentally shown the next answer early.
8. As a user, I want "Next" and "Previous" buttons to move through the generated questions, so that I can review the set at my own pace, forward or backward.
9. As a user, I want "Previous" to do nothing useful on the first question and "Next" to do nothing useful on the last, rather than wrapping around, so that navigation behaves predictably and I always know where the set ends.
10. As a user, I want no further LLM calls to happen while I navigate the quiz, so that the experience is fast and doesn't incur repeated cost/latency after generation.
11. As a user, I want no free-text answer input during the quiz, so that the interaction stays a simple read-and-reveal check, not a graded exercise.
12. As a user, I want the quiz set to be disposable — not saved as flashcards and not affecting my spaced-repetition schedule — so that a casual comprehension check never pollutes my real review queue.
13. As a user, I want a clear error if the note is too long to quiz in one call, so that I understand why generation failed rather than seeing a silent or partial result.
14. As a user, I want a clear error if the LLM's output is malformed, so that I know generation failed rather than seeing a broken or empty quiz.
15. As the developer, I want the quiz LLM call to reuse ticket 06's injectable/mockable client boundary, so that no second client abstraction is introduced for the same underlying model integration.

## Implementation Decisions

- **LLM call & schema:** One call per quiz start (never zero, never more than one), using ticket
  06's Anthropic client boundary (`claude-sonnet-5`, structured/tool JSON), over the source's full
  `raw_text`. Response validated by a Pydantic model as a strict `list[QuizQuestion]` where
  `QuizQuestion` is `{question: str, answer: str}`. Malformed output is a generation failure
  surfaced to the user; nothing partial is shown.
- **Chunking / oversized notes (v1 limitation):** If ticket 05's chunking helper determines the
  note's `raw_text` doesn't fit in a single LLM call, quiz generation fails clearly (e.g. "note too
  long for quiz generation") rather than issuing multiple calls and merging results. Multi-chunk
  quiz generation (dedup, ordering, partial-failure handling across chunks) is explicitly deferred
  — the ticket plan specifies exactly one LLM call per quiz start with no merge logic.
- **State storage (no server-side session):** The generated question set is embedded directly into
  the response the "Quiz Me" click returns (inline JSON data for client-side JS to read — e.g. a
  `<script type="application/json">` block or data attributes). No server-side session, cache, or
  session-id concept is introduced. Next, Previous, and Show Answer are pure client-side state
  transitions (a JS index into the array plus a per-question shown/hidden flag) with zero
  additional network calls. This is a deliberate, narrow departure from the project's default
  HTMX-GET-swap interaction style, justified because there is no further server round-trip to make
  once the one-shot generation completes.
- **Generation UX (synchronous, no polling):** Unlike ticket 06's BackgroundTasks + polling-popup
  pattern (justified there by potentially large flashcard batches), this ticket's work is capped at
  exactly one bounded LLM call, so "Quiz Me" is a single synchronous POST that returns the
  rendered quiz directly. The loading UX is a disabled-button/spinner state for the duration of that
  one request — no background job, no status-polling endpoint, no job-state tracking.
- **Navigation bounds:** Previous is disabled/no-ops at index 0; Next is disabled/no-ops at the
  last index. No wraparound in either direction.
- **Show Answer scope:** Per-question and reset on navigation — arriving at any question always
  starts with its answer hidden, regardless of prior toggle state on other questions.
- **Placement & independence:** The "Quiz Me" button lives in the note view's main-editor surface,
  as a sibling to ticket 06's "Convert to Flashcards" button, with no dependency on the source's
  flashcard-generation `status`. A source can be quizzed with or without ever being converted to
  flashcards, and converting to flashcards does not block or reset quizzing (or vice versa).
- **No persistence:** No new DB table, no write to `cards`, no tie to SM-2 defaults, `due_date`, or
  `reviews`. Refreshing the page or navigating away discards the quiz; clicking "Quiz Me" again
  triggers a fresh LLM call and a fresh set — regeneration is not blocked or cached.

## Testing Decisions

- **What makes a good test:** asserts externally observable behavior at the two seams the plan
  calls out — the LLM boundary's request/response contract, and the HTTP response the "Quiz Me"
  endpoint returns — not client-side JS internals (navigation/toggle logic is DOM state, out of
  scope for backend test seams though worth a light manual/browser check).
- **LLM boundary (mocked):** a canned structured JSON response covering multiple `{question,
  answer}` pairs is asserted to flow through into the rendered response; a malformed-output case
  (schema-invalid JSON) is asserted to fail generation cleanly with a clear error and no partial
  question set rendered. A too-long-note case (chunking helper reports overflow) is asserted to
  fail before any LLM call is made.
- **HTTP/session seam:** start quiz (`POST` from the note view) → response contains the full
  question set (all questions embedded, not just the first) → and, since there is no
  server-side navigation endpoint by design, a test asserting **no second LLM call occurs** for
  what would be "Next/Previous/Show Answer" actions (i.e. those actions never hit the server at
  all — verified by there being no corresponding route, and by the mocked LLM client being invoked
  exactly once per "Quiz Me" click, not once per subsequent interaction).
- **Modules tested:** the quiz-generation route (happy path, malformed-LLM-output failure,
  oversized-note failure), the Pydantic `QuizQuestion`/list validation, and reuse of ticket 06's
  client boundary (same injection point, different prompt/schema).
- **Prior art:** ticket 06's mocked-LLM-client test pattern and Pydantic-validated structured JSON
  approach; ticket 03's HTTP-seam test harness (FastAPI `TestClient` + real Postgres via
  testcontainers). No new test seam is introduced — this ticket reuses both.

## Out of Scope

- Multi-call chunked quiz generation for notes exceeding one call's context (v1 fails clearly
  instead; see decisions.md #2).
- Server-side quiz-session/cache storage keyed by a session id (decisions.md #3).
- Processing-popup/polling infrastructure for quiz generation (decisions.md #4) — a future ticket
  if latency in practice warrants it.
- Free-text answer input, answer grading, or any LLM call during navigation.
- Persisting the quiz set as `cards`, tying it to SM-2 scheduling, or logging it as a `reviews`
  entry — it is not a review mode.
- Any change to ticket 06's flashcard-generation flow, its `cards`/`sources.status` semantics, or
  its BackgroundTasks/polling pattern — this ticket only reuses its LLM client boundary.

## Further Notes

- This ticket is blocked on ticket 05 (needs `sources.raw_text` and its chunking helper to detect
  the too-long case) and reuses the LLM client boundary established by ticket 06. As of this
  writing, neither ticket 05 nor ticket 06 has published GitHub issues yet (both are being planned
  in parallel), so issues created for this ticket reference them in prose rather than by issue
  number; the reference should be updated once those issues exist.
- See [decisions.md](decisions.md) for the full rationale behind each locked decision, including
  the accepted v1 limitation on oversized notes (#2) and the deliberate departure from the
  project's default HTMX-GET-swap style for post-generation navigation (#3).
