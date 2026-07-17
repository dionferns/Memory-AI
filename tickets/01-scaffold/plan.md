# 01 — Project Scaffold

**Depends on:** nothing. **Goal:** a foundation with no app logic — every later ticket builds on this.

## Build
- Remove the empty `Memory_AI/` directory. Establish a Python `src/` layout package for the app.
- **uv** dependency management: `pyproject.toml` with dependency groups (runtime + dev), lockfile.
- Core runtime deps declared (not yet wired): FastAPI, uvicorn, SQLAlchemy 2.0, Alembic, psycopg,
  Jinja2, python-multipart, passlib[bcrypt], pydantic-settings, anthropic, pypdf.
- Dev deps: pytest, pytest-cov, ruff, mypy, pre-commit, testcontainers.
- **Ruff** config (lint + format), **mypy** config (strict-ish), **pytest** config with coverage gate (~80%).
- **pre-commit** hooks running ruff + mypy.
- **Docker Compose** for local dev: app service + Postgres service, healthchecks, volume for pg data.
- **`.env.example`** with all keys: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `JWT_SECRET`, plus app settings.
- **pydantic-settings** config module that loads env (no secrets committed).
- A minimal FastAPI app with a `/health` endpoint returning 200, so CI has something to run.
- **GitHub Actions** CI skeleton: Postgres service → uv install → ruff → mypy → pytest+coverage.

## Definition of done
- `docker compose up` brings up app + Postgres; `/health` returns 200.
- `ruff`, `mypy`, `pytest` all pass locally and in CI.
- No business logic yet.

## Test seam
- One smoke test hitting `/health` via the FastAPI test client (establishes the HTTP seam pattern).
