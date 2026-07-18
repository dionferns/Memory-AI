"""Query-level tests for ``get_due_cards`` (ticket 09, issue #44).

Exercises the shared "what's due" query directly against the DB harness:
ordering, cap via ``LIMIT``, subject filtering, the ``as_of`` boundary, and
user scoping. The HTTP-seam tests in ``test_review_global.py`` cover the
route built on top of this function.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from memory_ai.models import Card, Folder, Source, Subject, User
from memory_ai.reviews.queries import get_due_cards


def _make_user(db_session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed", created_at=datetime.now(UTC))
    db_session.add(user)
    db_session.flush()
    return user


def _make_subject(db_session: Session, user_id: int, name: str = "Subject") -> Subject:
    subject = Subject(user_id=user_id, name=name, created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.flush()
    return subject


def _make_folder(db_session: Session, subject_id: int, name: str = "Folder") -> Folder:
    folder = Folder(subject_id=subject_id, name=name, created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.flush()
    return folder


def _make_source(db_session: Session, folder_id: int, filename: str = "notes.txt") -> Source:
    source = Source(
        folder_id=folder_id,
        filename=filename,
        file_type="txt",
        raw_text="notes",
        status="done",
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.flush()
    return source


def _make_card(
    db_session: Session,
    source_id: int,
    folder_id: int,
    due_date: date,
    front: str = "front",
    back: str = "back",
) -> Card:
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
        due_date=due_date,
        created_at=datetime.now(UTC),
    )
    db_session.add(card)
    db_session.flush()
    return card


def test_get_due_cards_orders_most_overdue_first(db_session: Session) -> None:
    user = _make_user(db_session, "queries-order@example.com")
    subject = _make_subject(db_session, user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    today = date(2026, 7, 18)
    newest_due = _make_card(db_session, source.id, folder.id, today - timedelta(days=1))
    oldest_due = _make_card(db_session, source.id, folder.id, today - timedelta(days=10))
    middle_due = _make_card(db_session, source.id, folder.id, today - timedelta(days=5))

    result = get_due_cards(db_session, user.id, as_of=today)

    assert [c.id for c in result] == [oldest_due.id, middle_due.id, newest_due.id]


def test_get_due_cards_tiebreaks_same_due_date_by_id(db_session: Session) -> None:
    user = _make_user(db_session, "queries-tiebreak@example.com")
    subject = _make_subject(db_session, user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    today = date(2026, 7, 18)
    same_due_date = today - timedelta(days=1)
    first = _make_card(db_session, source.id, folder.id, same_due_date)
    second = _make_card(db_session, source.id, folder.id, same_due_date)

    result = get_due_cards(db_session, user.id, as_of=today)

    assert [c.id for c in result] == sorted([first.id, second.id])


def test_get_due_cards_excludes_cards_due_after_as_of(db_session: Session) -> None:
    user = _make_user(db_session, "queries-future@example.com")
    subject = _make_subject(db_session, user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    today = date(2026, 7, 18)
    due_card = _make_card(db_session, source.id, folder.id, today)
    future_card = _make_card(db_session, source.id, folder.id, today + timedelta(days=1))

    result = get_due_cards(db_session, user.id, as_of=today)

    result_ids = [c.id for c in result]
    assert due_card.id in result_ids
    assert future_card.id not in result_ids


def test_get_due_cards_applies_limit(db_session: Session) -> None:
    user = _make_user(db_session, "queries-limit@example.com")
    subject = _make_subject(db_session, user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    today = date(2026, 7, 18)
    for i in range(5):
        _make_card(db_session, source.id, folder.id, today - timedelta(days=i))

    result = get_due_cards(db_session, user.id, limit=2, as_of=today)

    assert len(result) == 2


def test_get_due_cards_limit_larger_than_due_count_is_a_no_op(db_session: Session) -> None:
    user = _make_user(db_session, "queries-limit-noop@example.com")
    subject = _make_subject(db_session, user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    today = date(2026, 7, 18)
    _make_card(db_session, source.id, folder.id, today)
    _make_card(db_session, source.id, folder.id, today)

    result = get_due_cards(db_session, user.id, limit=100, as_of=today)

    assert len(result) == 2


def test_get_due_cards_filters_by_subject(db_session: Session) -> None:
    user = _make_user(db_session, "queries-subject@example.com")
    subject_a = _make_subject(db_session, user.id, "Subject A")
    subject_b = _make_subject(db_session, user.id, "Subject B")
    folder_a = _make_folder(db_session, subject_a.id)
    folder_b = _make_folder(db_session, subject_b.id)
    source_a = _make_source(db_session, folder_a.id, "a.txt")
    source_b = _make_source(db_session, folder_b.id, "b.txt")

    today = date(2026, 7, 18)
    card_a = _make_card(db_session, source_a.id, folder_a.id, today)
    _make_card(db_session, source_b.id, folder_b.id, today)

    result = get_due_cards(db_session, user.id, subject_id=subject_a.id, as_of=today)

    assert [c.id for c in result] == [card_a.id]


def test_get_due_cards_scopes_to_user(db_session: Session) -> None:
    user = _make_user(db_session, "queries-scope-mine@example.com")
    other = _make_user(db_session, "queries-scope-theirs@example.com")
    my_subject = _make_subject(db_session, user.id)
    their_subject = _make_subject(db_session, other.id)
    my_folder = _make_folder(db_session, my_subject.id)
    their_folder = _make_folder(db_session, their_subject.id)
    my_source = _make_source(db_session, my_folder.id, "mine.txt")
    their_source = _make_source(db_session, their_folder.id, "theirs.txt")

    today = date(2026, 7, 18)
    my_card = _make_card(db_session, my_source.id, my_folder.id, today)
    _make_card(db_session, their_source.id, their_folder.id, today)

    result = get_due_cards(db_session, user.id, as_of=today)

    assert [c.id for c in result] == [my_card.id]


def test_get_due_cards_no_due_cards_returns_empty_list(db_session: Session) -> None:
    user = _make_user(db_session, "queries-empty@example.com")
    subject = _make_subject(db_session, user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)

    today = date(2026, 7, 18)
    _make_card(db_session, source.id, folder.id, today + timedelta(days=1))

    result = get_due_cards(db_session, user.id, as_of=today)

    assert result == []
