# 02 — Database Foundation

**Depends on:** 01. **Goal:** ORM, migrations, all base models, and the reusable test DB harness.

## Build
- SQLAlchemy 2.0 engine/session setup; a `get_db` dependency for FastAPI.
- **Alembic** configured against the models; initial migration creating all tables.
- **All base models** per the locked schema:
  - `users` (id, email unique, password_hash, created_at)
  - `user_settings` (user_id FK unique, daily_review_cap, timezone, timestamps)
  - `subjects` (id, user_id FK, name, created_at)
  - `folders` (id, subject_id FK, name, created_at)
  - `sources` (id, folder_id FK, filename, file_type, raw_text TEXT, status, error_message, created_at)
  - `cards` (id, source_id FK, folder_id FK, front, back, ease_factor=2.5, interval_days=0,
    repetitions=0, due_date, last_reviewed_at, created_at)
  - `reviews` (id, card_id FK, grade, reviewed_at, prev_interval_days, new_interval_days)
- Cascade deletes down the hierarchy (subject→folder→source→card; card→reviews).
- **Test harness** (the reusable prior art for all later tickets): test Postgres via testcontainers,
  a transaction-rollback fixture, and a FastAPI test-client fixture wired to the test DB.

## Definition of done
- `alembic upgrade head` builds the full schema; `downgrade` reverses it.
- The test harness fixtures are importable and used by a trivial model round-trip test.

## Test seam
- Establishes the integration seam (real Postgres + rollback) that tickets 03–10 reuse.
