# 06 — AI Flashcard Generation

**Depends on:** 05. **Goal:** on-demand flashcard generation from a source's text via Claude,
triggered explicitly by the user, with a processing popup.

## Build
- Uploading a note (05) only stores it as a `sources` row (`status=stored`, no cards) — generation
  never runs automatically on upload.
- The note view — the **main content editor**, not the subjects/folders/notes sidebar/dropdown nav —
  shows a **"Convert to Flashcards"** button per source. Clicking it is the only way to trigger
  generation.
- On click, transition the source to `processing` and schedule a **FastAPI BackgroundTasks** job
  that: reads `raw_text` → calls the LLM → validates output → writes `cards` → sets source
  `status=done` (or `failed` + `error_message`). Re-clicking on a `done`/`failed` source re-runs
  generation rather than being blocked (decide replace-vs-append-cards scope at build time).
- **LLM client boundary** (injectable/mockable): Anthropic **`claude-sonnet-5`** via official SDK,
  **structured/tool JSON** returning a strict `[{question, answer}]` array validated by Pydantic.
  Malformed output → generation failure. `ANTHROPIC_API_KEY` from env.
- Model decides card count from content (no fixed number).
- Cards **auto-saved** once generation succeeds (no separate approval gate on the generated set —
  the user's button click is the approval gate). Each card starts with SM-2 defaults (ease 2.5,
  interval 0, reps 0, due today) and FKs to its source and folder.
- **Processing popup:** clicking "Convert to Flashcards" returns immediately with an HTMX fragment;
  the popup **polls** a status endpoint until `done` (swap in results) or `failed` (show error +
  retry).

## Definition of done
- A newly uploaded note has no cards and no processing state until the user clicks "Convert to
  Flashcards".
- Clicking the button on a stored source yields validated cards saved to the DB; the popup clears
  on completion.
- Failure path surfaces an error and does not leave partial/committed bad cards.

## Test seams
- **LLM boundary (mocked):** canned structured JSON incl. a malformed-output failure case.
- **HTTP seam:** upload → no cards yet → click convert → poll status → cards present; failure path;
  re-trigger on an already-`done` source.
