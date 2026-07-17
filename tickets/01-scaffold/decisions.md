# 01 — Scaffold: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17. These are the source of truth for the
scaffold ticket; the PRD and issues derive from them.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Package name / layout | `src/memory_ai/` (`import memory_ai`) | Clean PEP8 name; distinctive; delete empty `Memory_AI/` |
| 2 | Python version | **3.12** (`>=3.12,<3.13`) | Widest wheel availability for psycopg/pydantic-core/testcontainers; safest CI. Overrides the 3.14 venv |
| 3 | Docker Compose scope | Dev-only: `uvicorn --reload` + `postgres:16` | No prod image needed until deploy |
| 4 | mypy strictness | `strict = true` from day one | Easy to hold from the start, painful to retrofit |
| 5 | CI Postgres at ticket 01 | Include `postgres:16` service, **no** migrations yet | Establishes the ticket-02 pattern without a dead migration step |
| 6 | Ruff rules / line length | `E,F,I,B,UP,SIM,C4`, formatter, **100** cols | Solid, not noisy |
| 7 | Coverage gate | `--cov=memory_ai --cov-fail-under=80` wired now | Gate mechanism exists; trivially green on `/health` |
| 8 | CI triggers | push to `main` + all PRs | Standard |
| 9 | Deps manager | uv, lockfile, runtime/dev group split | Locked in master design |

## Notes
- `.env.example` keys: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `JWT_SECRET` (+ app settings).
- CI step order (fail-fast): `uv sync` → `ruff check` → `ruff format --check` → `mypy` → `pytest`.
- Ticket 02 adds the Alembic `upgrade head` step and the real DB test harness.
