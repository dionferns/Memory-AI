"""Tests for `generation.reconcile_interrupted_jobs` (issue #125).

`BackgroundTasks` jobs are purely in-memory: if the process exits between
`convert_source` committing `status="processing"` and `_run_generation_job`
finishing, no code will ever run to flip that source out of `processing` --
it's stuck forever. `reconcile_interrupted_jobs` is called once at app
startup (`main._lifespan`) to deterministically fail out any such leftover
row before the app serves its first request.

Seam: ticket 21's shared harness (`db_session` fixture: real Postgres
testcontainer + per-test transaction rollback) -- no HTTP layer needed since
this is a plain persistence helper, not a route.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import hash_password
from memory_ai.generation import reconcile_interrupted_jobs
from memory_ai.models import Folder, Source, Subject, User

TEST_EMAIL = "reconcile-test-user@example.com"


def _make_user(db_session: Session) -> User:
    user = User(
        email=TEST_EMAIL,
        password_hash=hash_password("irrelevant-pw"),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_folder(db_session: Session, user: User) -> Folder:
    subject = Subject(user_id=user.id, name="Subject", created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)
    folder = Folder(subject_id=subject.id, name="Folder", created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


def _make_source(db_session: Session, folder: Folder, *, status: str) -> Source:
    source = Source(
        folder_id=folder.id,
        filename=f"notes-{status}.txt",
        file_type="txt",
        raw_text="Some notes.",
        status=status,
        error_message=None,
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def test_reconcile_fails_out_a_source_stuck_in_processing(db_session: Session) -> None:
    user = _make_user(db_session)
    folder = _make_folder(db_session, user)
    stuck = _make_source(db_session, folder, status="processing")

    reconciled_count = reconcile_interrupted_jobs(db_session)

    assert reconciled_count == 1
    db_session.expire_all()
    result = db_session.execute(select(Source).where(Source.id == stuck.id)).scalar_one()
    assert result.status == "failed"
    assert result.error_message is not None
    assert "restart" in result.error_message.lower()


def test_reconcile_leaves_done_and_failed_and_stored_sources_untouched(db_session: Session) -> None:
    user = _make_user(db_session)
    folder = _make_folder(db_session, user)
    done = _make_source(db_session, folder, status="done")
    failed = _make_source(db_session, folder, status="failed")
    stored = _make_source(db_session, folder, status="stored")

    reconciled_count = reconcile_interrupted_jobs(db_session)

    assert reconciled_count == 0
    db_session.expire_all()
    for source, expected_status in [(done, "done"), (failed, "failed"), (stored, "stored")]:
        result = db_session.execute(select(Source).where(Source.id == source.id)).scalar_one()
        assert result.status == expected_status


def test_reconcile_is_a_noop_with_no_sources(db_session: Session) -> None:
    assert reconcile_interrupted_jobs(db_session) == 0
