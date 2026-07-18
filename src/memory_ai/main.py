from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import available_timezones

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, current_user, hash_password, verify_password
from memory_ai.config import get_settings
from memory_ai.database import get_db
from memory_ai.hierarchy import router as hierarchy_router
from memory_ai.models import User, UserSettings
from memory_ai.quiz import router as quiz_router

app = FastAPI(title="Memory AI")
app.include_router(hierarchy_router)
app.include_router(quiz_router)

# Serves src/memory_ai/static/quiz.js: the client-side Next/Previous/Show
# Answer navigation for notes-quiz mode (ticket 12, issue #65). No other
# static assets exist yet -- this mount exists for that one file.
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Sane defaults applied to every new user's `user_settings` row at
# registration (ticket 03 decision #13 / PRD user story #5).
_DEFAULT_DAILY_REVIEW_CAP = 20
_DEFAULT_TIMEZONE = "UTC"

_MIN_PASSWORD_LENGTH = 8

# `daily_review_cap` bounds (ticket 10 decision #1): integer, 1..500 inclusive.
_MIN_DAILY_REVIEW_CAP = 1
_MAX_DAILY_REVIEW_CAP = 500

# Sorted once at import time -- `zoneinfo.available_timezones()` is a set with
# no defined order, and both the `<select>` render and validation need the
# same underlying set (ticket 10 decision #2/#7).
_VALID_TIMEZONES = frozenset(available_timezones())
_SORTED_TIMEZONES = sorted(_VALID_TIMEZONES)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(user: User = Depends(current_user)) -> dict[str, str]:  # noqa: B008
    """Trivial protected demo route proving out the ``current_user`` dependency.

    Later tickets (04+) import and depend on the same ``current_user``
    dependency for their real protected routes; this route exists purely to
    exercise it end-to-end.
    """
    return {"email": user.email}


@app.get("/login")
def login_form(request: Request) -> Response:
    """Render the Jinja + HTMX login form."""
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Verify credentials and, on success, set a signed JWT session cookie.

    On failure (unknown email or wrong password), re-renders the login form
    partial with a generic error so an HTMX partial swap can show it inline,
    without revealing whether the email exists.
    """
    user = db.query(User).filter(User.email == email).one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "_login_form.html",
            {"error": "Invalid email or password.", "email": email},
        )

    settings = get_settings()
    token = create_access_token(user.id)
    max_age = settings.access_token_expire_minutes * 60

    redirect_target = "/"
    response: Response
    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=200, headers={"HX-Redirect": redirect_target})
    else:
        response = RedirectResponse(url=redirect_target, status_code=303)

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=max_age,
    )
    return response


@app.get("/register")
def register_form(request: Request) -> Response:
    """Render the Jinja + HTMX registration form."""
    return templates.TemplateResponse(request, "register.html", {})


@app.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Create a new user + default settings row, then auto-log them in.

    Password length is checked before touching the DB. The duplicate-email
    case is handled by attempting the insert and catching the unique
    constraint's ``IntegrityError`` (ticket 03 decision #9) rather than a
    pre-check ``SELECT``, avoiding a check-then-insert race. The `users` and
    `user_settings` rows are inserted in a single transaction (decision #13).
    """
    if len(password) < _MIN_PASSWORD_LENGTH:
        return templates.TemplateResponse(
            request,
            "_register_form.html",
            {
                "error": "Password must be at least 8 characters long.",
                "email": email,
            },
        )

    now = datetime.now(UTC)
    user = User(email=email, password_hash=hash_password(password), created_at=now)

    # Scope the attempted insert in its own SAVEPOINT (via `begin_nested`)
    # rather than calling a bare `db.rollback()` on failure: that would
    # unwind the *whole* session transaction, which is too broad when `db`
    # is itself already wrapped in an outer transaction (as ticket 21's test
    # harness does per-test). Rolling back just this SAVEPOINT leaves any
    # outer transaction untouched either way.
    nested = db.begin_nested()
    try:
        db.add(user)
        db.flush()
        db.add(
            UserSettings(
                user_id=user.id,
                daily_review_cap=_DEFAULT_DAILY_REVIEW_CAP,
                timezone=_DEFAULT_TIMEZONE,
                created_at=now,
                updated_at=now,
            )
        )
    except IntegrityError:
        nested.rollback()
        return templates.TemplateResponse(
            request,
            "_register_form.html",
            {
                "error": "That email is already registered.",
                "email": email,
            },
        )
    else:
        nested.commit()

    db.commit()

    settings = get_settings()
    token = create_access_token(user.id)
    max_age = settings.access_token_expire_minutes * 60

    redirect_target = "/"
    response: Response
    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=200, headers={"HX-Redirect": redirect_target})
    else:
        response = RedirectResponse(url=redirect_target, status_code=303)

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=max_age,
    )
    return response


