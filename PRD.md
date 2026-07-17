# PRD: Memory-AI — v1

> Master PRD for Memory-AI v1. Per-ticket detail is elaborated later in `tickets/NN-name/plan.md`
> via the per-ticket `/grill-me` → `/to-prd` → `/to-issues` cycle. GitHub issues are created at
> the `/to-issues` stage (deferred until the `gh` CLI is installed and authenticated).

## Problem Statement

A learner accumulates study notes in many formats (PDF, Markdown, plain text) across many subjects.
Turning those notes into effective spaced-repetition flashcards by hand is slow and tedious, and once
cards exist, keeping a consistent daily review habit across *all* subjects — while still being able to
drill a single subject — is hard to manage. The learner wants a single place to dump notes, get
flashcards generated automatically, and be handed the right cards to review each day, with review
progress that stays consistent no matter which view they study from.

## Solution

A web application where each user has an account and can:

- Organize study material into a fixed two-level hierarchy: **Subjects → Folders**.
- Upload note files (PDF / Markdown / TXT) into a folder. On upload, a "processing" popup appears while
  an LLM generates flashcards from the extracted text; the popup clears when generation completes.
- Review the generated flashcards, editing or deleting any that are wrong.
- Do a **global daily review** that pulls a capped number of due cards from across all subjects using an
  **SM-2** spaced-repetition schedule, with the daily cap configurable in settings.
- Alternatively drill a **single subject**, reviewing all of that subject's due cards (uncapped).
- Trust that both review paths operate on the same card schedule — reviewing a card anywhere updates its
  single due date, so the two views never drift out of sync.

## User Stories

### Accounts & Auth
1. As a new user, I want to register with an email and password, so that I have a private account for my study material.
2. As a returning user, I want to log in, so that I can access my subjects, folders, and cards.
3. As a logged-in user, I want to log out, so that my session ends on a shared machine.
4. As a user, I want my password stored securely (hashed), so that a database breach does not expose my credentials.
5. As a user, I want my session carried in a secure httpOnly cookie, so that my auth token cannot be stolen by page scripts.
6. As a user, I want to only ever see my own subjects, folders, sources, and cards, so that my data is private to me.

### Subjects & Folders
7. As a user, I want to create a subject, so that I can group related material (e.g. "System Design").
8. As a user, I want to rename or delete a subject, so that I can keep my workspace tidy.
9. As a user, I want to create a folder inside a subject, so that I can divide material further (e.g. "Caching").
10. As a user, I want to rename or delete a folder, so that I can reorganize as my notes grow.
11. As a user, I want deleting a subject or folder to remove its contained sources and cards, so that I do not leave orphaned data.
12. As a user, I want to see a list of my subjects and, within each, its folders, so that I can navigate my material.

### Uploading & Parsing
13. As a user, I want to upload a PDF, Markdown, or TXT file into a folder, so that I can turn my notes into cards.
14. As a user, I want a clear error if I upload an unsupported file type, so that I know what is accepted.
15. As a user, I want a clear message if a PDF has no extractable text (e.g. a scan), so that I understand why no cards were made.
16. As a user, I want oversized files rejected with a clear limit message, so that I do not wait on a file that will not process.
17. As a user, I want the raw extracted text of my upload stored, so that cards remain traceable to their source.

### AI Flashcard Generation
18. As a user, I want a "processing / creating flashcards" popup to appear immediately after upload, so that I know work is happening.
19. As a user, I want the upload request to return quickly rather than hang, so that the UI stays responsive during a long LLM call.
20. As a user, I want the popup to clear automatically once cards are ready, so that I do not have to refresh manually.
21. As a user, I want to be told if flashcard generation failed, so that I can retry rather than wonder.
22. As a user, I want the number of generated cards to reflect the content of my notes, so that short notes do not produce padded cards.
23. As a user, I want generated cards to be well-formed question/answer pairs, so that they are usable for review.
24. As a user, I want my API key kept in configuration (not in code), so that the integration is secure and swappable.

### Card Management
25. As a user, I want to view all cards generated from a source, so that I can check their quality.
26. As a user, I want to edit a card's front or back, so that I can fix an inaccurate AI-generated card.
27. As a user, I want to delete a card, so that I can remove cards that are wrong or redundant.

