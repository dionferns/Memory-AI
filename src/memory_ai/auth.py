"""Password hashing and JWT issuance helpers for the auth flow.

``create_access_token`` is deliberately a standalone, importable function (not
inlined in the ``/login`` route) so ticket 03's registration slice can reuse it
for auto-login after signup, per the ticket-03 decisions.
"""

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from memory_ai.config import get_settings

JWT_ALGORITHM = "HS256"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify ``plain_password`` against a stored bcrypt ``password_hash``."""
    return bool(_pwd_context.verify(plain_password, password_hash))


def hash_password(plain_password: str) -> str:
    """Hash ``plain_password`` with bcrypt (passlib default work factor)."""
    return str(_pwd_context.hash(plain_password))


def create_access_token(user_id: int) -> str:
    """Issue a signed HS256 JWT for ``user_id``.

    Claims are minimal: ``sub`` (the user id, as a string) and ``exp`` (now +
    ``settings.access_token_expire_minutes``). Signed with ``settings.jwt_secret``.
    """
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
