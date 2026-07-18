"""Card CRUD routes: view, inline edit, inline delete.

- ``GET /sources/{source_id}/cards`` -- every card generated from a source,
  the primary entry point right after ticket 06's "Convert to Flashcards"
  completes (issue #72).
- ``GET /folders/{folder_id}/cards`` -- every card across every source
  within a folder, an aggregate browse view (issue #72).
- ``GET /cards/{card_id}/edit`` + ``PATCH /cards/{card_id}`` -- inline
  front/back edit (issue #75), reusing the shared ``_card_row.html`` display
  partial from issue #72 so the edit swap targets the same markup. The
  handler writes only ``front``/``back``; every SM-2 scheduling column
  (``ease_factor``, ``interval_days``, ``repetitions``, ``due_date``,
  ``last_reviewed_at``) is never part of the update payload or touched by
  this route.
- ``GET /cards/{card_id}/delete-confirm`` + ``DELETE /cards/{card_id}`` --
  inline two-step delete confirm (issue #77, no modal/native ``confirm()``),
  again reusing the shared ``_card_row.html`` partial as the "cancel" swap
  target. The DELETE issues nothing but a plain row delete; ``reviews`` rows
  cascade via ticket 02's DB-level ``ON DELETE CASCADE`` FK, no app-level
  cleanup code.

Every route resolves ownership through the ``user -> subject -> folder ->
source -> card`` join chain and returns a plain 404 (never 403) for a
resource that doesn't exist or isn't owned by the requesting user, matching
ticket 04's established pattern. Listing routes order by ``created_at``
ascending (ties broken by ``id`` for a stable order); no pagination in v1.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import Card, Folder, Source, Subject, User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_owned_source(db: Session, source_id: int, user_id: int) -> Source:
    """Fetch a source scoped to ``user_id`` via a join through folder -> subject.

    A source that doesn't exist, or whose owning folder/subject belongs to
    another user, raises a plain 404 (ticket 04 decision #4).
    """
    source = db.execute(
        select(Source)
        .join(Folder, Source.folder_id == Folder.id)
        .join(Subject, Folder.subject_id == Subject.id)
        .where(Source.id == source_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404)
    return source


def _get_owned_folder(db: Session, folder_id: int, user_id: int) -> Folder:
    """Fetch a folder scoped to ``user_id`` via a join to its owning subject."""
    folder = db.execute(
        select(Folder)
        .join(Subject, Folder.subject_id == Subject.id)
        .where(Folder.id == folder_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404)
    return folder


def _get_owned_card(db: Session, card_id: int, user_id: int) -> Card:
    """Fetch a card scoped to ``user_id`` via the full ownership join chain.

    Joins ``cards -> sources -> folders -> subjects`` and filters on the
    subject's ``user_id``. A card that doesn't exist, or whose owning
    source/folder/subject belongs to another user, raises a plain 404 --
    never 403 -- so another user's card id can't be confirmed to exist
    (ticket 07 decision #11).
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


def _list_cards_for_source(db: Session, source_id: int) -> list[Card]:
    return list(
        db.execute(
            select(Card)
            .where(Card.source_id == source_id)
            .order_by(Card.created_at.asc(), Card.id.asc())
        )
        .scalars()
        .all()
    )


def _list_cards_for_folder(db: Session, folder_id: int) -> list[Card]:
    # `Card.folder_id` is a denormalized column (ticket 02), so the
    # per-folder aggregate is a direct filter -- no join through `sources`
    # needed to gather every card across every source in the folder.
    return list(
        db.execute(
            select(Card)
            .where(Card.folder_id == folder_id)
            .order_by(Card.created_at.asc(), Card.id.asc())
        )
        .scalars()
        .all()
    )


@router.get("/sources/{source_id}/cards")
def list_source_cards(
    source_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render every card generated from a source, ordered oldest-first."""
    source = _get_owned_source(db, source_id, user.id)
    cards = _list_cards_for_source(db, source.id)
    return templates.TemplateResponse(
        request,
        "cards_source.html",
        {"source": source, "cards": cards},
    )


@router.get("/folders/{folder_id}/cards")
def list_folder_cards(
    folder_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render every card across every source within a folder, oldest-first."""
    folder = _get_owned_folder(db, folder_id, user.id)
    cards = _list_cards_for_folder(db, folder.id)
    return templates.TemplateResponse(
        request,
        "cards_folder.html",
        {"folder": folder, "cards": cards},
    )


_EMPTY_FIELD_ERROR = "Front and back are both required."


def _clean_card_field(raw: str) -> tuple[str, str | None]:
    """Trim ``raw`` and reject if empty/whitespace-only after trimming.

    Per ticket 07 decision #3/#4: both `front` and `back` are required
    (empty/whitespace-only rejected) with no app-level max length.
    """
    trimmed = raw.strip()
    if not trimmed:
        return trimmed, _EMPTY_FIELD_ERROR
    return trimmed, None


@router.get("/cards/{card_id}")
def view_card(
    card_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Return a card's display-mode row fragment.

    Exists in this issue purely as the shared display fragment other cards
    routes render/return to; later issues (#75 edit, #77 delete) reuse it as
    the "cancel"/settle swap target for their own inline partials.
    """
    card = _get_owned_card(db, card_id, user.id)
    return templates.TemplateResponse(request, "_card_row.html", {"card": card})


@router.get("/cards/{card_id}/edit")
def edit_card_form(
    card_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Swap a card's display row for its inline front/back edit form."""
    card = _get_owned_card(db, card_id, user.id)
    return templates.TemplateResponse(request, "_card_edit_row.html", {"card": card})


@router.patch("/cards/{card_id}")
def update_card(
    card_id: int,
    request: Request,
    # Both default to "" rather than `Form(...)` (required): Starlette's
    # form parser treats a genuinely-empty submitted value as an absent
    # field, so a required `Form(...)` 422s with a raw FastAPI validation
    # error before this handler ever runs -- bypassing the inline
    # validation error `_clean_card_field` is meant to render. Defaulting
    # to "" lets a truly-empty submission reach that check like a
    # whitespace-only one already does.
    front: str = Form(""),
    back: str = Form(""),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Update a card's `front`/`back` only.

    Never touches `ease_factor`, `interval_days`, `repetitions`, `due_date`,
    or `last_reviewed_at` -- those SM-2 scheduling columns are simply absent
    from this handler's write path (ticket 07 decision #1/#2). On validation
    failure, re-renders the inline edit form with an error and leaves the
    card unchanged.
    """
    card = _get_owned_card(db, card_id, user.id)

    trimmed_front, front_error = _clean_card_field(front)
    trimmed_back, back_error = _clean_card_field(back)
    error = front_error or back_error
    if error:
        return templates.TemplateResponse(
            request,
            "_card_edit_row.html",
            {"card": card, "error": error, "front": front, "back": back},
        )

    card.front = trimmed_front
    card.back = trimmed_back
    db.commit()

    return templates.TemplateResponse(request, "_card_row.html", {"card": card})


@router.get("/cards/{card_id}/delete-confirm")
def delete_confirm_card(
    card_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Swap a card's display row for an inline "Confirm delete? / Cancel" pair.

    No modal, no native JS `confirm()` -- an inline two-step partial swap
    (ticket 07 decision #6/#7). "Cancel" swaps back to the display row via
    `GET /cards/{card_id}` without ever calling the delete endpoint.
    """
    card = _get_owned_card(db, card_id, user.id)
    return templates.TemplateResponse(request, "_card_delete_confirm.html", {"card": card})


@router.delete("/cards/{card_id}")
def delete_card(
    card_id: int,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Delete a card owned by the current user.

    Issues nothing more than a `DELETE` on the card row -- cascading removal
    of its `reviews` rows is handled entirely by the DB's `ON DELETE CASCADE`
    foreign key already established in ticket 02 (ticket 07 decision #8), no
    app-level cleanup code. Returns an empty body; the client removes the row
    itself via its own `hx-target`/`hx-swap="outerHTML"`.
    """
    card = _get_owned_card(db, card_id, user.id)
    db.delete(card)
    db.commit()
    return Response(status_code=200)
