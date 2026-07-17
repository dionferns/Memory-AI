# Tickets

Component tickets for Memory-AI v1, numbered by build order. Each folder holds a `plan.md`
describing what to build for that component. Per-ticket workflow: run `/grill-me` on the
folder's `plan.md`, then `/to-prd`, then `/to-issues` (which creates GitHub issues and writes
the created issue links back into the folder as `issues.md`).

See the master [PRD.md](../PRD.md) for the full v1 spec and the design record.

## Build order

| # | Ticket | Depends on | Summary |
|---|--------|-----------|---------|
| 01 | [scaffold](01-scaffold/plan.md) | — | Repo layout, uv, ruff/mypy/pytest, pre-commit, Docker Compose, CI skeleton |
| 02 | [db-foundation](02-db-foundation/plan.md) | 01 | SQLAlchemy + Alembic, base models, test DB harness |
| 03 | [auth](03-auth/plan.md) | 02 | Register/login/logout, JWT-cookie, bcrypt, auth dependency |
| 04 | [hierarchy](04-hierarchy/plan.md) | 03 | Subjects + folders CRUD, user-scoped |
| 05 | [upload-and-parse](05-upload-and-parse/plan.md) | 04 | File upload, PDF/MD/TXT extraction, Source records, per-folder filename uniqueness |
| 06 | [ai-flashcards](06-ai-flashcards/plan.md) | 05 | User-triggered ("Convert to Flashcards") Claude integration, structured JSON, BackgroundTasks, polling popup |
| 07 | [card-crud](07-card-crud/plan.md) | 06 | View/edit/delete cards |
| 08 | [sr-algorithm](08-sr-algorithm/plan.md) | 02 | SM-2 pure module + exhaustive unit tests, reviews log |
| 09 | [review-flows](09-review-flows/plan.md) | 07, 08 | Global (capped) + per-subject (uncapped) review, 4-button grading, tz-aware today |
| 10 | [settings](10-settings/plan.md) | 09 | Daily cap, timezone, settings UI |
| 11 | [written-answer-feedback](11-written-answer-feedback/plan.md) | 09 | Free-text review answers, LLM-graded outcome drives SM-2 grading |
| 12 | [notes-quiz](12-notes-quiz/plan.md) | 05 | "Quiz Me" — one-shot LLM Q&A batch over a note, browsed one question at a time |

Ordering: 01→02→03 are horizontal foundations. 05→06→07 form the ingestion pipeline.
08→09→10 form the review pipeline (08 depends only on 02, so it can be built in parallel
with the ingestion pipeline, but 09 needs both 07 and 08). 11 depends on 09 (extends the review
UI/grading path) and reuses the LLM client boundary established in 06, so it can start once both
have landed. 12 depends only on 05 (it needs stored note text, not flashcards) and reuses the LLM
client boundary from 06, so it can be built any time after 05 lands, in parallel with 06 onward.
