# Dev-only image for the `app` service. Not hardened or intended for production use.
FROM python:3.12-slim

# Install uv (used to manage deps and run the app in the same way as local dev).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching; source is bind-mounted at
# runtime for live reload, so it isn't copied into the image here.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN uv sync --frozen

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn memory_ai.main:app --reload --host 0.0.0.0 --port 8000"]
