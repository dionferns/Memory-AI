# PRD: Ticket 06 — AI Flashcard Generation

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Turning uploaded notes into flashcards by hand is slow and tedious — the whole point of the app is
that the user shouldn't have to do it. But generation is also the app's most expensive and
failure-prone step (an external LLM call), so it can't run silently and automatically on every
upload: the user needs to control when it happens, see that it's working, and get a clear signal if
it fails. Ticket 05 stores an uploaded note's extracted text as a `sources` row and stops there;
this ticket turns that stored text into saved, review-ready `cards` on explicit user demand.

## Solution

Each source in the main content editor gets a **"Convert to Flashcards"** button. Clicking it
transitions the source to `processing`, schedules a FastAPI `BackgroundTasks` job, and returns
immediately with an HTMX fragment showing a processing popup. The popup polls a status endpoint
every 2 seconds. The background job reads the source's `raw_text` (chunking it via ticket 05's
helper if it exceeds the model's context), calls Claude (`claude-sonnet-5`) through an injectable
`FlashcardGenerator` boundary using forced tool-use for structured `[{question, answer}]` output,
validates the result with Pydantic, and either saves the cards and sets `status=done`, or sets
`status=failed` with an `error_message` and saves nothing. Re-clicking the button on a `done` or
`failed` source re-runs generation, replacing that source's existing cards.

## User Stories

1. As a user, I want a "Convert to Flashcards" button on each uploaded source, so that I decide when generation runs rather than waiting on every upload.
2. As a user, I want a newly uploaded note to show no cards and no processing state until I click the button, so that I'm not confused by cards I didn't ask for or a popup I didn't trigger.
3. As a user, I want the button click to return immediately with a "processing" popup, so that the UI stays responsive during a long LLM call.
4. As a user, I want the popup to clear automatically once cards are ready, so that I don't have to refresh manually.
5. As a user, I want to be told clearly if flashcard generation failed, so that I can retry rather than wonder what happened.
6. As a user, I want a failed or already-completed source's button to work again, so that I can retry a failure or regenerate cards after editing my note.
7. As a user, I want a retry to replace the previous card set rather than pile up duplicates, so that regenerating doesn't leave me with a cluttered, doubled-up deck.
8. As a user, I want the number of generated cards to reflect the content of my notes, so that short notes don't produce padded, low-value cards.
9. As a user, I want generated cards to be well-formed question/answer pairs, so that they're immediately usable for review.
10. As a user, I want generated cards auto-saved once generation succeeds, so that my button click is the only approval step I need — I correct mistakes afterward via edit/delete (ticket 07), not through a separate review gate.
11. As a user, I want each generated card to start with sane default scheduling (never reviewed, due today), so that it enters the normal review flow immediately.
12. As a user, I want my API key kept in configuration, not in code, so that the integration stays secure and swappable.
13. As the developer, I want the LLM call behind an injectable, always-mocked client boundary, so that tests never make real network calls and later tickets (11, 12) can reuse the same seam.
14. As the developer, I want malformed LLM output treated as a hard failure with zero partial writes, so that a bad generation never leaves half-written or garbage cards in the database.

## Implementation Decisions

- **Trigger and status lifecycle:** a source starts at `status=stored` after upload (ticket 05) —
  generation never runs automatically. `POST /sources/{id}/convert` transitions it to `processing`
  (replacing any existing cards first if this is a re-trigger — see below), schedules a
  `BackgroundTasks` job, and returns an HTMX fragment for the processing popup. The background job
  opens its own SQLAlchemy session (the request's session may already be closed by the time the
  task runs) and, on completion, sets `status=done` (cards saved) or `status=failed` +
  `error_message` (nothing saved).
- **Re-trigger scope:** clicking "Convert to Flashcards" on a `done` or `failed` source is allowed
  and **replaces** — all existing `cards` rows for that source (and their cascaded `reviews`) are
  deleted before the new generation runs. This is the simplest correct behavior and doubles as the
  retry mechanism for a `failed` source.
- **LLM client boundary:** a `FlashcardGenerator` protocol with `generate(text: str) -> list[GeneratedCard]`.
  The real implementation calls the Anthropic SDK's **sync** client with `model="claude-sonnet-5"`,
  forced tool use (`tool_choice` pinned to a single `emit_flashcards` tool whose `input_schema`
  requires a `cards: [{question, answer}]` array, capped at 100 entries), `max_tokens=4096`, and
  default temperature. `ANTHROPIC_API_KEY` is read from the existing `memory_ai/config.py` setting.
