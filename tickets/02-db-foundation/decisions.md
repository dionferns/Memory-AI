# 02 — DB Foundation: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17. These are the source of truth for the
db-foundation ticket; the PRD's schema section is the higher-level contract this elaborates.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Primary key type | Auto-increment integer | Sufficient for v1's single-user scale; small, simple FKs |
| 2 | ORM declaration style | SQLAlchemy 2.0 typed (`DeclarativeBase` + `Mapped[]`/`mapped_column()`) | Passes mypy strict cleanly, modern idiom |
| 3 | Engine/session mode | Sync | Matches the already-pinned `psycopg[binary]` driver and BackgroundTasks usage in ticket 06 |
| 4 | Model file layout | Single `models.py` | 7 small tables; avoids premature package structure |
| 5 | Cascade deletes | DB-level `ON DELETE CASCADE` on FKs | Correct even for direct DB access, not just ORM-mediated deletes |
| 6 | `sources.status` / `reviews.grade` storage | Plain string columns, validated in app code (Enum/Literal) | Adding a new status/grade later is a code change, not a migration |
| 7 | Timestamp columns | Timezone-aware (`TIMESTAMPTZ`), stored in UTC | Matches the PRD's per-user-timezone "due today" requirement; avoids naive-datetime bugs |
| 8 | `cards.due_date` type | `DATE` (not `TIMESTAMPTZ`) | "Due today" is a day-boundary concept; a DATE avoids instant-vs-day ambiguity |
| 9 | Testcontainer lifecycle | Session-scoped, one Postgres container per pytest run | Container startup is slow; isolation comes from the rollback fixture instead |
| 10 | Per-test isolation | Outer transaction + `SAVEPOINT`, rolled back after each test | Standard SQLAlchemy pattern; fast, no per-test schema reset |
| 11 | Test schema setup | Run real `alembic upgrade head` against the testcontainer | Exercises actual migrations; single source of truth vs. `metadata.create_all()` |
| 12 | Migration-drift CI check | Deferred | Only one migration exists at this ticket; add an autogenerate-diff check once migrations accumulate |
| 13 | Indexes on `cards.due_date`, `cards.folder_id` | Added in the initial migration | Cheap now; ticket 09's review queries need them, avoids a follow-up migration |
| 14 | `user_settings` row creation | App code, at registration (ticket 03) inserts `users` + default `user_settings` in one transaction | Explicit, testable at the HTTP seam; no DB-trigger magic |
| 15 | Alembic `env.py` DB URL source | `memory_ai.config.get_settings()` | Single source of truth for config; dev/test/CI resolve `DATABASE_URL` identically |
| 16 | `subjects.name` / `folders.name` uniqueness | No DB-level uniqueness constraint | Not required by any user story; keep schema minimal |
| 17 | CI migration step | Add `alembic upgrade head` before `pytest` | Keeps CI's service-container Postgres consistent with the test harness's own testcontainer, which already migrates |
| 18 | Docker Compose `app` startup | Entrypoint runs `alembic upgrade head` then `uvicorn` | `docker compose up` always yields a fully migrated, working dev DB |

## Notes
- This is the first ticket to introduce real Alembic migrations; ticket 01's CI intentionally
  deferred the migration step until now (see ticket 01 decision #5).
- `user_settings.user_id` FK stays `NOT NULL UNIQUE`; there is a brief window during ticket 03's
  registration transaction where the `users` row exists before the `user_settings` insert commits,
  but both happen in the same DB transaction so no inconsistent state is ever visible.
