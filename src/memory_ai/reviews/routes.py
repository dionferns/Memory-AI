"""Review-session routes: global daily review, subject drill, grading.

- ``GET /review`` -- the global daily review (issue #44): resolves the
  user's timezone + daily cap, calls ``get_due_cards(subject_id=None,
  limit=cap, as_of=<tz boundary>)``, and renders the review shell showing
  the first due card's front (or the "all caught up" empty state).
- ``GET /review/subjects/{subject_id}`` -- the per-subject drill (issue
  #48): calls the *same* ``get_due_cards`` with ``subject_id=<id>,
  limit=None`` (uncapped), so it cannot drift from the global view.
- ``GET /review/{card_id}/reveal`` -- swaps a card's front-only partial for
  its back + the four grade buttons (issue #51's "Show answer" step). Pure
  read, no scheduling mutation.
- ``POST /review/grade/{card_id}`` -- grades a card (issue #51): validates
  the grade/scope, calls ticket 08's ``apply_grade_to_card`` persistence
  helper (no SM-2 math duplicated here), commits, then re-runs
  ``get_due_cards`` for the originating scope (carried as form fields) and
  returns the next due card's front partial or the empty-state partial,
  HTMX-swapped into the same ``#review-card`` container. This re-query is
  what makes the sync guarantee true by construction: grading in one scope
  is immediately reflected in the other, since both read through the same
  function.

Every route resolves the user's ``UserSettings`` row for
``timezone``/``daily_review_cap`` and calls ticket 08's ``today_in_tz`` to
compute the "due today" boundary -- no timezone math happens here beyond
that single call, matching ticket 09 decision #7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import Card, Folder, Source, Subject, User, UserSettings
from memory_ai.reviews.queries import get_due_cards
from memory_ai.scheduling import Grade, apply_grade_to_card, today_in_tz
from memory_ai.written_answer import (
    WrittenAnswerGrader,
    WrittenAnswerGradingError,
    get_written_answer_grader,
)

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_GLOBAL_EMPTY_MESSAGE = "You're all caught up!"
_SUBJECT_EMPTY_MESSAGE = "Nothing due in this subject right now."

_VALID_GRADES: frozenset[str] = frozenset({"again", "hard", "good", "easy"})
_VALID_SCOPES: frozenset[str] = frozenset({"global", "subject"})

# Outcome -> pre-selected grade mapping for written-answer mode (ticket 11
# decisions.md #10): perfect->easy, good->good, wrong->again. "Hard" is
# never auto-mapped -- it stays reachable only via manual override, per
# decisions.md #6.
_OUTCOME_TO_GRADE: dict[str, Grade] = {
    "perfect": "easy",
    "good": "good",
    "wrong": "again",
}

# Single, generic fallback notice shown for every written-answer grading
# failure (timeout, unparseable response, or out-of-enum outcome) -- ticket
# 11 decisions.md #3 collapses all three into one failure classification at
# the LLM boundary, so there is exactly one notice here too, not one per
# failure mode.
_WRITTEN_ANSWER_FAILURE_NOTICE = (
    "We couldn't grade your answer right now -- showing the card to grade manually instead."
)


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


def _get_owned_card(db: Session, card_id: int, user_id: int) -> Card:
    """Fetch a card scoped to ``user_id`` via the full ownership join chain.

    Mirrors ``cards.py``'s helper of the same name/behavior (ticket 07
    decision #11): a card that doesn't exist, or whose owning
    source/folder/subject belongs to another user, raises a plain 404 --
    never 403.
    """
    card = db.execute(
        select(Card)
        .join(Source, Card.source_id == Source.id)
        .join(Folder, Source.folder_id == Folder.id)
        .join(Subject, Folder.subject_id == Subject.id)
        .where(Card.id == card_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=404)
    return card


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
    written: str | None = None,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the global daily review: first due card (capped) or empty state.

    ``written`` is the per-review-session written-answer-mode toggle (ticket
    11 decisions.md #4) -- a plain query param, not a DB-backed setting, so
    it defaults to off on every fresh page load and is carried forward
    through subsequent card advances via a hidden form field (see
    ``grade_card``).
    """
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
            "written": written == "1",
        },
    )


@router.get("/review/subjects/{subject_id}")
def review_subject(
    subject_id: int,
    request: Request,
    written: str | None = None,
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
            "written": written == "1",
        },
    )


