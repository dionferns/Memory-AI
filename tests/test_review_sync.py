"""End-to-end test suite for the full review-flows surface (ticket 09, issue #53).

This is the ticket's explicit "sync test: grade in one view, assert the
other reflects the new due_date" plus the remaining required tests from the
PRD's Testing Decisions that aren't already exercised incidentally by
issues #44/#48/#51's own acceptance-criteria tests:

- Sync guarantee, both directions (subject -> global, global -> subject).
- Cap + most-overdue ordering (global), directly against the shared query
  with the user's real ``daily_review_cap``, plus an HTTP-level check that
  overflow beyond the cap remains reachable via the uncapped subject view
  (PRD story 32: overflow cards "remain due", never hidden).
- Subject review uncapped, at the HTTP seam.
- Timezone boundary: a card due exactly at a user's local midnight is
  included/excluded correctly depending on ``user_settings.timezone``,
  using a frozen "now" (monkeypatched) so the test is deterministic
  regardless of wall-clock time when it runs.
- Empty state for both scopes, at the HTTP seam.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``) -- no new test seam.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Source, Subject, User, UserSettings
from memory_ai.reviews.queries import get_due_cards

TEST_EMAIL = "review-sync-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"

_CAP = 3


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    now = datetime.now(UTC)
    user = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=user.id,
            daily_review_cap=_CAP,
            timezone="UTC",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authed_client(client: TestClient, seeded_user: User) -> TestClient:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    return client


def _make_subject(db_session: Session, user_id: int, name: str = "Subject") -> Subject:
    subject = Subject(user_id=user_id, name=name, created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)
    return subject


def _make_folder(db_session: Session, subject_id: int, name: str = "Folder") -> Folder:
    folder = Folder(subject_id=subject_id, name=name, created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
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
    db_session.commit()
    db_session.refresh(source)
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
    db_session.commit()
    db_session.refresh(card)
    return card


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    return _make_subject(db_session, seeded_user.id, "Mine")


@pytest.fixture
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    return _make_folder(db_session, my_subject.id)


@pytest.fixture
def my_source(db_session: Session, my_folder: Folder) -> Source:
    return _make_source(db_session, my_folder.id)


# --- Sync guarantee ---------------------------------------------------------


def test_grading_via_subject_scope_removes_card_from_global_view(
    authed_client: TestClient,
    db_session: Session,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    today = date.today()
    card = _make_card(db_session, my_source.id, my_folder.id, today, "Q", "A")

    before = authed_client.get("/review")
    assert f"review-card-{card.id}-front" in before.text

    grade_response = authed_client.post(
        f"/review/grade/{card.id}",
        data={"grade": "good", "scope": "subject", "subject_id": str(my_subject.id)},
    )
    assert grade_response.status_code == 200

    after = authed_client.get("/review")
    assert f"review-card-{card.id}-front" not in after.text
    assert "review-empty-global" in after.text


def test_grading_via_global_scope_removes_card_from_subject_view(
    authed_client: TestClient,
    db_session: Session,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    today = date.today()
    card = _make_card(db_session, my_source.id, my_folder.id, today, "Q", "A")

    before = authed_client.get(f"/review/subjects/{my_subject.id}")
    assert f"review-card-{card.id}-front" in before.text

    grade_response = authed_client.post(
        f"/review/grade/{card.id}", data={"grade": "easy", "scope": "global"}
    )
    assert grade_response.status_code == 200

    after = authed_client.get(f"/review/subjects/{my_subject.id}")
    assert f"review-card-{card.id}-front" not in after.text
    assert f"review-empty-subject-{my_subject.id}" in after.text


# --- Cap + most-overdue ordering (global) -----------------------------------


def test_global_review_returns_exactly_cap_cards_most_overdue_first(
    db_session: Session,
    seeded_user: User,
    my_source: Source,
    my_folder: Folder,
) -> None:
    """seeded_user's daily_review_cap is 3 -- seed 5 due cards across two
    subjects with distinct due dates in the past. A single call must
    return exactly the cap's worth, oldest-due_date-first -- the same
    query the global route calls with the user's real cap."""
    today = date.today()
    other_subject = _make_subject(db_session, seeded_user.id, "Other")
    other_folder = _make_folder(db_session, other_subject.id)
    other_source = _make_source(db_session, other_folder.id, "other.txt")

    due_offsets = [1, 10, 3, 7, 2]
    cards = []
    for i, offset in enumerate(due_offsets):
        source, folder = (my_source, my_folder) if i % 2 == 0 else (other_source, other_folder)
        cards.append(_make_card(db_session, source.id, folder.id, today - timedelta(days=offset)))

    result = get_due_cards(db_session, seeded_user.id, subject_id=None, limit=_CAP, as_of=today)

    assert len(result) == _CAP
    expected_order = sorted(cards, key=lambda c: c.due_date)[:_CAP]
    assert [c.id for c in result] == [c.id for c in expected_order]


