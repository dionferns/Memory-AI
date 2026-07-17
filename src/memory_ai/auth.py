"""Password hashing and JWT issuance/verification helpers for the auth flow.

``create_access_token`` is deliberately a standalone, importable function (not
inlined in the ``/login`` route) so ticket 03's registration slice can reuse it
for auto-login after signup, per the ticket-03 decisions.

``current_user`` is the route dependency later tickets (04+) import to enforce
"is this a valid session" on their protected routes; the per-resource
ownership scoping is out of scope here (see ticket 03 PRD).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from memory_ai.config import get_settings
from memory_ai.database import get_db
from memory_ai.models import User

JWT_ALGORITHM = "HS256"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _unauthenticated(request: Request) -> HTTPException:
    """Build the "not logged in" response for a protected route.

    HTMX partial requests (``HX-Request`` header present) get a 401 with an
    ``HX-Redirect`` header so HTMX follows it client-side; full-page requests
    get a normal 302 redirect via the ``Location`` header. Per ticket-03
    decision #10.
    """
    if request.headers.get("HX-Request") == "true":
        return HTTPException(status_code=401, headers={"HX-Redirect": "/login"})
    return HTTPException(status_code=302, headers={"Location": "/login"})


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


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate ``token``, checking signature and ``exp``.

    Raises ``jwt.PyJWTError`` (or a subclass, e.g. ``jwt.ExpiredSignatureError``
    or ``jwt.InvalidSignatureError``) on any failure. Callers that want a
    uniform "unauthenticated" outcome should catch ``jwt.PyJWTError``.
    """
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    return payload


def current_user(
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
) -> User:
    """FastAPI dependency: resolve the logged-in ``User`` from the session cookie.

    Reads the ``access_token`` cookie, validates it (signature + ``exp``), and
    loads the ``User`` row by the token's ``sub`` claim. On any failure
    (missing cookie, invalid signature, expired token, or the user no longer
    existing), raises the appropriate "unauthenticated" ``HTTPException`` per
    ``_unauthenticated`` above, rather than returning ``None`` -- this keeps
    every downstream protected route's happy path free of null-checks.
    """
    token = request.cookies.get("access_token")
    if token is None:
        raise _unauthenticated(request)

    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise _unauthenticated(request) from None

    user_id_claim = payload.get("sub")
    if user_id_claim is None:
        raise _unauthenticated(request)

    try:
        user_id = int(user_id_claim)
    except (TypeError, ValueError):
        raise _unauthenticated(request) from None

    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        raise _unauthenticated(request)

    return user
