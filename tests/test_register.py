"""HTTP-seam tests for the registration flow: ``GET /register`` and
``POST /register``.

Seam: ticket 21's shared harness -- FastAPI ``TestClient`` + real Postgres
via testcontainers, wrapped in a per-test transaction that's rolled back at
teardown (``tests/conftest.py``'s ``client``/``db_session`` fixtures).
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.models import User, UserSettings

TEST_EMAIL = "register-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


def test_get_register_renders_form(client: TestClient) -> None:
    response = client.get("/register")

    assert response.status_code == 200
    assert "register-form" in response.text
    assert 'name="email"' in response.text
    assert 'name="password"' in response.text


def test_register_happy_path_creates_user_and_settings_and_sets_cookie(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.cookies.get("access_token") is not None

    user = db_session.execute(select(User).where(User.email == TEST_EMAIL)).scalar_one()
    settings = db_session.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    ).scalar_one()

    assert user.password_hash != TEST_PASSWORD
    assert settings.daily_review_cap > 0
    assert settings.timezone


def test_register_happy_path_sets_expected_cookie_attributes(client: TestClient) -> None:
    response = client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    set_cookie_header = response.headers.get("set-cookie", "")

    assert "access_token=" in set_cookie_header
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()
    assert "max-age=604800" in set_cookie_header.lower()
    # Secure must NOT be set in the (non-production) test environment.
    assert "secure" not in set_cookie_header.lower()


def test_register_via_htmx_returns_hx_redirect_header_and_sets_cookie(
    client: TestClient,
) -> None:
    response = client.post(
        "/register",
        data={"email": "htmx-" + TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/"
    assert response.cookies.get("access_token") is not None


def test_register_with_duplicate_email_returns_friendly_error_and_creates_no_rows(
    client: TestClient, db_session: Session
) -> None:
    first = client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": "a-different-password"},
        follow_redirects=False,
    )

    assert second.status_code == 200
    assert "already registered" in second.text.lower()
    assert second.cookies.get("access_token") is None

    users = db_session.execute(select(User).where(User.email == TEST_EMAIL)).scalars().all()
    assert len(users) == 1


def test_register_with_duplicate_email_does_not_touch_existing_password_hash(
    client: TestClient, db_session: Session
) -> None:
    client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    original = db_session.execute(select(User).where(User.email == TEST_EMAIL)).scalar_one()
    original_hash = original.password_hash

    client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": "a-different-password"},
        follow_redirects=False,
    )

    unchanged = db_session.execute(select(User).where(User.email == TEST_EMAIL)).scalar_one()
    assert unchanged.password_hash == original_hash


def test_register_with_short_password_returns_friendly_error_and_creates_no_rows(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/register",
        data={"email": TEST_EMAIL, "password": "short1"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "8 characters" in response.text
    assert response.cookies.get("access_token") is None

    users = db_session.execute(select(User).where(User.email == TEST_EMAIL)).scalars().all()
    assert users == []