def test_global_cap_does_not_hide_overflow_cards_from_subject_view(
    authed_client: TestClient,
    db_session: Session,
    seeded_user: User,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    """PRD story 32: overflow cards (beyond the cap) remain due, not
    dropped -- they're still reachable via the uncapped subject view even
    though the global (capped) query wouldn't return all of them."""
    today = date.today()
    for i in range(_CAP + 2):
        _make_card(db_session, my_source.id, my_folder.id, today - timedelta(days=i))

    capped = get_due_cards(db_session, seeded_user.id, subject_id=None, limit=_CAP, as_of=today)
    assert len(capped) == _CAP

    uncapped = get_due_cards(
        db_session, seeded_user.id, subject_id=my_subject.id, limit=None, as_of=today
    )
    assert len(uncapped) == _CAP + 2

    response = authed_client.get(f"/review/subjects/{my_subject.id}")
    assert response.status_code == 200
    most_overdue_id = uncapped[0].id
    assert f"review-card-{most_overdue_id}-front" in response.text


# --- Subject review uncapped, at the HTTP seam ------------------------------


def test_subject_review_http_returns_more_than_cap_worth_via_repeated_grading(
    authed_client: TestClient,
    db_session: Session,
    my_subject: Subject,
    my_source: Source,
    my_folder: Folder,
) -> None:
    """Grade every due card in the subject one at a time via the subject
    scope; assert every one of them (more than the global cap) was
    reachable through the subject route -- proving it never silently
    truncates to the cap."""
    today = date.today()
    seeded_ids = {
        _make_card(db_session, my_source.id, my_folder.id, today - timedelta(days=i)).id
        for i in range(_CAP + 2)
    }

    seen_ids: set[int] = set()
    response = authed_client.get(f"/review/subjects/{my_subject.id}")
    for _ in range(len(seeded_ids) + 1):
        if f"review-empty-subject-{my_subject.id}" in response.text:
            break
        current_id = next(cid for cid in seeded_ids if f"review-card-{cid}-front" in response.text)
        seen_ids.add(current_id)
        response = authed_client.post(
            f"/review/grade/{current_id}",
            data={"grade": "good", "scope": "subject", "subject_id": str(my_subject.id)},
        )

    assert seen_ids == seeded_ids
    assert f"review-empty-subject-{my_subject.id}" in response.text


# --- Timezone boundary -------------------------------------------------------


def test_local_midnight_boundary_differs_from_naive_utc(
    authed_client: TestClient,
    db_session: Session,
    seeded_user: User,
    my_source: Source,
    my_folder: Folder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeze "now" to 05:00 UTC. Under UTC, today's date is the same
    calendar day; under America/Los_Angeles (UTC-7 in July, PDT), local
    time is 22:00 the *previous* day, so "today" there is one day earlier.
    A card due on the UTC calendar day is therefore due under a UTC-only
    comparison but *not yet* due once the user's own timezone is honored --
    this is the exact "naive UTC-only comparison would disagree" case the
    PRD's tz-boundary test calls for."""
    frozen_now = datetime(2026, 7, 18, 5, 0, 0, tzinfo=UTC)

    class _FrozenClock:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return frozen_now if tz is None else frozen_now.astimezone(tz)  # type: ignore[arg-type]

    import memory_ai.reviews.routes as routes_module

    monkeypatch.setattr(routes_module, "datetime", _FrozenClock)

    # Sanity: UTC's calendar date at this instant is 2026-07-18; LA's is
    # 2026-07-17 (one day earlier).
    utc_today = frozen_now.date()
    la_today = frozen_now.astimezone(ZoneInfo("America/Los_Angeles")).date()
    assert la_today == utc_today - timedelta(days=1)

    card = _make_card(db_session, my_source.id, my_folder.id, utc_today, "Boundary Q", "Boundary A")

    # seeded_user is UTC -- the card (due on utc_today) is due now.
    utc_response = authed_client.get("/review")
    assert f"review-card-{card.id}-front" in utc_response.text

    # A second user in America/Los_Angeles, same instant: local "today" is
    # utc_today - 1 day, so this same due_date is *not yet* due for them.
    now = datetime.now(UTC)
    la_user = User(
        email="review-sync-la-user@example.com",
        password_hash=hash_password(TEST_PASSWORD),
        created_at=now,
    )
    db_session.add(la_user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=la_user.id,
            daily_review_cap=_CAP,
            timezone="America/Los_Angeles",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    db_session.refresh(la_user)

    la_subject = _make_subject(db_session, la_user.id, "LA Subject")
    la_folder = _make_folder(db_session, la_subject.id)
    la_source = _make_source(db_session, la_folder.id, "la.txt")
    la_card = _make_card(db_session, la_source.id, la_folder.id, utc_today, "LA Q", "LA A")

    la_client = TestClient(authed_client.app)
    la_client.cookies.set("access_token", create_access_token(la_user.id))
    la_response = la_client.get("/review")

    assert f"review-card-{la_card.id}-front" not in la_response.text
    assert "review-empty-global" in la_response.text


# --- Empty state, both scopes, at the HTTP seam -----------------------------


def test_global_empty_state_when_no_cards_due(authed_client: TestClient) -> None:
    response = authed_client.get("/review")

    assert response.status_code == 200
    assert "review-empty-global" in response.text


def test_subject_empty_state_when_no_cards_due(
    authed_client: TestClient, my_subject: Subject
) -> None:
    response = authed_client.get(f"/review/subjects/{my_subject.id}")

    assert response.status_code == 200
    assert f"review-empty-subject-{my_subject.id}" in response.text
