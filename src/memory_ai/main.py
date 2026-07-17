from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from memory_ai.auth import create_access_token, current_user, verify_password
from memory_ai.config import get_settings
from memory_ai.database import get_db
from memory_ai.models import User

app = FastAPI(title="Memory AI")

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
