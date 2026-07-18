"""DB-harness tests for the ``apply_grade_to_card`` persistence helper.

Uses ticket 02/21's real-Postgres, rollback-per-test harness (the shared
``db_session`` fixture from ``tests/conftest.py``). Every assertion here
compares the mutated ``Card`` row and the created ``Review`` row against a
hand-computed ``apply_sm2`` result, per ``tickets/08-sr-algorithm/PRD.md``'s
persistence-helper test seam.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.models import Card, Folder, Review, Source, Subject, User
from memory_ai.scheduling import apply_grade_to_card, apply_sm2, today_in_tz

UTC_TZ = ZoneInfo("UTC")


def _make_card(
    session: Session, *, ease_factor: float = 2.5, interval_days: int = 0, repetitions: int = 0
) -> Card:
    """Build a full Source/Folder/Subject/User fixture chain and one Card."""
    user = User(
        email=f"sr-{id(object())}@example.com",
        password_hash="hashed",
        created_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()

    subject = Subject(user_id=user.id, name="Biology", created_at=datetime.now(UTC))
    session.add(subject)
    session.flush()

    folder = Folder(subject_id=subject.id, name="Cells", created_at=datetime.now(UTC))
    session.add(folder)
    session.flush()

    source = Source(
        folder_id=folder.id,
        filename="notes.txt",
        file_type="text/plain",
        raw_text="mitochondria is the powerhouse of the cell",
        status="ready",
        created_at=datetime.now(UTC),
    )
    session.add(source)
    session.flush()

    card = Card(
        source_id=source.id,
        folder_id=folder.id,
        front="What is the powerhouse of the cell?",
        back="The mitochondria",
        ease_factor=ease_factor,
        interval_days=interval_days,
        repetitions=repetitions,
        # Deliberately unrelated to any date a test/expected value might land
        # on, so a bug that leaves ``due_date`` unmutated can never pass by
        # coincidence with "today".
        due_date=date(2000, 1, 1),
        created_at=datetime.now(UTC),
    )
    session.add(card)
    session.flush()
    return card


def test_apply_grade_to_card_updates_card_and_creates_review(db_session: Session) -> None:
    card = _make_card(db_session, ease_factor=2.5, interval_days=0, repetitions=0)
    now_utc = datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC)

    today = today_in_tz(now_utc, UTC_TZ)
    expected = apply_sm2(ease_factor=2.5, interval_days=0, repetitions=0, grade="good", today=today)

    review = apply_grade_to_card(db_session, card, "good", now_utc, UTC_TZ)
    db_session.flush()

    assert card.ease_factor == expected.ease_factor
    assert card.interval_days == expected.interval_days
    assert card.repetitions == expected.repetitions
    assert card.due_date == expected.due_date
    assert card.last_reviewed_at == now_utc

    assert isinstance(review, Review)
    assert review.card_id == card.id
    assert review.grade == "good"
    assert review.reviewed_at == now_utc
    assert review.prev_interval_days == 0
    assert review.new_interval_days == expected.interval_days

    fetched = db_session.execute(select(Review).where(Review.card_id == card.id)).scalars().all()
    assert len(fetched) == 1
    assert fetched[0].id == review.id


def test_apply_grade_to_card_does_not_commit_or_flush(db_session: Session) -> None:
    """The helper itself must not commit/flush -- that's the caller's job."""
    card = _make_card(db_session, ease_factor=2.5, interval_days=0, repetitions=0)
    now_utc = datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC)

    review = apply_grade_to_card(db_session, card, "good", now_utc, UTC_TZ)

    # Still pending (added, not flushed/committed) and has no PK assigned yet.
    assert review in db_session.new
    assert review.id is None


def test_apply_grade_to_card_two_calls_in_sequence(db_session: Session) -> None:
    card = _make_card(db_session, ease_factor=2.5, interval_days=0, repetitions=0)

    first_now = datetime(2026, 7, 17, 9, 0, 0, tzinfo=UTC)
    second_now = datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)

    first_today = today_in_tz(first_now, UTC_TZ)
    first_expected = apply_sm2(
        ease_factor=2.5, interval_days=0, repetitions=0, grade="good", today=first_today
    )

    first_review = apply_grade_to_card(db_session, card, "good", first_now, UTC_TZ)
    db_session.flush()

    assert card.ease_factor == first_expected.ease_factor
    assert card.interval_days == first_expected.interval_days
    assert card.repetitions == first_expected.repetitions
    assert card.due_date == first_expected.due_date
    assert first_review.prev_interval_days == 0
    assert first_review.new_interval_days == first_expected.interval_days

    second_today = today_in_tz(second_now, UTC_TZ)
    second_expected = apply_sm2(
        ease_factor=first_expected.ease_factor,
        interval_days=first_expected.interval_days,
        repetitions=first_expected.repetitions,
        grade="easy",
        today=second_today,
    )

    second_review = apply_grade_to_card(db_session, card, "easy", second_now, UTC_TZ)
    db_session.flush()

    assert card.ease_factor == second_expected.ease_factor
    assert card.interval_days == second_expected.interval_days
    assert card.repetitions == second_expected.repetitions
    assert card.due_date == second_expected.due_date
    assert card.last_reviewed_at == second_now
    assert second_review.prev_interval_days == first_expected.interval_days
    assert second_review.new_interval_days == second_expected.interval_days

    reviews = (
        db_session.execute(select(Review).where(Review.card_id == card.id).order_by(Review.id))
        .scalars()
        .all()
    )
    assert len(reviews) == 2
    assert reviews[0].id == first_review.id
    assert reviews[1].id == second_review.id
    assert reviews[0].grade == "good"
    assert reviews[1].grade == "easy"
    assert reviews[0].reviewed_at == first_now
    assert reviews[1].reviewed_at == second_now
