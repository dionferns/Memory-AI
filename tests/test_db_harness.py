"""Round-trip test proving the DB test harness (ticket 21).

Exercises the harness itself, not application code: a real Postgres
testcontainer migrated via `alembic upgrade head`, per-test transactional
isolation (outer transaction + SAVEPOINT), and a FastAPI `TestClient` wired
to that same session via a `get_db` override. Later tickets build their own
HTTP-seam tests on top of these fixtures.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.models import Subject, User


def _make_user(db_session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed", created_at=datetime.now(UTC))
    db_session.add(user)
    db_session.flush()
    return user


def test_create_and_read_round_trip(db_session: Session) -> None:
    user = _make_user(db_session, "round-trip@example.com")

    subject = Subject(user_id=user.id, name="Biology", created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()

    fetched = db_session.execute(select(Subject).where(Subject.name == "Biology")).scalar_one()

    assert fetched.id == subject.id
    assert fetched.user_id == user.id
    assert fetched.name == "Biology"


def test_cascade_delete_removes_children(db_session: Session) -> None:
    user = _make_user(db_session, "cascade@example.com")

    subject = Subject(user_id=user.id, name="Chemistry", created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()
    subject_id = subject.id

    db_session.delete(user)
    db_session.commit()

    remaining = db_session.execute(
        select(Subject).where(Subject.id == subject_id)
    ).scalar_one_or_none()

    assert remaining is None


def test_rows_do_not_leak_across_tests(db_session: Session) -> None:
    """Guards the SAVEPOINT-rollback fixture: earlier tests' rows must be gone."""
    leaked = (
        db_session.execute(
            select(User).where(User.email.in_(["round-trip@example.com", "cascade@example.com"]))
        )
        .scalars()
        .all()
    )

    assert leaked == []


def test_health_via_transactional_test_client(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
