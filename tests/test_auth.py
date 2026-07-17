"""Unit tests for the JWT issuance and password-hashing helpers in ``memory_ai.auth``.

These exercise the helpers directly (no HTTP, no DB) so they're independent
of ticket 21's test harness landing.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import jwt
import pytest

from memory_ai.auth import JWT_ALGORITHM, create_access_token, hash_password, verify_password
from memory_ai.config import get_settings


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@localhost:5432/memory_ai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_access_token_contains_sub_and_exp() -> None:
    token = create_access_token(user_id=42)

    payload = jwt.decode(token, "unit-test-secret", algorithms=[JWT_ALGORITHM])

    assert payload["sub"] == "42"
    assert "exp" in payload


def test_create_access_token_sub_is_a_string() -> None:
    token = create_access_token(user_id=7)

    payload = jwt.decode(token, "unit-test-secret", algorithms=[JWT_ALGORITHM])

    assert isinstance(payload["sub"], str)
    assert payload["sub"] == "7"


def test_create_access_token_expiry_matches_setting() -> None:
    before = datetime.now(UTC)
    token = create_access_token(user_id=1)
    after = datetime.now(UTC)

    payload = jwt.decode(token, "unit-test-secret", algorithms=[JWT_ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

    settings = get_settings()
    # jwt truncates `exp` to whole seconds, so allow a 1s margin below the
    # (sub-second precision) lower bound.
    expected_min = before.timestamp() + settings.access_token_expire_minutes * 60 - 1
    expected_max = after.timestamp() + settings.access_token_expire_minutes * 60

    assert expected_min <= exp.timestamp() <= expected_max


def test_create_access_token_is_signed_hs256() -> None:
    token = create_access_token(user_id=1)

    header = jwt.get_unverified_header(token)

    assert header["alg"] == "HS256"


def test_create_access_token_rejects_wrong_secret() -> None:
    token = create_access_token(user_id=1)

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "wrong-secret", algorithms=[JWT_ALGORITHM])


def test_hash_password_and_verify_password_round_trip() -> None:
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password("correct-horse-battery-staple", hashed)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct-horse-battery-staple")

    assert not verify_password("wrong-password", hashed)


def test_hash_password_does_not_store_plaintext() -> None:
    hashed = hash_password("super-secret")

    assert hashed != "super-secret"
    assert hashed.startswith("$2b$")
