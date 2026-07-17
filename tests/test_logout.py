"""HTTP-seam tests for the logout flow: ``POST /logout``.

Seam: FastAPI ``TestClient`` + real Postgres via ticket 21/02's shared test
harness (``db_session``/``client`` fixtures in ``conftest.py``), per the
ticket-03 testing decisions.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import hash_password
from memory_ai.models import User

TEST_EMAIL = "logout-seam-test-user@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


def _make_user(db_session: Session) -> User:
    user = User(
        email=TEST_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client: TestClient, db_session: Session) -> None:
    """Log in via the real /login route to obtain a session cookie."""
    _make_user(db_session)
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.cookies.get("access_token") is not None


def test_logout_clears_cookie_and_redirects_to_login(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie_header
    # An expired/zero Max-Age (or a past Expires date) tells the browser to
    # delete the cookie immediately.
    assert "max-age=0" in set_cookie_header.lower()


def test_logout_clears_cookie_with_matching_attributes(
    client: TestClient, db_session: Session
) -> None:
    """The clearing Set-Cookie must match login's attributes so the browser
    recognizes it as the same cookie and actually removes it."""
    _login(client, db_session)

    response = client.post("/logout", follow_redirects=False)

    set_cookie_header = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header
    # Secure must NOT be set in the (non-production) test environment.
    assert "secure" not in set_cookie_header


def test_logout_via_htmx_returns_hx_redirect_header_and_clears_cookie(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)

    response = client.post(
        "/logout",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/login"
    assert "max-age=0" in response.headers.get("set-cookie", "").lower()


def test_logout_without_a_session_still_redirects_to_login(client: TestClient) -> None:
    """Logging out with no cookie present is a no-op that still redirects."""
    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_access_token_from_before_logout_is_gone_from_client_jar(
    client: TestClient, db_session: Session
) -> None:
    """After logout, the TestClient's cookie jar no longer carries a (valid,
    non-expired) access_token -- mirroring a real browser dropping it."""
    _login(client, db_session)
    assert client.cookies.get("access_token") is not None

    client.post("/logout", follow_redirects=False)

    assert client.cookies.get("access_token") is None
