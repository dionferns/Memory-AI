"""HTTP-seam tests for inline card delete (ticket 07, issue #77).

Covers the two-step inline confirm swap (`GET /cards/{id}/delete-confirm`
-> "Confirm delete? / Cancel"), `DELETE /cards/{id}` (row removal + cascade
to `reviews`), and cross-user/nonexistent-id 404s.

Seam: ticket 21's shared harness (`client` fixture: FastAPI `TestClient` +
real Postgres testcontainer + per-test transaction rollback via
`db_session`).
"""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Review, Source, Subject, User

TEST_EMAIL = "cards-delete-seam-test-user@example.com"
OTHER_EMAIL = "cards-delete-seam-other-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    user = User(
        email=TEST_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session: Session) -> User:
    user = User(
        email=OTHER_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
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
        raw_text="Some notes.",
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
    front: str = "Front",
    back: str = "Back",
) -> Card:
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front=front,
        back=back,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
        due_date=date(2026, 8, 1),
        created_at=datetime.now(UTC),
    )
    db_session.add(card)
    db_session.commit()
    db_session.refresh(card)
    return card


def _make_review(db_session: Session, card_id: int) -> Review:
    review = Review(
        card_id=card_id,
        grade="good",
        reviewed_at=datetime.now(UTC),
        prev_interval_days=0,
        new_interval_days=1,
    )
    db_session.add(review)
    db_session.commit()
    db_session.refresh(review)
    return review


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    return _make_subject(db_session, seeded_user.id, "System Design")


@pytest.fixture
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    return _make_folder(db_session, my_subject.id, "Caching")


@pytest.fixture
def my_source(db_session: Session, my_folder: Folder) -> Source:
    return _make_source(db_session, my_folder.id)


@pytest.fixture
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Not Mine")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Theirs")


@pytest.fixture
def their_source(db_session: Session, their_folder: Folder) -> Source:
    return _make_source(db_session, their_folder.id)


def _card_exists(db_session: Session, card_id: int) -> bool:
    db_session.expire_all()
    return (
        db_session.execute(select(Card).where(Card.id == card_id)).scalar_one_or_none() is not None
    )


def _reviews_for(db_session: Session, card_id: int) -> list[Review]:
    db_session.expire_all()
    return list(db_session.execute(select(Review).where(Review.card_id == card_id)).scalars().all())


# --- GET /cards/{id}/delete-confirm -----------------------------------------


def test_delete_confirm_renders_confirm_and_cancel_pair(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id)

    response = authed_client.get(f"/cards/{card.id}/delete-confirm")

    assert response.status_code == 200
    text = response.text
    assert "Confirm delete?" in text
    assert f'hx-delete="/cards/{card.id}"' in text
    assert f'hx-get="/cards/{card.id}"' in text
    # No native `confirm()` dialog and no modal -- must not appear anywhere.
    assert "confirm(" not in text
    assert "<dialog" not in text


def test_delete_confirm_for_other_users_card_returns_404(
    authed_client: TestClient, db_session: Session, their_source: Source, their_folder: Folder
) -> None:
    theirs = _make_card(db_session, their_source.id, their_folder.id)

    response = authed_client.get(f"/cards/{theirs.id}/delete-confirm")

    assert response.status_code == 404


def test_delete_confirm_for_nonexistent_card_returns_404(authed_client: TestClient) -> None:
    response = authed_client.get("/cards/999999999/delete-confirm")

    assert response.status_code == 404


# --- Cancel restores display row without deleting ---------------------------


def test_cancel_restores_display_row_without_deleting(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id, "Keep me", "Still here")

    # "Cancel" is just a GET back to the display fragment -- proving it never
    # calls the delete endpoint is exactly "the card still exists after".
    response = authed_client.get(f"/cards/{card.id}")

    assert response.status_code == 200
    assert "Keep me" in response.text
    assert "Still here" in response.text
    assert _card_exists(db_session, card.id)


# --- DELETE /cards/{id} ------------------------------------------------------


def test_delete_card_removes_row_and_returns_empty_body(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id)

    response = authed_client.delete(f"/cards/{card.id}")

    assert response.status_code == 200
    assert response.text == ""
    assert not _card_exists(db_session, card.id)


def test_delete_card_with_reviews_cascades_review_deletion(
    authed_client: TestClient, db_session: Session, my_source: Source, my_folder: Folder
) -> None:
    card = _make_card(db_session, my_source.id, my_folder.id)
    review_a = _make_review(db_session, card.id)
    review_b = _make_review(db_session, card.id)
    # Capture the ids before the delete call -- once the DB cascade removes
    # the rows, the ORM instances become stale and accessing an attribute on
    # them re-queries and raises `ObjectDeletedError` instead of returning a
    # value.
    review_ids = {review_a.id, review_b.id}
    assert len(_reviews_for(db_session, card.id)) == 2

    response = authed_client.delete(f"/cards/{card.id}")

    assert response.status_code == 200
    assert not _card_exists(db_session, card.id)
    # The cascade must actually remove the specific review rows, not just
    # leave the count at zero for a coincidental reason.
    remaining_review_ids = {r.id for r in db_session.execute(select(Review)).scalars().all()}
    assert review_ids.isdisjoint(remaining_review_ids)
    assert _reviews_for(db_session, card.id) == []


def test_delete_other_users_card_returns_404_and_does_not_delete_it(
    authed_client: TestClient, db_session: Session, their_source: Source, their_folder: Folder
) -> None:
    theirs = _make_card(db_session, their_source.id, their_folder.id)

    response = authed_client.delete(f"/cards/{theirs.id}")

    assert response.status_code == 404
    assert _card_exists(db_session, theirs.id)


def test_delete_other_users_card_does_not_cascade_delete_its_reviews(
    authed_client: TestClient, db_session: Session, their_source: Source, their_folder: Folder
) -> None:
    theirs = _make_card(db_session, their_source.id, their_folder.id)
    review = _make_review(db_session, theirs.id)

    response = authed_client.delete(f"/cards/{theirs.id}")

    assert response.status_code == 404
    assert _card_exists(db_session, theirs.id)
    remaining = _reviews_for(db_session, theirs.id)
    assert [r.id for r in remaining] == [review.id]


def test_delete_nonexistent_card_returns_404(authed_client: TestClient) -> None:
    response = authed_client.delete("/cards/999999999")

    assert response.status_code == 404


def test_delete_card_unauthenticated_redirects(client: TestClient) -> None:
    response = client.delete("/cards/1", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_delete_confirm_unauthenticated_redirects(client: TestClient) -> None:
    response = client.get("/cards/1/delete-confirm", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
