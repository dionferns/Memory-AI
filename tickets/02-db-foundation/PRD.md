# PRD: Ticket 02 — Database Foundation

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

As the developer, I have a running FastAPI scaffold but no database layer at all: no ORM models, no
migrations, and no way to run tests against a real database. Every later ticket (auth, hierarchy,
uploads, flashcards, review) needs a persistent schema and a reliable way to exercise it in tests
before any of that feature work can begin.

## Solution

The full v1 data model — `users`, `user_settings`, `subjects`, `folders`, `sources`, `cards`,
`reviews` — expressed as typed SQLAlchemy 2.0 models, with an Alembic migration that builds the
schema from nothing and a reusable test harness (real Postgres via testcontainers, transaction
rollback per test) that every later ticket's tests build on. After this ticket, `alembic upgrade
head` produces the complete schema, `docker compose up` migrates automatically, CI migrates its
Postgres service before running tests, and a trivial round-trip test proves the harness works.

## User Stories

1. As the developer, I want all seven base tables modeled in SQLAlchemy, so that every later ticket has the schema it needs.
2. As the developer, I want models declared in SQLAlchemy 2.0's typed style (`Mapped[]`/`mapped_column()`), so that mypy strict passes without stub gymnastics.
3. As the developer, I want a single `get_db` FastAPI dependency, so that every future route gets a consistent, request-scoped session.
4. As the developer, I want Alembic configured against the models with an initial migration, so that the schema is versioned and reproducible.
5. As the developer, I want Alembic to read `DATABASE_URL` from the same config module the app uses, so that dev/test/CI never resolve a different database by accident.
6. As the developer, I want auto-increment integer primary keys, so that the schema stays simple at v1 scale.
7. As the developer, I want cascade deletes enforced at the database level (`ON DELETE CASCADE`), so that a subject/folder delete correctly removes its folders/sources/cards/reviews even outside the ORM.
8. As the developer, I want `sources.status` and `reviews.grade` stored as plain validated strings, so that adding a new value later is a code change, not a migration.
9. As the developer, I want all timestamp columns timezone-aware and stored in UTC, so that per-user-timezone "due today" logic (ticket 09) has a correct foundation.
10. As the developer, I want `cards.due_date` stored as a bare `DATE`, so that "due today" stays a day-boundary concept without instant-vs-day ambiguity.
11. As the developer, I want indexes on `cards.due_date` and `cards.folder_id`, so that ticket 09's review queries are fast from the start.
12. As the developer, I want a session-scoped Postgres testcontainer for the test suite, so that tests don't pay container-startup cost per test.
13. As the developer, I want each test wrapped in a transaction + `SAVEPOINT` that rolls back, so that tests never leak state into each other without a full schema reset.
14. As the developer, I want the test harness to run real `alembic upgrade head` against the testcontainer, so that migration bugs are caught by the same tests that exercise the schema.
15. As the developer, I want a FastAPI test-client fixture wired to the test database, so that later tickets have a ready-made HTTP test seam.
16. As the developer, I want CI to run `alembic upgrade head` against its Postgres service before `pytest`, so that CI's database path matches the test harness's.
17. As the developer, I want the Compose `app` service to run migrations automatically before starting uvicorn, so that `docker compose up` always yields a working, migrated dev database.
18. As the developer, I want a trivial model round-trip test, so that the harness itself is proven to work before other tickets depend on it.

## Implementation Decisions

- **Models:** all seven tables in a single `memory_ai/models.py`, SQLAlchemy 2.0 typed declarative
  style (`DeclarativeBase`, `Mapped[]`, `mapped_column()`). Auto-increment integer primary keys.
  - `users`: id, email (unique), password_hash, created_at.
  - `user_settings`: id, user_id (FK, unique, not null), daily_review_cap, timezone, created_at, updated_at.
  - `subjects`: id, user_id (FK), name, created_at. No uniqueness constraint on name.
  - `folders`: id, subject_id (FK), name, created_at. No uniqueness constraint on name.
  - `sources`: id, folder_id (FK), filename, file_type, raw_text (TEXT), status (str), error_message (nullable), created_at.
  - `cards`: id, source_id (FK), folder_id (FK, denormalized), front, back, ease_factor (default 2.5), interval_days (default 0), repetitions (default 0), due_date (DATE, indexed), last_reviewed_at (nullable), created_at. Indexed also on folder_id.
  - `reviews`: id, card_id (FK), grade (str), reviewed_at, prev_interval_days, new_interval_days.
- **Timestamps:** all `created_at`/`updated_at`/`reviewed_at`/`last_reviewed_at` columns are
  `TIMESTAMPTZ`, values stored in UTC. `cards.due_date` is the one exception: a bare `DATE`.
- **Cascades:** FK constraints carry `ondelete="CASCADE"` at the DB level for the full
  subject→folder→source→card and card→reviews chains.
- **Status/grade fields:** plain string columns (no Postgres `ENUM` type); validity is enforced in
  application code via Python `Enum`/`Literal` + Pydantic, not a DB constraint.
- **Engine/session:** sync SQLAlchemy engine (matches the already-pinned `psycopg[binary]` driver);
  a `get_db` generator dependency yields a session per request and closes it in a `finally`.
- **Alembic:** `env.py` imports `memory_ai.config.get_settings()` for `DATABASE_URL` rather than
  reading `os.environ` directly. One initial migration creates the full schema.
- **`user_settings` creation:** not a DB trigger — ticket 03's registration endpoint inserts the
  `users` row and a default `user_settings` row in the same DB transaction.
- **Test harness:** a session-scoped Postgres testcontainer is started once per pytest run and
  migrated via `alembic upgrade head`; each test runs inside an outer transaction with a
  `SAVEPOINT` that's rolled back at teardown; a FastAPI `TestClient` fixture overrides `get_db` to
  use the same transactional session.
- **CI:** the existing `postgres:16` service container gets a new `alembic upgrade head` step
  inserted between `uv sync` and `pytest`.
- **Docker Compose:** the `app` service's entrypoint runs `alembic upgrade head` before launching
  `uvicorn --reload`.

## Testing Decisions

- **What makes a good test:** asserts externally observable state (rows exist, correct FK/cascade
  behavior, migration up/down works) — not SQLAlchemy internals. This ticket has no HTTP endpoints
  of its own, so there is no HTTP-seam test here; the "test" is the harness itself proving it works.
- **Seam:** a new **DB integration seam** (real Postgres via testcontainers + transaction rollback)
  — this is the highest seam available since there's no HTTP layer yet, and it becomes the seam
  every later ticket's HTTP tests are built on top of.
- **Module tested:** `models.py` (round-trip create/cascade-delete), the Alembic migration
  (`upgrade`/`downgrade`), and the harness fixtures themselves (session-scoped container,
  rollback-per-test, test-client override).
- **Prior art:** none yet — this ticket **is** the prior art tickets 03–10 reuse, per the master
  PRD's Testing Decisions section.

## Out of Scope

- Any HTTP routes/endpoints (auth, hierarchy, upload, cards, review — all later tickets).
- Populating real data through the app (registration, uploads, etc. — ticket 03 onward).
- The migration-drift CI check (`alembic check`-style autogenerate diff) — deferred until multiple
  migrations exist.
- DB-level uniqueness constraints on `subjects.name` / `folders.name`.
- Postgres native `ENUM` types for `status`/`grade`.

## Further Notes

- This is the first ticket to introduce real Alembic migrations; ticket 01's CI intentionally
  deferred the migration step until this ticket needed it (ticket 01 decision #5).
- Ticket 02 modifies files ticket 01 created (`.github/workflows/ci.yml`, `docker-compose.yml`,
  `Dockerfile`) to add the migration steps — this is expected, not scope creep.
