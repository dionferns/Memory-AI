"""Sync SQLAlchemy engine/session setup and the FastAPI DB dependency."""

from collections.abc import Generator

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
