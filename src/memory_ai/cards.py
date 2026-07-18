"""Card listing routes: per-source and per-folder (ticket 07, issue #72).

- ``GET /sources/{source_id}/cards`` -- every card generated from a source,
  the primary entry point right after ticket 06's "Convert to Flashcards"
  completes.
- ``GET /folders/{folder_id}/cards`` -- every card across every source
  within a folder, an aggregate browse view.

Both routes resolve ownership through the ``user -> subject -> folder ->
source -> card`` join chain and return a plain 404 (never 403) for a
resource that doesn't exist or isn't owned by the requesting user, matching
ticket 04's established pattern. Both order by ``created_at`` ascending
(ties broken by ``id`` for a stable order); no pagination in v1.

This module also builds the shared ``_card_row.html`` display partial that
later issues (#75 inline edit, #77 inline delete) reuse so their HTMX swaps
target the same markup.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
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
