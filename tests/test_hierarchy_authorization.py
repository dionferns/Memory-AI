"""Dedicated cross-user authorization + cascade-delete hardening tests for
the hierarchy (ticket 04, issue #87).

These tests deliberately re-verify, as a focused cross-cutting slice, two
properties that #85 (subject CRUD) and #86 (folder CRUD) already build
correctly but don't exhaustively cover on their own:

1. A subject or folder belonging to another user (or that doesn't exist at
   all) is rejected identically with a 404 on every view/rename/delete
   route -- never a 403 -- so an id's ownership can never be probed for.
2. Deleting a subject or folder cascades all the way down through the
   schema (subject -> folder -> source -> card -> reviews), not just one
   level. Since source/card routes don't exist until ticket 05, source and
   card rows are inserted directly against the database in fixtures to
   prove the DB's ``ON DELETE CASCADE`` chain fires end-to-end.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Card, Folder, Review, Source, Subject, User

TEST_EMAIL = "authz-seam-test-user@example.com"
OTHER_EMAIL = "authz-seam-other-user@example.com"
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


def _make_source(db_session: Session, folder_id: int) -> Source:
    source = Source(
        folder_id=folder_id,
        filename="notes.txt",
        file_type="text/plain",
        raw_text="Some raw text.",
        status="processed",
        error_message=None,
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_card(db_session: Session, source_id: int, folder_id: int) -> Card:
    card = Card(
        source_id=source_id,
        folder_id=folder_id,
        front="Front",
        back="Back",
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
        due_date=date.today(),
        last_reviewed_at=None,
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
def their_subject(db_session: Session, other_user: User) -> Subject:
    return _make_subject(db_session, other_user.id, "Theirs")


@pytest.fixture
def their_folder(db_session: Session, their_subject: Subject) -> Folder:
    return _make_folder(db_session, their_subject.id, "Their Folder")


# --- Cross-user authorization: subjects ------------------------------------


def test_view_other_users_subject_returns_404_not_403(
    authed_client: TestClient, their_subject: Subject
) -> None:
    response = authed_client.get(f"/subjects/{their_subject.id}")

    assert response.status_code == 404
    assert response.status_code != 403


def test_edit_form_for_other_users_subject_returns_404_not_403(
    authed_client: TestClient, their_subject: Subject
) -> None:
    response = authed_client.get(f"/subjects/{their_subject.id}/edit")

    assert response.status_code == 404
    assert response.status_code != 403


def test_rename_other_users_subject_returns_404_not_403(
    authed_client: TestClient, their_subject: Subject
) -> None:
    response = authed_client.patch(f"/subjects/{their_subject.id}", data={"name": "Hijacked"})

    assert response.status_code == 404
    assert response.status_code != 403


def test_delete_other_users_subject_returns_404_not_403(
    authed_client: TestClient, their_subject: Subject
) -> None:
    response = authed_client.delete(f"/subjects/{their_subject.id}")

    assert response.status_code == 404
    assert response.status_code != 403


def test_create_folder_under_other_users_subject_returns_404_not_403(
    authed_client: TestClient, their_subject: Subject
) -> None:
    response = authed_client.post(f"/subjects/{their_subject.id}/folders", data={"name": "Sneaky"})

    assert response.status_code == 404
    assert response.status_code != 403


def test_nonexistent_subject_returns_identical_404_to_other_users_subject(
    authed_client: TestClient, their_subject: Subject
) -> None:
    """A nonexistent id and another user's real id must be indistinguishable."""
    nonexistent_response = authed_client.get("/subjects/999999999")
    not_owned_response = authed_client.get(f"/subjects/{their_subject.id}")

    assert nonexistent_response.status_code == not_owned_response.status_code == 404


# --- Cross-user authorization: folders --------------------------------------


