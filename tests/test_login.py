"""HTTP-seam tests for the login flow: ``GET /login`` and ``POST /login``.

Seam: FastAPI ``TestClient`` against a real Postgres reachable at
``DATABASE_URL`` (matching the ticket-03 testing decision of "FastAPI
TestClient + real Postgres"). Ticket 21's shared test harness (testcontainers
+ per-test transaction rollback) had not landed on ``main`` yet at the time
this ticket was built, so this module manages its own seed/cleanup instead of
relying on shared fixtures. CI provisions a real Postgres service and runs
`alembic upgrade head` before `pytest`, so this suite runs there unmodified;
locally it requires a reachable, migrated Postgres at `DATABASE_URL`.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from memory_ai.auth import hash_password
from memory_ai.database import SessionLocal
from memory_ai.main import app
from memory_ai.models import User

client = TestClient(app)

TEST_EMAIL = "login-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def seeded_user() -> Generator[User, None, None]:
    """Insert (and clean up) a single known user for login tests."""
    db = SessionLocal()
    try:
        db.query(User).filter(User.email == TEST_EMAIL).delete()
        db.commit()

        user = User(
            email=TEST_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
            created_at=datetime.now(UTC),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user
    finally:
        db.query(User).filter(User.email == TEST_EMAIL).delete()
        db.commit()
        db.close()


def test_get_login_renders_form() -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert "login-form" in response.text
    assert 'name="email"' in response.text
    assert 'name="password"' in response.text


def test_login_with_correct_credentials_sets_cookie(seeded_user: User) -> None:
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303
    cookie = response.cookies.get("access_token")
    assert cookie is not None


def test_login_with_correct_credentials_sets_expected_cookie_attributes(
    seeded_user: User,
) -> None:
    response = client.post(
        "/login",
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


def test_login_via_htmx_returns_hx_redirect_header_and_sets_cookie(
    seeded_user: User,
) -> None:
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/subjects"
    assert response.cookies.get("access_token") is not None


def test_login_with_wrong_password_does_not_set_cookie(seeded_user: User) -> None:
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": "totally-wrong-password"},
        follow_redirects=False,
    )

    assert response.cookies.get("access_token") is None


def test_login_with_wrong_password_returns_generic_error() -> None:
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": "totally-wrong-password"},
        follow_redirects=False,
    )

    assert "invalid email or password" in response.text.lower()


def test_login_with_unknown_email_does_not_set_cookie() -> None:
    response = client.post(
        "/login",
        data={"email": "no-such-user@example.com", "password": "whatever123"},
        follow_redirects=False,
    )

    assert response.cookies.get("access_token") is None


def test_login_with_unknown_email_returns_same_generic_error_as_wrong_password(
    seeded_user: User,
) -> None:
    """The error message must not leak whether the email exists."""
    unknown_email_response = client.post(
        "/login",
        data={"email": "no-such-user@example.com", "password": "whatever123"},
        follow_redirects=False,
    )
    wrong_password_response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": "totally-wrong-password"},
        follow_redirects=False,
    )

    def extract_error(text: str) -> str:
        start = text.index('class="error"')
        end = text.index("</p>", start)
        return text[start:end]

    assert extract_error(unknown_email_response.text) == extract_error(wrong_password_response.text)