@router.get("/review/{card_id}/reveal")
def reveal_card(
    card_id: int,
    request: Request,
    scope: str = "global",
    subject_id: int | None = None,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Swap a card's front-only partial for its back + the 4 grade buttons.

    Pure read -- never mutates scheduling state. ``scope``/``subject_id``
    are echoed straight through from the front partial's query string so
    the grade buttons rendered next know which scope to re-query after
    grading.
    """
    if scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422)
    if scope == "subject":
        if subject_id is None:
            raise HTTPException(status_code=422)
        _get_owned_subject(db, subject_id, user.id)

    card = _get_owned_card(db, card_id, user.id)

    return templates.TemplateResponse(
        request,
        "_review_card_back.html",
        {"card": card, "scope": scope, "subject_id": subject_id},
    )


@router.post("/review/grade/{card_id}")
def grade_card(
    card_id: int,
    request: Request,
    grade: str = Form(...),
    scope: str = Form(...),
    subject_id: int | None = Form(None),
    written: str | None = Form(None),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Grade a card, then advance to the next due card in the same scope.

    Validates ``grade``/``scope`` (and card/subject ownership) before ever
    touching scheduling state, so an invalid request never leaves a partial
    mutation behind. Calls ticket 08's ``apply_grade_to_card`` for the
    actual SM-2 math -- no scheduling logic is duplicated here -- then
    re-runs the *same* ``get_due_cards`` used by the GET routes for the
    originating scope, which is what makes the sync guarantee (grading in
    one view is immediately reflected in the other) true by construction.
    Editing/deleting a card's front/back content (ticket 07's concern) is
    entirely untouched by this route -- only scheduling fields are written.
    """
    if grade not in _VALID_GRADES:
        raise HTTPException(status_code=422)
    if scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422)
    if scope == "subject" and subject_id is None:
        raise HTTPException(status_code=422)

    card = _get_owned_card(db, card_id, user.id)
    if scope == "subject":
        assert subject_id is not None
        _get_owned_subject(db, subject_id, user.id)

    user_settings = _get_user_settings(db, user.id)
    now_utc, tz = _resolve_boundary(user_settings)

    apply_grade_to_card(db, card, cast(Grade, grade), now_utc, tz)
    db.commit()

    boundary = today_in_tz(now_utc, tz)
    if scope == "subject":
        assert subject_id is not None
        next_cards = get_due_cards(db, user.id, subject_id=subject_id, limit=None, as_of=boundary)
        empty_message = _SUBJECT_EMPTY_MESSAGE
    else:
        next_cards = get_due_cards(
            db, user.id, subject_id=None, limit=user_settings.daily_review_cap, as_of=boundary
        )
        empty_message = _GLOBAL_EMPTY_MESSAGE

    next_card = next_cards[0] if next_cards else None
    if next_card is None:
        return templates.TemplateResponse(
            request,
            "_review_empty.html",
            {"scope": scope, "subject_id": subject_id, "empty_message": empty_message},
        )

    # Written-answer mode (ticket 11) is carried forward from a hidden form
    # field, not re-derived -- this is what keeps the per-session toggle "on"
    # across card advances regardless of whether the *previous* card was
    # graded via the LLM path or the fallback path. `apply_grade_to_card`
    # above is completely unaffected by this flag; it only changes which
    # front partial gets rendered next (ticket 11 decisions.md #9: this
    # route's grading behavior is unaware written-answer mode exists).
    front_template = (
        "_review_card_front_written.html" if written == "1" else "_review_card_front.html"
    )
    return templates.TemplateResponse(
        request,
        front_template,
        {"card": next_card, "scope": scope, "subject_id": subject_id},
    )


@router.post("/review/{card_id}/answer")
def submit_written_answer(
    card_id: int,
    request: Request,
    user_answer: str = Form(...),
    scope: str = Form(...),
    subject_id: int | None = Form(None),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    grader: WrittenAnswerGrader = Depends(get_written_answer_grader),  # noqa: B008
) -> Response:
    """Grade a written answer via the LLM boundary and reveal the result (ticket 11, issue #69).

    This is *not* a second grading/persistence path: it never calls
    ``apply_grade_to_card`` and never mutates any scheduling state -- it only
    calls ticket 11's ``WrittenAnswerGrader`` boundary and renders one of two
    partials:

    - On success: ``_review_card_graded.html``, which reveals the gold
      answer, the outcome badge, the feedback text, and the same four grade
      buttons ``_review_card_back.html`` renders, with the mapped button
      (decisions.md #10) pre-highlighted. All four buttons remain clickable
      (decisions.md #6) -- clicking a non-pre-selected one simply changes
      the selection before the user's next POST to ``/review/grade/{card_id}``,
      ticket 09's existing grading route, which is what actually persists a
      grade.
    - On any grading failure (network/timeout, unparseable response, or an
      out-of-enum outcome -- all pre-classified identically as
      ``WrittenAnswerGradingError`` by the LLM boundary, decisions.md #3):
      ``_review_card_back.html`` (the same plain flip-and-grade partial
      ticket 09's "Show answer" reveals), with no button pre-selected and a
      brief inline notice, so the review session continues normally.
    """
    if scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422)
    if scope == "subject":
        if subject_id is None:
            raise HTTPException(status_code=422)
        _get_owned_subject(db, subject_id, user.id)

    card = _get_owned_card(db, card_id, user.id)

    try:
        outcome = grader.grade(card.front, card.back, user_answer)
    except WrittenAnswerGradingError:
        return templates.TemplateResponse(
            request,
            "_review_card_back.html",
            {
                "card": card,
                "scope": scope,
                "subject_id": subject_id,
                "written": True,
                "written_notice": _WRITTEN_ANSWER_FAILURE_NOTICE,
            },
        )

    mapped_grade = _OUTCOME_TO_GRADE[outcome.outcome]
    return templates.TemplateResponse(
        request,
        "_review_card_graded.html",
        {
            "card": card,
            "scope": scope,
            "subject_id": subject_id,
            "outcome": outcome.outcome,
            "feedback": outcome.feedback,
            "mapped_grade": mapped_grade,
        },
    )
