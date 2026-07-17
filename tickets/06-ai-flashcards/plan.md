# 06 — AI Flashcard Generation

**Depends on:** 05. **Goal:** generate flashcards from a source's text via Claude, with a processing popup.

## Build
- On upload completion, create the `processing` source (from 05) and schedule a **FastAPI
  BackgroundTasks** job that: reads `raw_text` → calls the LLM → validates output → writes `cards` →
  sets source `status=done` (or `failed` + `error_message`).
- **LLM client boundary** (injectable/mockable): Anthropic **`claude-sonnet-5`** via official SDK,
  **structured/tool JSON** returning a strict `[{question, answer}]` array validated by Pydantic.
  Malformed output → generation failure. `ANTHROPIC_API_KEY` from env.
- Model decides card count from content (no fixed number).
- Cards **auto-saved** (no approval gate). Each card starts with SM-2 defaults (ease 2.5, interval 0,
  reps 0, due today) and FKs to its source and folder.
- **Processing popup:** upload returns immediately with an HTMX fragment; the popup **polls** a status
  endpoint until `done` (swap in results) or `failed` (show error + retry).

## Definition of done
- Uploading text yields validated cards saved to the DB; the popup clears on completion.
- Failure path surfaces an error and does not leave partial/committed bad cards.

## Test seams
- **LLM boundary (mocked):** canned structured JSON incl. a malformed-output failure case.
- **HTTP seam:** upload → poll status → cards present; failure path.
