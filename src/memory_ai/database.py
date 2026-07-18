"""Sync SQLAlchemy engine/session setup and the FastAPI DB dependencies."""

from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from memory_ai.config import get_settings

engine = create_engine(get_settings().database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session and closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def _session_scope() -> Iterator[Session]:
    """Open a brand-new, independent session and close it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> Callable[[], AbstractContextManager[Session]]:
    """FastAPI dependency: a context-manager factory for an independent session.

    Used by ``BackgroundTasks`` jobs (ticket 06+) that must not depend on the
    request-scoped ``get_db`` session, which may already be closed by the
    time the background job actually runs. The returned factory opens a
    brand-new session bound to the same engine and closes it when the
    ``with`` block exits.

    Tests override this dependency to return a factory that yields the
    shared per-test transactional ``db_session`` *without* closing it, so a
    background job invoked during an HTTP-seam test lands its writes on the
    same connection the test asserts against, and the shared session stays
    usable after the request completes.
    """
    return _session_scope
