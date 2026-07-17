# 02 — Database Foundation

**Depends on:** 01. **Goal:** ORM, migrations, all base models, and the reusable test DB harness.

> Decisions locked via `/grill-me` on 2026-07-17 — see [decisions.md](decisions.md).

## Build
- SQLAlchemy 2.0 **typed** engine/session setup (`DeclarativeBase` + `Mapped[]`/`mapped_column()`,
  sync driver), a `get_db` dependency for FastAPI. Auto-increment integer PKs throughout.
- **Alembic** configured against the models, reading `DATABASE_URL` via `memory_ai.config.get_settings()`;
  initial migration creating all tables in a single `memory_ai/models.py`.
- **All base models** per the locked schema:
  - `users` (id, email unique, password_hash, created_at)
  - `user_settings` (user_id FK unique NOT NULL, daily_review_cap, timezone, timestamps) — row is
    created by app code at registration (ticket 03), not a DB trigger.
  - `subjects` (id, user_id FK, name, created_at) — no uniqueness constraint on name.
  - `folders` (id, subject_id FK, name, created_at) — no uniqueness constraint on name.
  - `sources` (id, folder_id FK, filename, file_type, raw_text TEXT, status: str, error_message, created_at)
  - `cards` (id, source_id FK, folder_id FK, front, back, ease_factor=2.5, interval_days=0,
    repetitions=0, due_date: DATE, last_reviewed_at, created_at) — indexed on `due_date` and `folder_id`.
  - `reviews` (id, card_id FK, grade: str, reviewed_at, prev_interval_days, new_interval_days)
  - `status`/`grade` are plain validated strings, not DB enums. All timestamps `TIMESTAMPTZ` in UTC;
    `due_date` is a bare `DATE` (day-boundary concept, not an instant).
- Cascade deletes down the hierarchy (subject→folder→source→card; card→reviews) via DB-level
  `ON DELETE CASCADE`.
- **Test harness** (the reusable prior art for all later tickets): session-scoped Postgres
  testcontainer, migrated once via real `alembic upgrade head`; a transaction+`SAVEPOINT`
  rollback fixture per test; a FastAPI test-client fixture wired to the test DB.
- **CI:** add an `alembic upgrade head` step (against the existing `postgres:16` service container)
  before `pytest`, now that real migrations exist.
- **Docker Compose:** `app` service entrypoint runs `alembic upgrade head` then starts uvicorn, so
  `docker compose up` always yields a fully migrated dev DB.

## Definition of done
- `alembic upgrade head` builds the full schema; `downgrade` reverses it.
- The test harness fixtures are importable and used by a trivial model round-trip test.
- CI runs migrations against its Postgres service; Compose migrates automatically on `up`.

## Test seam
- Establishes the integration seam (real Postgres + rollback) that tickets 03–10 reuse.
