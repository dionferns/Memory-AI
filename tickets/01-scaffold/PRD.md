# PRD: Ticket 01 — Project Scaffold

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

As the developer, I have a near-empty repository and no reliable way to build, run, lint, type-check, or
test the application. Before any feature work can begin, I need a trustworthy foundation so that every
later ticket starts from a consistent, reproducible, automatically-verified baseline — and so that broken
code cannot silently reach `main`.

## Solution

A pure-foundation scaffold with no business logic: a `src/`-layout Python package, uv-managed
dependencies pinned to Python 3.12, a minimal FastAPI app exposing `/health`, quality gates (Ruff, mypy,
pytest with a coverage gate, pre-commit), a dev Docker Compose stack (app + Postgres), and a GitHub
Actions pipeline that runs the gates on every push to `main` and every pull request. After this ticket,
`docker compose up` serves `/health`, and lint/type/test all pass locally and in CI.

## User Stories

1. As the developer, I want a `src/`-layout `memory_ai` package, so that imports are clean and the app is packaged properly.
2. As the developer, I want the empty `Memory_AI/` directory removed, so that the repo has no confusing dead folders.
3. As the developer, I want the project pinned to Python 3.12, so that dependency wheels are reliably available in CI and locally.
4. As the developer, I want uv to manage dependencies with a committed lockfile, so that environments are reproducible.
5. As the developer, I want runtime and dev dependencies separated into groups, so that production installs stay lean.
6. As the developer, I want a minimal FastAPI app with a `/health` endpoint, so that CI and Compose have something real to exercise.
7. As the developer, I want configuration loaded from the environment via pydantic-settings, so that secrets never live in code.
8. As the developer, I want a committed `.env.example` listing every required key, so that anyone can configure the app without guessing.
9. As the developer, I want Ruff linting and formatting configured, so that style is consistent and enforced automatically.
10. As the developer, I want mypy in strict mode, so that type errors are caught from day one rather than retrofitted.
11. As the developer, I want pytest configured with a coverage gate, so that the enforcement mechanism exists before real code lands.
12. As the developer, I want pre-commit hooks running Ruff and mypy, so that problems are caught before they are committed.
13. As the developer, I want a dev Docker Compose stack (app + Postgres), so that I can run everything with one command and match CI.
14. As the developer, I want the app container to wait for a healthy Postgres, so that startup ordering is reliable.
15. As the developer, I want a GitHub Actions pipeline running on pushes to `main` and all PRs, so that every change is verified.
16. As the developer, I want CI to run lint, format-check, type-check, and tests fail-fast in order, so that failures are fast and clear.
17. As the developer, I want a Postgres service container present in CI now, so that the pattern is ready for the database ticket.
18. As the developer, I want branch protection on `main` requiring green CI, so that broken code cannot merge.
19. As the developer, I want a `/health` smoke test via the FastAPI test client, so that the reusable HTTP test seam is established.

## Implementation Decisions

- **Package & layout:** `src/` layout, package `memory_ai` (`import memory_ai`); the empty `Memory_AI/`
  directory is deleted. FastAPI `app` lives in the package's `main` module; configuration in a `config`
  module backed by pydantic-settings.
- **Python version:** pinned to **3.12** (`requires-python >=3.12,<3.13`) plus a `.python-version`;
  interpreter managed by uv. This overrides the existing 3.14 venv (chosen for wheel availability).
- **Dependencies (uv, lockfile, runtime/dev split):**
  - Runtime: fastapi, uvicorn, sqlalchemy, alembic, psycopg, jinja2, python-multipart, passlib[bcrypt],
    pydantic-settings, anthropic, pypdf.
  - Dev: pytest, pytest-cov, ruff, mypy, pre-commit, testcontainers.
  - Most runtime deps are declared but unwired at this ticket.
- **Quality gates:** mypy `strict = true`; Ruff rule set `E, F, I, B, UP, SIM, C4` with the Ruff formatter
  and line length 100; pytest configured with `--cov=memory_ai --cov-fail-under=80`; pre-commit runs Ruff
  (lint + format) and mypy.
- **Local dev (dev-only Compose):** `app` runs `uvicorn` with reload and mounted source; `db` runs
  `postgres:16` with a healthcheck and a named volume; `app` depends on `db` being healthy. No production
  image at this ticket.
- **Config contract:** `.env.example` commits keys `DATABASE_URL`, `ANTHROPIC_API_KEY`, `JWT_SECRET`, plus
  app settings; the real `.env` remains gitignored.
- **CI (GitHub Actions):** triggers on push to `main` and all PRs; single job on Python 3.12 with a
  `postgres:16` service container (pattern only — no migration step yet); steps fail-fast in order:
  checkout → setup-uv (cached) → `uv sync` → `ruff check` → `ruff format --check` → `mypy` → `pytest`.
  Branch protection on `main` requires the job green.

## Testing Decisions

- **What makes a good test:** it asserts externally-observable behavior. Here that means one smoke test
  that issues an HTTP GET to `/health` through the FastAPI test client and asserts a 200 response — not
  the framework's internals.
- **Seam:** the HTTP seam (FastAPI test client). This is the highest available seam and the one later
  tickets reuse; no new seam is introduced.
- **Module tested:** the FastAPI app (`/health`).
- **Prior art:** none (greenfield). This ticket *is* the prior art — it establishes the HTTP-seam test
  pattern and the pytest+coverage configuration that tickets 02–10 follow.
- **Coverage gate:** `--cov-fail-under=80`, trivially satisfied by the `/health` test now; the threshold
  holds as real code lands.

## Out of Scope

- Any business logic: auth, models, migrations, uploads, LLM calls, scheduling (all later tickets).
- Database models and Alembic migrations, and any CI migration step (ticket 02).
- The real Postgres test harness / testcontainers fixtures (ticket 02 establishes these; testcontainers is
  only *declared* as a dev dependency here).
- A production/hardened Docker image and deployment concerns.
- Multi-version Python matrix in CI (single 3.12 job for now).

## Further Notes

- `gh` CLI is installed and authenticated (account `dionferns`, ADMIN on `dionferns/Memory-AI`), so the
  subsequent `/to-issues` step can create issues.
- Pre-existing uncommitted working-tree changes (LICENSE / main.py / docs deletions, `.gitignore` edits)
  are unrelated to this ticket and are intentionally left for the user to handle separately.
- This ticket is the foundation dependency for all others; nothing else can start until it is merged.