### Daily Review (global)
28. As a user, I want a daily review that gives me cards due today from across all my subjects, so that I keep a single study habit.
29. As a user, I want the daily review limited to my configured cap, so that I am not overwhelmed on heavy days.
30. As a user, I want the most-overdue cards prioritized within the cap, so that I address my biggest gaps first.
31. As a user, I want to grade each card Again / Hard / Good / Easy, so that the schedule adapts to how well I know it.
32. As a user, I want overflow due cards (beyond the cap) to remain due, so that nothing is silently dropped.

### Subject Review (drill)
33. As a user, I want to review all due cards within a single subject, ignoring the global cap, so that I can cram before an exam.
34. As a user, I want grading a card in subject review to update the same schedule as the global review, so that the two never diverge.

### Scheduling behavior
35. As a user, I want "due today" computed against my own timezone's midnight, so that my day boundary is correct.
36. As a user, I want a card I grade Again to come back soon, and a card I grade Easy to be pushed far out, so that review effort matches difficulty.
37. As a user, I want my review history recorded, so that the schedule is auditable and future stats are possible.

### Settings
38. As a user, I want to set my daily review cap, so that I control my workload.
39. As a user, I want to set my timezone, so that daily boundaries match where I live.
40. As a user, I want my settings to persist and apply immediately to the next review, so that changes take effect predictably.

## Implementation Decisions

### Architecture
- **Backend:** FastAPI, SQLAlchemy 2.0 ORM, Alembic migrations, PostgreSQL.
- **Frontend:** server-rendered HTML with Jinja2 templates + HTMX for interactivity (polling, partial updates). No SPA.
- **Repo:** single monorepo, Python `src/` layout. The empty `Memory_AI/` directory is removed.
- **Config:** all secrets/credentials via environment (`.env`, with a committed `.env.example`): database URL, `ANTHROPIC_API_KEY`, JWT signing secret.

### Auth
- JWT issued on login, carried in an **httpOnly, Secure, SameSite** cookie (not localStorage).
- Passwords hashed with **bcrypt** (via passlib).
- A route dependency enforces authentication and scopes every query to the current user.
- v1 includes register / login / logout only. No email verification, no password reset.

### Data model (schema)
- **users**: id, email (unique), password_hash, created_at.
- **user_settings**: user_id (FK, unique), daily_review_cap (int), timezone (str), created_at/updated_at.
- **subjects**: id, user_id (FK), name, created_at.
- **folders**: id, subject_id (FK), name, created_at.
- **sources**: id, folder_id (FK), filename, file_type, raw_text (TEXT), status (processing | done | failed),
  error_message (nullable), created_at. Stores extracted text only — the original binary is not persisted.
- **cards**: id, source_id (FK), folder_id (FK, denormalized for fast subject/folder queries), front, back,
  ease_factor (default 2.5), interval_days (default 0), repetitions (default 0), due_date, last_reviewed_at
  (nullable), created_at.
- **reviews** (audit log): id, card_id (FK), grade, reviewed_at, prev_interval_days, new_interval_days.
- Hierarchy is fixed at two levels (Subject → Folder); folders do not nest. Deletes cascade downward.
- A single `due_date` per card is the sole source of truth; global and subject review are different queries
  over the same rows, so their schedules cannot drift.

### AI flashcard pipeline
- Upload path: parse file → create a `sources` row with status=`processing` → schedule a **FastAPI
  BackgroundTasks** job → return immediately with a fragment showing the processing popup.
- The popup uses **HTMX polling** against a status endpoint; when status is `done` it swaps in the results,
  when `failed` it shows an error with retry.
- LLM provider: **Anthropic Claude (`claude-sonnet-5`)** via the official SDK, using **structured/tool-based
  JSON output** that returns a strict `[{question, answer}]` array, validated by Pydantic. Malformed output
  is treated as a generation failure.
- The LLM call sits behind an injectable client boundary so it can be mocked in tests.
- Cards are auto-saved on success (no approval gate); correction happens via post-hoc edit/delete.

### File parsing
- **pypdf** extracts text from text-based PDFs; Markdown and TXT are read directly.
- OCR / scanned PDFs / embedded images are out of scope. PDFs with no extractable text fail with a clear message.
- A file-size cap is enforced; note text exceeding the model context is chunked.

