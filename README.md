# Memory AI

Turn study notes into spaced-repetition flashcards. Upload a PDF, Markdown, or TXT file into a
folder, and an LLM (Claude) generates flashcards from the extracted text. Review due cards either
globally (capped, across all subjects) or per-subject (uncapped) on an SM-2 schedule — both views
read and write the same card state, so they never drift out of sync.

See [PRD.md](PRD.md) for the full product spec and design record.

## Features

- **Accounts** — email/password registration and login, JWT-in-httpOnly-cookie sessions.
- **Subjects → Folders** hierarchy, scoped per user, with cascade delete.
- **Upload & parse** — PDF/Markdown/TXT extraction, per-folder filename uniqueness.
- **AI flashcard generation** — user-triggered "Convert to Flashcards", background job with
  processing/status polling, retry on failure.
- **Card CRUD** — view, inline-edit, inline-delete (with confirmation), scoped to the owning
  folder/subject.
- **Spaced repetition** — pure SM-2 module driving due dates; global daily-capped review and
  per-subject uncapped review share one due-cards query.
- **Written-answer grading** — optional free-text review mode, graded by an LLM outcome
  classification mapped onto the same SM-2 grade scale.
- **Quiz Me** — one-shot LLM-generated Q&A batch over a single note, browsed client-side.
- **Settings** — per-user daily review cap and timezone (drives the tz-aware "due today"
  boundary), validated with no partial apply.

## Tech stack

- **Backend**: FastAPI, SQLAlchemy 2.0 (typed), Alembic migrations, Postgres 16
- **Frontend**: server-rendered Jinja2 templates + HTMX (no SPA build step), one global CSS
  stylesheet
- **LLM**: Anthropic Claude, via an injectable client boundary (mockable in tests)
- **Package/tooling**: `uv`, `ruff` (lint + format), `mypy` (strict), `pytest` +
  `testcontainers` (real Postgres in tests, transaction-rolled-back per test)

## Running it

### Docker Compose (fastest path)

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum
docker compose up
```

The app is served at `http://localhost:8000`; migrations run automatically on container start.

### Locally with uv

```bash
uv sync
cp .env.example .env   # point DATABASE_URL at a local Postgres, fill in ANTHROPIC_API_KEY
uv run alembic upgrade head
uv run uvicorn memory_ai.main:app --reload
```

## Development

```bash
uv run ruff check .          # lint
uv run ruff format --check . # format check
uv run mypy .                # strict type check
uv run pytest                # tests (spins up a real Postgres via testcontainers)
```

All four gates run in CI (`.github/workflows`) on every push/PR to `main`.

## Project structure

```
src/memory_ai/       Application code (routes, models, scheduling, LLM boundary, templates, static)
alembic/versions/     Database migrations
tests/                pytest suite (HTTP-seam + DB-harness tests)
tickets/              Per-feature planning docs (PRD/decisions/GitHub issues) and build order
```

`tickets/README.md` documents the build order and each ticket's scope. `tickets/SUPERVISOR-GUIDE.md`
records the multi-agent orchestration method used to implement this project's tickets.