@app.post("/logout")
def logout(request: Request) -> Response:
    """Clear the ``access_token`` session cookie and redirect to ``/login``.

    No server-side revocation store exists in v1 (per the ticket-03
    decisions) -- this simply clears the cookie so the browser stops sending
    it. A "logged out" token remains cryptographically valid until its
    ``exp``, which is an accepted, bounded limitation.
    """
    settings = get_settings()
    redirect_target = "/login"

    response: Response
    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=200, headers={"HX-Redirect": redirect_target})
    else:
        response = RedirectResponse(url=redirect_target, status_code=303)

    # Attributes must match those used in `set_cookie` at login time
    # (httponly/samesite/secure/path) for the browser to actually clear it.
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
    )
    return response


@app.get("/settings")
def settings_form(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the settings page with the logged-in user's persisted values.

    Reuses ticket 03's ``current_user`` dependency for auth (no new auth
    logic) -- an unauthenticated request is redirected to ``/login`` by that
    dependency before this handler body ever runs.
    """
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).one()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "daily_review_cap": user_settings.daily_review_cap,
            "timezone": user_settings.timezone,
            "timezones": _SORTED_TIMEZONES,
        },
    )


def _validate_daily_review_cap(raw: str) -> tuple[int | None, str | None]:
    """Parse+validate the submitted cap string.

    Returns ``(parsed_value, None)`` on success or ``(None, error_message)``
    on failure. Non-integer input (including floats like "20.5") and
    out-of-range integers are both rejected (ticket 10 decision #1).
    """
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None, "Daily review cap must be a whole number."

    if not (_MIN_DAILY_REVIEW_CAP <= parsed <= _MAX_DAILY_REVIEW_CAP):
        return None, (
            f"Daily review cap must be between {_MIN_DAILY_REVIEW_CAP} and {_MAX_DAILY_REVIEW_CAP}."
        )

    return parsed, None


@app.post("/settings")
def update_settings(
    request: Request,
    daily_review_cap: str = Form(...),
    timezone: str = Form(...),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Validate both fields, then persist both together or neither.

    Per ticket 10 decision #4, an invalid submission rejects the *whole*
    submission -- no UPDATE is issued for either field, even if the other
    field on its own would have been valid. Both validations run before any
    DB write is attempted, so there is no partial-apply window.
    """
    parsed_cap, cap_error = _validate_daily_review_cap(daily_review_cap)

    timezone_error: str | None = None
    if timezone not in _VALID_TIMEZONES:
        timezone_error = "Please select a valid timezone."

    if cap_error is not None or timezone_error is not None:
        return templates.TemplateResponse(
            request,
            "_settings_form.html",
            {
                "daily_review_cap": daily_review_cap,
                "timezone": timezone,
                "timezones": _SORTED_TIMEZONES,
                "cap_error": cap_error,
                "timezone_error": timezone_error,
            },
        )

    # Both fields passed validation here. `_validate_daily_review_cap` only
    # ever returns `(value, None)` on success or `(None, error)` on failure,
    # so `cap_error is None` guarantees `parsed_cap` is not None.
    assert parsed_cap is not None

    db.execute(
        update(UserSettings)
        .where(UserSettings.user_id == user.id)
        .values(daily_review_cap=parsed_cap, timezone=timezone, updated_at=datetime.now(UTC))
    )
    db.commit()

    return templates.TemplateResponse(
        request,
        "_settings_form.html",
        {
            "daily_review_cap": parsed_cap,
            "timezone": timezone,
            "timezones": _SORTED_TIMEZONES,
            "success": True,
        },
    )
