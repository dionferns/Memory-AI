"""HTTP-seam tests for the global dark stylesheet (ticket 13, issue #112).

Covers the two acceptance criteria that can be checked at the HTTP seam:

- ``GET /static/styles.css`` is served (200) and its body contains the exact
  custom-property declarations for the palette locked in decisions.md #1/#3/
  #4/#5.
- Every current full-page template's rendered response links the stylesheet
  in its ``<head>`` via ``<link rel="stylesheet" href="/static/styles.css">``.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient``
+ real Postgres testcontainer + per-test transaction rollback).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import Folder, Source, Subject, User, UserSettings

TEST_EMAIL = "static-styles-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"

_LINK_TAG = '<link rel="stylesheet" href="/static/styles.css">'

# Exact custom-property declarations expected in styles.css, per decisions.md
# #1/#3/#4/#5 and the issue's acceptance criteria. Checked as whole
# declarations (property + exact hex value), not loose substrings, so a
# typo'd hex value or a renamed property fails the test.
_EXPECTED_DECLARATIONS = [
    "--bg: #1c1c1c;",
    "--surface: #2c4251;",
    "--accent-primary: #28965a;",
    "--accent-danger: #d16666;",
    "--text: #e8e8e8;",
]


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    now = datetime.now(UTC)
    user = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=user.id,
            daily_review_cap=20,
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


@pytest.fixture
def seeded_folder(db_session: Session, seeded_user: User) -> Folder:
    now = datetime.now(UTC)
    subject = Subject(user_id=seeded_user.id, name="Subject", created_at=now)
    db_session.add(subject)
    db_session.flush()
    folder = Folder(subject_id=subject.id, name="Folder", created_at=now)
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


@pytest.fixture
def seeded_source(db_session: Session, seeded_folder: Folder) -> Source:
    source = Source(
        folder_id=seeded_folder.id,
        filename="notes.txt",
        file_type="txt",
        raw_text="Some notes.",
        status="stored",
        created_at=datetime.now(UTC),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def test_styles_css_is_served(client: TestClient) -> None:
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "css" in response.headers["content-type"]


@pytest.mark.parametrize("declaration", _EXPECTED_DECLARATIONS)
def test_styles_css_contains_expected_custom_properties(
    client: TestClient, declaration: str
) -> None:
    response = client.get("/static/styles.css")

    assert declaration in response.text


def test_styles_css_border_is_derived_from_surface_not_a_literal_new_color(
    client: TestClient,
) -> None:
    """``--border`` must be present as a custom property but is a derived
    mid-tone (decisions.md #5), not one of the four supplied palette hexes --
    so unlike the other five vars this only checks the property exists.
    """
    response = client.get("/static/styles.css")

    assert "--border:" in response.text


def test_login_page_links_stylesheet(client: TestClient) -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert _LINK_TAG in response.text


def test_register_page_links_stylesheet(client: TestClient) -> None:
    response = client.get("/register")

    assert response.status_code == 200
    assert _LINK_TAG in response.text


def test_subjects_page_links_stylesheet(authed_client: TestClient) -> None:
    response = authed_client.get("/subjects")

    assert response.status_code == 200
    assert _LINK_TAG in response.text


def test_settings_page_links_stylesheet(authed_client: TestClient) -> None:
    response = authed_client.get("/settings")

    assert response.status_code == 200
    assert _LINK_TAG in response.text


def test_cards_folder_page_links_stylesheet(
    authed_client: TestClient, seeded_folder: Folder
) -> None:
    response = authed_client.get(f"/folders/{seeded_folder.id}/cards")

    assert response.status_code == 200
    assert _LINK_TAG in response.text


def test_cards_source_page_links_stylesheet(
    authed_client: TestClient, seeded_source: Source
) -> None:
    response = authed_client.get(f"/sources/{seeded_source.id}/cards")

    assert response.status_code == 200
    assert _LINK_TAG in response.text