### Spaced repetition
- **SM-2**, implemented as a pure module: `(card scheduling state, grade) → (new interval, ease, repetitions, due_date)`.
- Four grade buttons (Again / Hard / Good / Easy) map to SM-2 quality values.
- "Due today" is evaluated against the user's timezone midnight (default UTC when unset).
- Global daily review returns `min(cap, due-count)` cards ordered most-overdue-first; per-subject review returns
  all due cards for that subject (uncapped). Overflow cards simply remain due on subsequent days.
- Every grading writes a `reviews` row.

### Tooling / infra
- **uv** for dependency management (lockfile, dev/prod split).
- **Ruff** (lint + format), **mypy** (types), **pytest** + **pytest-cov** with a coverage gate (~80%).
- **pre-commit** runs ruff/mypy locally.
- **Docker Compose** runs app + Postgres locally, mirrored by a **GitHub Actions** CI pipeline
  (Postgres service → install → ruff → mypy → pytest+coverage). Branch protection on `main`.
- One git worktree + `feat/NN-name` branch per ticket → PR → green CI → merge to `main`.

## Testing Decisions

**What makes a good test here:** it asserts externally-observable behavior (HTTP responses, persisted
state, scheduling outputs), not internal implementation details. Tests should survive refactors that
preserve behavior. The LLM and the clock/timezone are the volatile boundaries and are controlled, never
called for real in CI.

**Seams (highest-possible; prefer existing over new):**
1. **HTTP seam (primary):** FastAPI test client + real test Postgres. Covers auth, subject/folder CRUD,
   upload, card CRUD, and both review flows end-to-end. Each test runs in a rolled-back transaction.
2. **LLM boundary seam:** the flashcard-generation client is injected and always mocked, returning canned
   structured JSON (including a malformed-output case to exercise the failure path).
3. **SM-2 pure-function seam:** exhaustive unit tests over `(state, grade) → new state`, including
   Again/Hard/Good/Easy transitions, first-review behavior, and due-date math.
4. **File-parser pure seam:** `(bytes, type) → text` unit tests with small fixtures (a text PDF, an MD,
   a TXT) plus the no-extractable-text failure case.

**Modules tested:** auth, subject/folder services, upload+parse, AI-generation orchestration (with mocked
LLM), card CRUD, the SM-2 scheduler, and the review query/cap/ordering logic. Integration behavior is
tested at the HTTP seam; correctness-critical pure logic (SM-2, parsing) at the unit seam.

**Prior art:** none yet (greenfield). The `02-db-foundation` ticket establishes the reusable test harness
(test Postgres via testcontainers, transaction rollback fixture, client fixture) that later tickets reuse;
subsequent tickets follow that harness as the prior art.

## Out of Scope (v1)

- OCR / scanned PDFs / images inside PDFs; non-PDF/MD/TXT formats.
- Email verification, password reset, OAuth/social login, multi-factor auth.
- FSRS scheduling (SM-2 only for v1); "new cards per day" sub-limit separate from the review cap.
- Sharing decks between users, collaboration, public decks.
- Persisting original uploaded binaries (only extracted text is stored).
- Celery/Redis task queue (FastAPI BackgroundTasks for v1); real-time push (polling instead).
- Mobile-native apps; advanced review statistics/dashboards; card tagging/search beyond the hierarchy.
- Approval gate before saving AI cards (cards auto-save; correction is post-hoc).

## Further Notes

- Build order (10 tickets): `01-scaffold` → `02-db-foundation` → `03-auth` → `04-hierarchy` →
  `05-upload-and-parse` → `06-ai-flashcards` → `07-card-crud` → `08-sr-algorithm` → `09-review-flows` →
  `10-settings`. Foundations (scaffold/db/auth) are necessarily horizontal; 05→07 form the ingestion
  pipeline and 08→10 the review pipeline.
- `gh` CLI is not yet installed; it (or a GitHub token) is required before `/to-issues` can create issues.
- Constraint: only this repository and project directory may be modified — never other repos or files
  elsewhere on the machine.
- The design tree behind this PRD was fully resolved via `/grill-me` on 2026-07-17; see the project memory
  entry "Memory-AI Locked Design" for the decision record.
