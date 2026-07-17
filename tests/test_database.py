"""Checks for the `get_db` FastAPI dependency.

No live DB connection is required: SQLAlchemy engines/sessions connect
lazily, so we can exercise the yield/close lifecycle without a reachable
Postgres. Full integration coverage lives in ticket 21's test harness.
"""

from sqlalchemy.orm import Session

from memory_ai.database import get_db


def test_get_db_yields_a_session_and_closes_it() -> None:
    gen = get_db()

    db = next(gen)
    assert isinstance(db, Session)
    assert db.is_active

    # Exhausting the generator runs the `finally: db.close()` block.
    next(gen, None)