def test_view_other_users_folder_returns_404_not_403(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{their_folder.id}")

    assert response.status_code == 404
    assert response.status_code != 403


def test_edit_form_for_other_users_folder_returns_404_not_403(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{their_folder.id}/edit")

    assert response.status_code == 404
    assert response.status_code != 403


def test_rename_other_users_folder_returns_404_not_403(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.patch(f"/folders/{their_folder.id}", data={"name": "Hijacked"})

    assert response.status_code == 404
    assert response.status_code != 403


def test_delete_other_users_folder_returns_404_not_403(
    authed_client: TestClient, their_folder: Folder
) -> None:
    response = authed_client.delete(f"/folders/{their_folder.id}")

    assert response.status_code == 404
    assert response.status_code != 403


def test_nonexistent_folder_returns_identical_404_to_other_users_folder(
    authed_client: TestClient, their_folder: Folder
) -> None:
    nonexistent_response = authed_client.get("/folders/999999999")
    not_owned_response = authed_client.get(f"/folders/{their_folder.id}")

    assert nonexistent_response.status_code == not_owned_response.status_code == 404


# --- Cascade delete: subject -> folder -> source -> card -> reviews -------


def test_deleting_a_subject_cascades_through_folder_source_card_and_reviews(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)
    card = _make_card(db_session, source.id, folder.id)
    review = _make_review(db_session, card.id)
    # Capture plain ids before the delete request: the route's own commit
    # expires every object in this shared session (it's the same session as
    # `db_session`, per the `client` fixture's `get_db` override), and the
    # DB-level cascade removes these rows out from under the ORM's back, so
    # any later attribute access on the stale `folder`/`source`/etc. objects
    # (even just reading `.id`) would try to refresh a row that's gone and
    # raise `ObjectDeletedError`.
    subject_id, folder_id, source_id, card_id, review_id = (
        subject.id,
        folder.id,
        source.id,
        card.id,
        review.id,
    )

    response = authed_client.delete(f"/subjects/{subject_id}")
    assert response.status_code == 200

    assert (
        db_session.execute(select(Subject).where(Subject.id == subject_id)).scalar_one_or_none()
        is None
    )
    assert (
        db_session.execute(select(Folder).where(Folder.id == folder_id)).scalar_one_or_none()
        is None
    )
    assert (
        db_session.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
        is None
    )
    assert db_session.execute(select(Card).where(Card.id == card_id)).scalar_one_or_none() is None
    assert (
        db_session.execute(select(Review).where(Review.id == review_id)).scalar_one_or_none()
        is None
    )


def test_deleting_a_subject_does_not_affect_a_sibling_subjects_data(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    doomed_subject = _make_subject(db_session, seeded_user.id, "Doomed")
    safe_subject = _make_subject(db_session, seeded_user.id, "Safe")
    safe_folder = _make_folder(db_session, safe_subject.id)
    safe_source = _make_source(db_session, safe_folder.id)
    safe_card = _make_card(db_session, safe_source.id, safe_folder.id)
    doomed_subject_id = doomed_subject.id
    safe_subject_id, safe_folder_id, safe_card_id = (
        safe_subject.id,
        safe_folder.id,
        safe_card.id,
    )

    response = authed_client.delete(f"/subjects/{doomed_subject_id}")
    assert response.status_code == 200

    assert (
        db_session.execute(
            select(Subject).where(Subject.id == safe_subject_id)
        ).scalar_one_or_none()
        is not None
    )
    assert (
        db_session.execute(select(Folder).where(Folder.id == safe_folder_id)).scalar_one_or_none()
        is not None
    )
    assert (
        db_session.execute(select(Card).where(Card.id == safe_card_id)).scalar_one_or_none()
        is not None
    )


# --- Cascade delete: folder -> source -> card -> reviews -------------------


def test_deleting_a_folder_cascades_through_source_card_and_reviews(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id)
    folder = _make_folder(db_session, subject.id)
    source = _make_source(db_session, folder.id)
    card = _make_card(db_session, source.id, folder.id)
    review = _make_review(db_session, card.id)
    # See the comment in the subject-cascade test above: ids must be
    # captured before the delete request, since the route's commit expires
    # every object in this shared session and the DB-level cascade removes
    # these rows out from under the ORM.
    subject_id, folder_id, source_id, card_id, review_id = (
        subject.id,
        folder.id,
        source.id,
        card.id,
        review.id,
    )

    response = authed_client.delete(f"/folders/{folder_id}")
    assert response.status_code == 200

    # The parent subject must survive -- only the folder and its descendants
    # are removed.
    assert (
        db_session.execute(select(Subject).where(Subject.id == subject_id)).scalar_one_or_none()
        is not None
    )
    assert (
        db_session.execute(select(Folder).where(Folder.id == folder_id)).scalar_one_or_none()
        is None
    )
    assert (
        db_session.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
        is None
    )
    assert db_session.execute(select(Card).where(Card.id == card_id)).scalar_one_or_none() is None
    assert (
        db_session.execute(select(Review).where(Review.id == review_id)).scalar_one_or_none()
        is None
    )


def test_deleting_a_folder_does_not_affect_a_sibling_folders_data(
    authed_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    subject = _make_subject(db_session, seeded_user.id)
    doomed_folder = _make_folder(db_session, subject.id, "Doomed")
    safe_folder = _make_folder(db_session, subject.id, "Safe")
    safe_source = _make_source(db_session, safe_folder.id)
    safe_card = _make_card(db_session, safe_source.id, safe_folder.id)

    response = authed_client.delete(f"/folders/{doomed_folder.id}")
    assert response.status_code == 200

    assert (
        db_session.execute(select(Folder).where(Folder.id == safe_folder.id)).scalar_one_or_none()
        is not None
    )
    assert (
        db_session.execute(select(Card).where(Card.id == safe_card.id)).scalar_one_or_none()
        is not None
    )
