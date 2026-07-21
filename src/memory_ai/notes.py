"""Note-content pane: rendering a single source's text as Markdown.

Ticket 14 (see ``tickets/14-sidebar-navigation/PRD.md`` and ``decisions.md``,
decisions #2/#3/#4/#6/#7/#8/#15). Two routes:

- ``GET /sources/{source_id}/content`` -- the right-pane fragment, swapped
  in by the sidebar tree's HTMX click-to-select (``_folder_notes_list.html``).
- ``GET /sources/{source_id}`` -- the full ``/subjects`` shell (sidebar tree
  + this note pre-selected/expanded in the right pane), for direct
  navigation, a page refresh, or a shared link. Reuses the fragment above
  internally rather than duplicating its markup.

No new storage or per-format conversion step: ``sources.raw_text`` (ticket
05) is plain extracted text regardless of the original PDF/TXT/MD format,
and plain text is itself valid Markdown source, so every source is rendered
through the exact same ``markdown.markdown()`` call with no per-format
branching (decision #6). Rendering uses the ``markdown`` package's default
mode with no extensions enabled -- in particular no raw-HTML-passthrough
*extension* (e.g. ``md_in_html``) is turned on (decision #8); this is a
deliberate "sane default, not a full security review" per that decision,
not an accidental oversight.
"""

from __future__ import annotations

from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import Folder, Source, Subject, User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_owned_source(db: Session, source_id: int, user_id: int) -> Source:
    """Fetch a source scoped to ``user_id`` via a join through folder -> subject.

    Same ownership pattern as every other source-scoped route in this app
    (``quiz.py``, ``generation.py``, ``cards.py``): a source that doesn't
    exist, or whose owning folder/subject belongs to another user, raises a
    plain 404 -- never 403 -- so ownership can't be probed for (ticket 04
    decision #4 / ticket 14 decision #15).
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


def _list_sources_for_folder(db: Session, folder_id: int) -> list[Source]:
    return list(
        db.execute(
            select(Source)
            .where(Source.folder_id == folder_id)
            .order_by(Source.created_at.asc(), Source.id.asc())
        )
        .scalars()
        .all()
    )


def _load_subjects_tree(db: Session, user_id: int) -> list[Subject]:
    """Same subjects+folders eager-load shape as ``hierarchy.subjects_page``
    (ticket 04 decision #7 / ticket 14 decision #1) -- one query for
    subjects, one follow-up query for their folders, no eager-loaded
    sources."""
    return list(
        db.execute(
            select(Subject)
            .where(Subject.user_id == user_id)
            .options(selectinload(Subject.folders))
            .order_by(Subject.created_at.asc(), Subject.id.asc())
        )
        .scalars()
        .all()
    )


@router.get("/sources/{source_id}/content")
def source_content(
    source_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Return the right-pane fragment for a single note's rendered content.

    Swapped into ``#content-pane`` by the sidebar tree's note rows via
    ``hx-get`` + ``hx-push-url`` (decision #2); also reused internally by
    the full-page route below.
    """
    source = _get_owned_source(db, source_id, user.id)
    rendered_html = markdown.markdown(source.raw_text)
    return templates.TemplateResponse(
        request,
        "_note_content.html",
        {"source": source, "rendered_html": rendered_html},
    )


@router.get("/sources/{source_id}")
def view_source_page(
    source_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the full sidebar-tree shell with this note pre-selected.

    For direct navigation, a page refresh, or a shared link (decision #3):
    the tree is expanded down to the note's owning subject/folder (so it's
    visible without an extra click), that one folder's notes are rendered
    eagerly rather than through its usual lazy `GET /folders/{id}/notes`
    fetch (it's already known and needed for this response), and the right
    pane shows the same content fragment `GET /sources/{id}/content` would
    swap in.
    """
    source = _get_owned_source(db, source_id, user.id)
    folder = source.folder

    subjects = _load_subjects_tree(db, user.id)
    rendered_html = markdown.markdown(source.raw_text)

    return templates.TemplateResponse(
        request,
        "subjects.html",
        {
            "subjects": subjects,
            "open_subject_id": folder.subject_id,
            "open_folder_id": folder.id,
            "folder_notes": {folder.id: _list_sources_for_folder(db, folder.id)},
            "selected_source_id": source.id,
            "selected_source": source,
            "source": source,
            "rendered_html": rendered_html,
        },
    )
