from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, current_user, hash_password, verify_password
from memory_ai.config import get_settings
from memory_ai.database import get_db
from memory_ai.hierarchy import router as hierarchy_router
from memory_ai.models import User, UserSettings

app = FastAPI(title="Memory AI")
app.include_router(hierarchy_router)

# Sane defaults applied to every new user's `user_settings` row at
# registration (ticket 03 decision #13 / PRD user story #5).
_DEFAULT_DAILY_REVIEW_CAP = 20
_DEFAULT_TIMEZONE = "UTC"

_MIN_PASSWORD_LENGTH = 8

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
