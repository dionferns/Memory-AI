"""HTTP-seam tests for upload rejection paths (ticket 05, issue #55).

Covers the four distinct rejection cases the upload route (#52) maps the
parser's typed exceptions to: unsupported file extension, oversized file
(both the fast Content-Length check and the real streaming-read guard),
a PDF with no extractable text, and a corrupt/unreadable PDF. Every case
must return 422 with a case-specific message, render as the same
HTMX-swappable sources-section fragment, and create no `sources` row.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback via
``db_session``).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.hierarchy import _CONTENT_LENGTH_FAST_REJECT_BYTES, _SUPPORTED_TYPES_MESSAGE
from memory_ai.models import Folder, Source, Subject, User
from memory_ai.parsing import MAX_FILE_SIZE_BYTES
from tests.test_parsing import _build_pdf

TEST_EMAIL = "upload-rejection-seam-test-user@example.com"
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
def authed_client(client: TestClient, seeded_user: User) -> TestClient:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    return client


@pytest.fixture
def my_subject(db_session: Session, seeded_user: User) -> Subject:
    subject = Subject(user_id=seeded_user.id, name="System Design", created_at=datetime.now(UTC))
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)
    return subject


@pytest.fixture
def my_folder(db_session: Session, my_subject: Subject) -> Folder:
    folder = Folder(subject_id=my_subject.id, name="Caching", created_at=datetime.now(UTC))
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


def _no_sources(db_session: Session, folder_id: int) -> bool:
    rows = db_session.execute(select(Source).where(Source.folder_id == folder_id)).all()
    return rows == []


# --- Unsupported file type ---------------------------------------------------


def test_unsupported_extension_returns_422_naming_accepted_types(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.docx", b"whatever", "application/octet-stream")},
    )

    assert response.status_code == 422
    # The upload form's own static label also mentions "PDF, MD, or TXT", so
    # assert on the *exact* error message text (scoped inside the error
    # paragraph) rather than loose substrings that the static label would
    # satisfy regardless of what the route actually returned.
    assert f'<p class="error">{_SUPPORTED_TYPES_MESSAGE}</p>' in response.text
    assert "pdf" in _SUPPORTED_TYPES_MESSAGE
    assert "md" in _SUPPORTED_TYPES_MESSAGE
    assert "txt" in _SUPPORTED_TYPES_MESSAGE
    assert _no_sources(db_session, my_folder.id)


def test_unsupported_extension_renders_inline_htmx_error_fragment(
    authed_client: TestClient, my_folder: Folder
) -> None:
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("notes.docx", b"whatever", "application/octet-stream")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 422
    assert f'id="folder-{my_folder.id}-sources-section"' in response.text
    assert '<p class="error">' in response.text


# --- Oversized file -----------------------------------------------------------


def test_oversized_file_rejected_via_large_content_length_fast_path(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    # Comfortably over the fast-reject threshold, so the Content-Length
    # header alone triggers the early rejection before the body is parsed.
    oversized = b"a" * (_CONTENT_LENGTH_FAST_REJECT_BYTES + 1024)
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("big.txt", oversized, "text/plain")},
    )

    assert response.status_code == 422
    assert "too large" in response.text.lower()
    assert _no_sources(db_session, my_folder.id)


def test_oversized_file_rejected_via_streaming_guard(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    # Just one byte over the cap: comfortably under the fast-reject
    # Content-Length threshold, so this can only be caught by the real
    # streaming-read guard (proving Content-Length alone isn't trusted).
    just_over_cap = b"a" * (MAX_FILE_SIZE_BYTES + 1)
    assert len(just_over_cap) < _CONTENT_LENGTH_FAST_REJECT_BYTES

    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("big.txt", just_over_cap, "text/plain")},
    )

    assert response.status_code == 422
    assert "too large" in response.text.lower()
    assert _no_sources(db_session, my_folder.id)


def test_file_at_exact_cap_is_accepted(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    at_cap = b"a" * MAX_FILE_SIZE_BYTES
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("ok.txt", at_cap, "text/plain")},
    )

    assert response.status_code == 200
    source = db_session.execute(select(Source).where(Source.folder_id == my_folder.id)).scalar_one()
    assert source.status == "stored"


# --- PDF with no extractable text vs. corrupt PDF ----------------------------


def test_pdf_with_no_extractable_text_returns_422_distinct_message(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    no_text_pdf = _build_pdf(b"")
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("scan.pdf", no_text_pdf, "application/pdf")},
    )

    assert response.status_code == 422
    assert "scanned" in response.text.lower() or "no extractable text" in response.text.lower()
    assert _no_sources(db_session, my_folder.id)


def test_corrupt_pdf_returns_422_distinct_message(
    authed_client: TestClient, db_session: Session, my_folder: Folder
) -> None:
    corrupt_pdf = b"%PDF-1.4\nthis is not a real pdf structure, just garbage 1234567890"
    response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("corrupt.pdf", corrupt_pdf, "application/pdf")},
    )

    assert response.status_code == 422
    assert "could not read" in response.text.lower()
    assert _no_sources(db_session, my_folder.id)


def test_no_extractable_text_and_corrupt_pdf_messages_are_distinct(
    authed_client: TestClient, my_folder: Folder
) -> None:
    no_text_pdf = _build_pdf(b"")
    corrupt_pdf = b"%PDF-1.4\nthis is not a real pdf structure, just garbage 1234567890"

    no_text_response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("scan.pdf", no_text_pdf, "application/pdf")},
    )
    corrupt_response = authed_client.post(
        f"/folders/{my_folder.id}/sources",
        files={"file": ("corrupt.pdf", corrupt_pdf, "application/pdf")},
    )

    assert no_text_response.status_code == 422
    assert corrupt_response.status_code == 422
    # Extract just the error paragraph so this compares messages, not
    # incidental markup differences (e.g. different filenames elsewhere in
    # the fragment).
    assert "no extractable text" in no_text_response.text.lower()
    assert "could not read" in corrupt_response.text.lower()
    assert "could not read" not in no_text_response.text.lower()
    assert "no extractable text" not in corrupt_response.text.lower()
