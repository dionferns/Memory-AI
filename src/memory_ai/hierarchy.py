"""Subject (and, from ticket 04 slice #86 onward, folder) CRUD routes.

Every route here depends on ticket 03's ``current_user`` dependency and
scopes its query to that user: subjects are filtered directly on
``Subject.user_id``; folders (added in a later slice) are filtered via a
join to their owning subject's ``user_id``, since ``folders`` carries no
``user_id`` column of its own. A resource that doesn't exist *or* belongs to
another user always returns 404 -- never 403 -- so an id's ownership can
never be probed for (ticket 04 decision #4).

Create/rename return just the changed HTML fragment; delete returns an
empty body with the row removed client-side via the control's own
``hx-target``/``hx-swap="outerHTML"`` (ticket 04 decision #6).
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import Subject, User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Ticket 04 decision #1: required, trimmed, empty/whitespace-only rejected,
# max 200 characters, no other character restrictions.
_MAX_NAME_LENGTH = 200


def _clean_name(raw: str) -> tuple[str, str | None]:
    """Trim ``raw`` and validate it per ticket 04 decision #1.

    Returns ``(trimmed_name, error_message)``; ``error_message`` is ``None``
    when the name is valid.
    """
    trimmed = raw.strip()
    if not trimmed:
        return trimmed, "Name is required."
    if len(trimmed) > _MAX_NAME_LENGTH:
        return trimmed, f"Name must be {_MAX_NAME_LENGTH} characters or fewer."
    return trimmed, None


def _get_owned_subject(db: Session, subject_id: int, user_id: int) -> Subject:
    """Fetch a subject scoped to ``user_id``, or raise 404.

    A subject that doesn't exist and a subject that exists but belongs to
    another user are indistinguishable to the caller -- both raise a plain
    404 (ticket 04 decision #4).
    """
    subject = db.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if subject is None:
        raise HTTPException(status_code=404)
    return subject


@router.get("/subjects")
def subjects_page(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the full ``/subjects`` hierarchy page for the current user."""
    subjects = (
        db.execute(
            select(Subject)
            .where(Subject.user_id == user.id)
            .order_by(Subject.created_at.asc(), Subject.id.asc())
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(request, "subjects.html", {"subjects": subjects})


@router.post("/subjects")
def create_subject(
    request: Request,
    name: str = Form(...),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Create a subject owned by the current user.

    On validation failure, re-renders just the create-form fragment with an
    inline error (ticket 04 decision #12). On success, returns the new
    subject's row fragment (appended out-of-band to the list) plus a fresh
    create form.
    """
    trimmed, error = _clean_name(name)
    if error:
        return templates.TemplateResponse(
            request,
            "_create_subject_form.html",
            {"error": error, "name": name},
        )

    subject = Subject(user_id=user.id, name=trimmed, created_at=datetime.now(UTC))
    db.add(subject)
    db.commit()

    return templates.TemplateResponse(
        request,
        "_create_subject_result.html",
        {"subject": subject},
    )


@router.get("/subjects/{subject_id}")
def view_subject(
    subject_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Return a subject's display-mode row fragment (used by rename-cancel)."""
    subject = _get_owned_subject(db, subject_id, user.id)
    return templates.TemplateResponse(request, "_subject_row.html", {"subject": subject})


@router.get("/subjects/{subject_id}/edit")
def edit_subject_form(
    subject_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Swap a subject's display row for its inline rename form."""
    subject = _get_owned_subject(db, subject_id, user.id)
    return templates.TemplateResponse(request, "_subject_edit_row.html", {"subject": subject})


@router.patch("/subjects/{subject_id}")
def rename_subject(
    subject_id: int,
    request: Request,
    name: str = Form(...),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Rename a subject owned by the current user.

    On validation failure, re-renders the inline edit form with an error
    (ticket 04 decision #12). On success, swaps back to the display row.
    """
    subject = _get_owned_subject(db, subject_id, user.id)

    trimmed, error = _clean_name(name)
    if error:
        return templates.TemplateResponse(
            request,
            "_subject_edit_row.html",
            {"subject": subject, "error": error, "name": name},
        )

    subject.name = trimmed
    db.commit()

    return templates.TemplateResponse(request, "_subject_row.html", {"subject": subject})


@router.delete("/subjects/{subject_id}")
def delete_subject(
    subject_id: int,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Delete a subject owned by the current user.

    Issues nothing more than a ``DELETE`` on the subject row -- cascading
    removal of its folders (and, from ticket 05 on, sources/cards/reviews
    beneath them) is handled entirely by the DB's ``ON DELETE CASCADE``
    foreign keys (ticket 04 decision #13). Returns an empty body; the client
    removes the row itself via its own ``hx-target``/``hx-swap="outerHTML"``.
    """
    subject = _get_owned_subject(db, subject_id, user.id)
    db.delete(subject)
    db.commit()
    return Response(status_code=200)
