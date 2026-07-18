"""HTTP-seam tests for the settings flow: ``GET /settings`` and ``POST /settings``.

Seam: ticket 21's shared harness -- FastAPI ``TestClient`` + real Postgres via
testcontainers, wrapped in a per-test transaction that's rolled back at
teardown (``tests/conftest.py``'s ``client``/``db_session`` fixtures).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, hash_password
from memory_ai.models import User, UserSettings

TEST_EMAIL = "settings-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"

_INITIAL_CAP = 20
_INITIAL_TIMEZONE = "UTC"


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    """Insert a user with a known ``user_settings`` row."""
    now = datetime.now(UTC)
    user = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), created_at=now)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSettings(
            user_id=user.id,
            daily_review_cap=_INITIAL_CAP,
            timezone=_INITIAL_TIMEZONE,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def logged_in_client(client: TestClient, seeded_user: User) -> TestClient:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)
    return client


def _fetch_settings(db_session: Session, user_id: int) -> UserSettings:
    return db_session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    ).scalar_one()


def test_get_settings_renders_current_persisted_values(
    logged_in_client: TestClient,
) -> None:
    response = logged_in_client.get("/settings")

    assert response.status_code == 200
    assert "settings-form" in response.text
    assert 'value="20"' in response.text
    assert 'value="UTC" selected' in response.text


def test_get_settings_while_logged_out_redirects_to_login(client: TestClient) -> None:
    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_get_settings_while_logged_out_via_htmx_returns_401_with_hx_redirect(
    client: TestClient,
) -> None:
    response = client.get("/settings", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 401
    assert response.headers.get("hx-redirect") == "/login"


def test_post_settings_happy_path_persists_both_fields_and_reflects_new_values(
    logged_in_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = logged_in_client.post(
        "/settings",
        data={"daily_review_cap": "45", "timezone": "America/New_York"},
    )

    assert response.status_code == 200
    assert "Settings updated" in response.text
    assert 'value="45"' in response.text
    assert 'value="America/New_York" selected' in response.text

    settings_row = _fetch_settings(db_session, seeded_user.id)
    assert settings_row.daily_review_cap == 45
    assert settings_row.timezone == "America/New_York"


@pytest.mark.parametrize("bad_cap", ["0", "501", "not-a-number", "-5"])
def test_post_settings_cap_out_of_range_is_rejected_and_row_unchanged(
    logged_in_client: TestClient, db_session: Session, seeded_user: User, bad_cap: str
) -> None:
    response = logged_in_client.post(
        "/settings",
        data={"daily_review_cap": bad_cap, "timezone": "America/New_York"},
    )

    assert response.status_code == 200
    assert 'id="daily_review_cap-error"' in response.text

    settings_row = _fetch_settings(db_session, seeded_user.id)
    assert settings_row.daily_review_cap == _INITIAL_CAP
    assert settings_row.timezone == _INITIAL_TIMEZONE


def test_post_settings_invalid_timezone_is_rejected_and_row_unchanged(
    logged_in_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = logged_in_client.post(
        "/settings",
        data={"daily_review_cap": "45", "timezone": "Mars/Olympus_Mons"},
    )

    assert response.status_code == 200
    assert 'id="timezone-error"' in response.text

    settings_row = _fetch_settings(db_session, seeded_user.id)
    assert settings_row.daily_review_cap == _INITIAL_CAP
    assert settings_row.timezone == _INITIAL_TIMEZONE


def test_post_settings_valid_cap_and_invalid_timezone_persists_neither(
    logged_in_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = logged_in_client.post(
        "/settings",
        data={"daily_review_cap": "99", "timezone": "Not/AZone"},
    )

    assert response.status_code == 200
    assert 'id="timezone-error"' in response.text
    assert 'id="daily_review_cap-error"' not in response.text

    settings_row = _fetch_settings(db_session, seeded_user.id)
    assert settings_row.daily_review_cap == _INITIAL_CAP
    assert settings_row.timezone == _INITIAL_TIMEZONE


def test_post_settings_invalid_cap_and_valid_timezone_persists_neither(
    logged_in_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = logged_in_client.post(
        "/settings",
        data={"daily_review_cap": "9999", "timezone": "America/New_York"},
    )

    assert response.status_code == 200
    assert 'id="daily_review_cap-error"' in response.text
    assert 'id="timezone-error"' not in response.text

    settings_row = _fetch_settings(db_session, seeded_user.id)
    assert settings_row.daily_review_cap == _INITIAL_CAP
    assert settings_row.timezone == _INITIAL_TIMEZONE


def test_post_settings_while_logged_out_redirects_to_login(client: TestClient) -> None:
    response = client.post(
        "/settings",
        data={"daily_review_cap": "45", "timezone": "America/New_York"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
