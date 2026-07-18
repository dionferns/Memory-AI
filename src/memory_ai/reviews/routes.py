"""Review-session routes: global daily review, subject drill.

- ``GET /review`` -- the global daily review (issue #44): resolves the
  user's timezone + daily cap, calls ``get_due_cards(subject_id=None,
  limit=cap, as_of=<tz boundary>)``, and renders the review shell showing
  the first due card's front (or the "all caught up" empty state).
- ``GET /review/subjects/{subject_id}`` -- the per-subject drill (issue
  #48): calls the *same* ``get_due_cards`` with ``subject_id=<id>,
  limit=None`` (uncapped), so it cannot drift from the global view.

Every route resolves the user's ``UserSettings`` row for
``timezone``/``daily_review_cap`` and calls ticket 08's ``today_in_tz`` to
compute the "due today" boundary -- no timezone math happens here beyond
that single call, matching ticket 09 decision #7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import Subject, User, UserSettings
from memory_ai.reviews.queries import get_due_cards
from memory_ai.scheduling import today_in_tz

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_GLOBAL_EMPTY_MESSAGE = "You're all caught up!"
_SUBJECT_EMPTY_MESSAGE = "Nothing due in this subject right now."


def _get_owned_subject(db: Session, subject_id: int, user_id: int) -> Subject:
    """Fetch a subject scoped to ``user_id``, or raise a plain 404.

    Mirrors ``hierarchy.py``'s helper of the same name/behavior (ticket 04
    decision #4): a subject that doesn't exist and one that exists but
    belongs to another user are indistinguishable to the caller.
    """
    subject = db.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if subject is None:
        raise HTTPException(status_code=404)
    return subject


def _get_user_settings(db: Session, user_id: int) -> UserSettings:
    return db.execute(select(UserSettings).where(UserSettings.user_id == user_id)).scalar_one()


def _resolve_boundary(user_settings: UserSettings) -> tuple[datetime, ZoneInfo]:
    """Resolve "now" and the user's tz, per ticket 09 decision #7.

    Returns ``(now_utc, tz)``; callers derive the "due today" boundary date
    via ``today_in_tz(now_utc, tz)``.
    """
    return datetime.now(UTC), ZoneInfo(user_settings.timezone)


@router.get("/review")
def review_global(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the global daily review: first due card (capped) or empty state."""
    user_settings = _get_user_settings(db, user.id)
    now_utc, tz = _resolve_boundary(user_settings)
    boundary = today_in_tz(now_utc, tz)

    cards = get_due_cards(
        db, user.id, subject_id=None, limit=user_settings.daily_review_cap, as_of=boundary
    )
    card = cards[0] if cards else None

    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "heading": "Daily Review",
            "card": card,
            "scope": "global",
            "subject_id": None,
            "empty_message": _GLOBAL_EMPTY_MESSAGE,
        },
    )


@router.get("/review/subjects/{subject_id}")
def review_subject(
    subject_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the per-subject drill: every due card in the subject, uncapped.

    Calls the exact same ``get_due_cards`` function the global route calls
    (ticket 09 decision #4) -- ``subject_id=<id>, limit=None`` -- so this
    view cannot drift from the global one; no separate/duplicated query.
    """
    subject = _get_owned_subject(db, subject_id, user.id)
    user_settings = _get_user_settings(db, user.id)
    now_utc, tz = _resolve_boundary(user_settings)
    boundary = today_in_tz(now_utc, tz)

    cards = get_due_cards(db, user.id, subject_id=subject.id, limit=None, as_of=boundary)
    card = cards[0] if cards else None

    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "heading": f"Review: {subject.name}",
            "card": card,
            "scope": "subject",
            "subject_id": subject.id,
            "empty_message": _SUBJECT_EMPTY_MESSAGE,
        },
    )
