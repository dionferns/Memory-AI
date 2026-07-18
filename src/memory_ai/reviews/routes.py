"""Review-session routes: global daily review.

- ``GET /review`` -- the global daily review (issue #44): resolves the
  user's timezone + daily cap, calls ``get_due_cards(subject_id=None,
  limit=cap, as_of=<tz boundary>)``, and renders the review shell showing
  the first due card's front (or the "all caught up" empty state).

Every route resolves the user's ``UserSettings`` row for
``timezone``/``daily_review_cap`` and calls ticket 08's ``today_in_tz`` to
compute the "due today" boundary -- no timezone math happens here beyond
that single call, matching ticket 09 decision #7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import User, UserSettings
from memory_ai.reviews.queries import get_due_cards
from memory_ai.scheduling import today_in_tz

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_GLOBAL_EMPTY_MESSAGE = "You're all caught up!"


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