- **Prompt:** a system prompt instructs the model to produce clear, atomic question/answer pairs
  covering the key facts/concepts in the text, without padding with trivial or duplicate cards; the
  user turn is the (possibly chunked) `raw_text` verbatim. Long text is split via ticket 05's
  chunking helper; each chunk gets an independent LLM call and the resulting card lists are
  concatenated (no cross-chunk deduplication in v1).
- **Validation and failure handling:** the tool call's `input` is validated against the card schema
  (non-empty array; both `question` and `answer` present and non-blank) in one all-or-nothing step.
  Any validation failure, or an Anthropic API error/timeout, results in `status=failed` with a
  generic `error_message` and zero `cards` rows written — there is no automatic retry; re-clicking
  the button is the retry path.
- **Persistence mapping:** validated `{question, answer}` pairs map to `cards.front`/`cards.back`.
  Each new card gets `ease_factor=2.5`, `interval_days=0`, `repetitions=0`, `due_date=today`
  (server UTC date at insert time), and FKs to its `source_id` and (denormalized) `folder_id`.
- **Status endpoint and polling:** `GET /sources/{id}/status` returns an HTMX fragment. While
  `processing`, the fragment re-includes `hx-trigger="every 2s"` so the popup keeps polling; on
  `done` it swaps in the rendered card list with no further trigger; on `failed` it swaps in the
  error message plus a "Retry" affordance (the same convert button) with no further trigger.
- **UI placement:** the "Convert to Flashcards" button lives on each source's row/card inside the
  main content editor (the folder/note detail view) — not in the subjects/folders/notes sidebar or
  dropdown nav.
- **`sources.status` values:** extended to four: `stored | processing | done | failed`. This is an
  app-code `Literal`/validation change, not a schema migration (ticket 02 already stores `status`
  as a plain validated string column).

## Testing Decisions

- **What makes a good test:** asserts externally observable behavior — HTTP status/response shape,
  `sources.status`/`error_message` transitions, and persisted `cards` rows — never real network
  calls to Anthropic and never internal LLM-SDK/prompt-string implementation details.
- **LLM boundary seam (primary, per the master PRD):** the `FlashcardGenerator` is injected and
  always mocked in tests, returning canned structured output, including a dedicated
  malformed-output case (missing field, empty array, over-length array) to exercise the failure
  path without needing a real invalid API response.
- **HTTP seam:** ticket 02's `TestClient` + real test Postgres, transaction-rolled-back per test.
  Covers: upload → source has no cards, `status=stored` → click convert → `status=processing` →
  poll status → `status=done` with cards present; the failure path (mocked generator raises /
  returns malformed output) → `status=failed`, `error_message` set, no cards written; re-trigger on
  an already-`done` source → old cards deleted, new cards saved, no duplication.
- **Modules tested:** the convert-trigger route, the background generation job (called directly/
  synchronously in tests rather than relying on `BackgroundTasks`' real async scheduling), the
  status-poll route, and the `FlashcardGenerator` real-implementation's request/response shaping
  (schema construction, response parsing) tested against a stubbed Anthropic client rather than the
  network.
- **Prior art:** ticket 02's test harness (testcontainer Postgres, rollback-per-test fixture,
  `TestClient` fixture); this is the first ticket to introduce a mocked-external-service seam
  alongside it.

## Out of Scope

- Automatic generation on upload (superseded by this ticket's manual-trigger redesign — see
  decisions.md's header note).
- A separate approval/review gate before cards are saved — the button click is the approval gate;
  correction happens post-hoc via ticket 07's edit/delete.
- Automatic retry of a failed LLM call — the user re-clicking the button is the retry mechanism.
- Cross-chunk deduplication of cards generated from a long, chunked source.
- Preserving review history across a replace-triggered re-generation (deleted cards cascade-delete
  their `reviews`; this is an accepted v1 limitation).
- Any card-count target/minimum — the model decides count from content, bounded only by the
  100-card guardrail in decisions.md #6.

## Further Notes

- This ticket establishes the **LLM boundary seam** ("the flashcard-generation client is injected
  and always mocked") called out in the master PRD's Testing Decisions — tickets 11
  (written-answer-feedback) and 12 (notes-quiz) reuse this same seam rather than inventing their
  own.
- Blocked by ticket 05 (upload-and-parse): this ticket needs the `sources` row, its `raw_text`, and
  the chunking helper that ticket 05 provides. Ticket 05 was still being planned in parallel as of
  this PRD's writing; see this ticket's `issues/README.md` for how that dependency is tracked.
- No new config surface: `ANTHROPIC_API_KEY` already exists in `memory_ai/config.py` (ticket 01).
