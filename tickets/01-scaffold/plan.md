# 01 — Project Scaffold

**Depends on:** nothing. **Goal:** a foundation with no app logic — every later ticket builds on this.

> Decisions locked via `/grill-me` on 2026-07-17 — see [decisions.md](decisions.md).

## Build

### Layout & runtime
- Remove the empty `Memory_AI/` directory.
- Python **`src/` layout**, package **`memory_ai`** (importable as `import memory_ai`).
- Python **3.12**: `requires-python = ">=3.12,<3.13"` in `pyproject.toml` + a fresh `.python-version`;
  interpreter managed by **uv**.
- Minimal FastAPI app `app` in `memory_ai/main.py` with a `/health` endpoint returning 200.
- `memory_ai/config.py` using **pydantic-settings** to load env (no secrets committed).

### Dependencies (declared; mostly unwired at this ticket)
- **Runtime:** fastapi, uvicorn, sqlalchemy (2.0), alembic, psycopg, jinja2, python-multipart,
  passlib[bcrypt], pydantic-settings, anthropic, pypdf.
- **Dev:** pytest, pytest-cov, ruff, mypy, pre-commit, testcontainers.
- Managed by **uv** with a committed lockfile and a runtime/dev dependency-group split.

### Quality gates
- **mypy**: `strict = true`.
- **Ruff**: rule set `E, F, I, B, UP, SIM, C4`; Ruff formatter; **line length 100**.
- **pytest**: configured with `--cov=memory_ai --cov-fail-under=80` (trivially green on `/health`;
  the 80 threshold stays as real code lands).
- **pre-commit**: hooks running ruff (lint + format) and mypy.

### Local dev — Docker Compose (dev-only)
- `app` service: `uvicorn memory_ai.main:app --reload`, source mounted for live reload.
- `db` service: `postgres:16` with a healthcheck and a named volume for data.
- `app` `depends_on` `db` being healthy.
- No production/hardened image at this ticket.

### Config
- **`.env.example`** committed with all keys: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `JWT_SECRET`, plus
  app settings. Real `.env` stays gitignored; nothing secret committed.

### CI — GitHub Actions
- Triggers: `push` to `main` + all `pull_request`s.
- Single job, Python 3.12, with a **`postgres:16` service container** (establishes the pattern ticket 02
  needs) — but **no Alembic/migration step yet** (nothing to migrate).
- Steps, fail-fast in order: checkout → `astral-sh/setup-uv` (cached) → `uv sync` → `ruff check` →
  `ruff format --check` → `mypy` → `pytest`.

## Definition of done
- `docker compose up` brings up app + Postgres; `/health` returns 200.
- `ruff`, `ruff format --check`, `mypy`, and `pytest` all pass locally and in CI.
- No business logic yet.

## Test seam
- One smoke test hitting `/health` via the FastAPI test client — establishes the HTTP seam pattern that
  later tickets reuse.
