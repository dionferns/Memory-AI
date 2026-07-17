"""Shared pytest fixtures for the DB integration seam (ticket 21).

This is the reusable harness later tickets (03-10) build their HTTP-seam
tests on:

- ``postgres_container`` / ``db_engine``: one Postgres testcontainer for the
  whole pytest run, migrated once via a real ``alembic upgrade head``
  subprocess (not ``Base.metadata.create_all()``).
- ``db_session``: wraps each test in an outer transaction plus a
  ``SAVEPOINT`` that's rolled back at teardown, so tests never leak state
  into each other without paying for a full schema reset per test.
- ``client``: a FastAPI ``TestClient`` whose ``get_db`` dependency is
  overridden to yield that same transactional session, giving later tickets
  a ready-made HTTP test seam.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, SessionTransaction
from testcontainers.postgres import PostgresContainer

from memory_ai.database import get_db
from memory_ai.main import app

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start one Postgres container for the whole pytest session."""
    with PostgresContainer("postgres:16", driver="psycopg") as container:
        yield container


@pytest.fixture(scope="session")
def db_engine(postgres_container: PostgresContainer) -> Iterator[Engine]:
    """Migrate the container via a real `alembic upgrade head` subprocess.

    Running it out-of-process (rather than calling `alembic.command.upgrade`
    in-process) means `alembic/env.py`'s own `get_settings().database_url`
    resolution (ticket 02 decision #15) picks up the container's URL exactly
    the way `uv run alembic upgrade head` would in dev/CI, without needing to
    mutate this process's cached `Settings` singleton.
    """
    url = postgres_container.get_connection_url()

    env = os.environ.copy()
    env["DATABASE_URL"] = url
    # `alembic/env.py` builds `Settings()` via the app's config module, which
    # requires these too; fall back to harmless placeholders if a developer
    # hasn't set them locally (CI already provides real placeholders).
    env.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-placeholder")
    env.setdefault("JWT_SECRET", "test-harness-placeholder-secret")

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Wrap a test in an outer transaction + SAVEPOINT, rolled back after.

    Standard SQLAlchemy pattern for isolating tests against a real database:
    bind a `Session` to a connection that already began an outer transaction,
    then open a nested transaction (`SAVEPOINT`). Application code is free to
    call `session.commit()` as normal -- committing only releases the
    SAVEPOINT, so an `after_transaction_end` listener immediately reopens a
    fresh one. Rolling back the outer transaction at teardown discards
    everything regardless of how many times the test "committed".
    """
    connection = db_engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(session: Session, transaction: SessionTransaction) -> None:
        parent = transaction._parent
        if transaction.nested and parent is not None and not parent.nested:
            session.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """A FastAPI TestClient wired to the per-test transactional session."""

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
