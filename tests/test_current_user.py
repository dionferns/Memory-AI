"""HTTP-seam tests for the ``current_user`` dependency, exercised via ``GET /me``.

Seam: ticket 21's shared harness (``client`` fixture: FastAPI ``TestClient`` +
real Postgres testcontainer + per-test transaction rollback via ``db_session``).
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from memory_ai.auth import JWT_ALGORITHM, create_access_token, hash_password
from memory_ai.config import get_settings
from memory_ai.models import User

TEST_EMAIL = "current-user-seam-test@example.com"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    """Insert a single known user, scoped to the per-test rolled-back transaction."""
    user = User(
        email=TEST_EMAIL,
        password_hash=hash_password(TEST_PASSWORD),
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_valid_session_cookie_grants_access_and_loads_correct_user(
    client: TestClient, seeded_user: User
) -> None:
    token = create_access_token(seeded_user.id)
    client.cookies.set("access_token", token)

    response = client.get("/me", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {"email": TEST_EMAIL}


def test_missing_cookie_on_full_page_request_redirects_to_login(client: TestClient) -> None:
    response = client.get("/me", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_missing_cookie_on_htmx_request_returns_401_with_hx_redirect(
    client: TestClient,
) -> None:
    response = client.get("/me", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 401
    assert response.headers.get("hx-redirect") == "/login"


def test_expired_token_on_full_page_request_redirects_to_login(
    client: TestClient, seeded_user: User
) -> None:
    settings = get_settings()
    expired_payload = {
        "sub": str(seeded_user.id),
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    client.cookies.set("access_token", expired_token)

    response = client.get("/me", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_expired_token_on_htmx_request_returns_401_with_hx_redirect(
    client: TestClient, seeded_user: User
) -> None:
    settings = get_settings()
    expired_payload = {
        "sub": str(seeded_user.id),
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    client.cookies.set("access_token", expired_token)

    response = client.get("/me", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 401
    assert response.headers.get("hx-redirect") == "/login"


def test_tampered_signature_token_redirects_to_login(client: TestClient, seeded_user: User) -> None:
    token = create_access_token(seeded_user.id)
    tampered_token = token[:-1] + ("A" if token[-1] != "A" else "B")
    client.cookies.set("access_token", tampered_token)

    response = client.get("/me", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_user_not_found_for_valid_token_redirects_to_login(client: TestClient) -> None:
    """A well-signed, unexpired token for a nonexistent user id is rejected too."""
    token = create_access_token(user_id=999_999_999)
    client.cookies.set("access_token", token)

    response = client.get("/me", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
