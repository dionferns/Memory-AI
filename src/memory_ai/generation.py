"""Convert-to-flashcards trigger, background generation job, and status poll.

Implements tickets/06-ai-flashcards's core generation flow:

- ``POST /sources/{id}/convert`` transitions a source to ``processing``,
  schedules a FastAPI ``BackgroundTasks`` job, and returns immediately with
  an HTMX fragment for the processing popup (decision #13). Re-clicking it
  on an already-``done``/``failed`` source **replaces**: existing ``cards``
  rows (and their cascaded ``reviews``) are deleted before the new
  generation runs (decision #5).
- The background job opens its own SQLAlchemy session via
  ``database.get_session_factory`` (decision #12) -- never the
  request-scoped session, which may already be closed by the time the job
  runs. It reads ``raw_text`` (chunked via ticket 05's ``chunk_text`` if it
  exceeds the model's context), calls the injected ``FlashcardGenerator``
  once per chunk, and on success persists all generated cards with the SM-2
  defaults from decision #17, setting ``status=done``. Any
  ``FlashcardValidationError``/``FlashcardAPIError`` (malformed output or an
  Anthropic API failure) results in ``status=failed`` with a generic
  ``error_message`` and zero ``cards`` rows written (decisions #7/#8) --
  cards are only ever added to the session after generation has fully
  succeeded for every chunk, so there is no partial-write window to roll
  back.
- ``GET /sources/{id}/status`` returns the same status fragment so the
  processing popup can poll it (decision #14).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from memory_ai.auth import current_user
from memory_ai.database import get_db, get_session_factory
from memory_ai.flashcards import (
    FlashcardAPIError,
    FlashcardGenerator,
    FlashcardValidationError,
    GeneratedCard,
    get_flashcard_generator,
)
from memory_ai.models import Card, Folder, Source, Subject, User
from memory_ai.parsing import chunk_text

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Generic, non-leaking failure message shown to the user for both a
# malformed-output validation failure and an Anthropic API error (decision
# #7/#8) -- neither exposes SDK/validation internals.
_GENERIC_ERROR_MESSAGE = "Flashcard generation failed. Please try again."


def _get_owned_source(db: Session, source_id: int, user_id: int) -> Source:
    """Fetch a source scoped to ``user_id`` via a join through folder -> subject.

    A source that doesn't exist, or whose owning folder/subject belongs to
    another user, raises a plain 404 -- never 403 -- matching the rest of
    the app's ownership-check pattern (ticket 04 decision #4).
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


@router.post("/sources/{source_id}/convert")
def convert_source(
    source_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    session_factory: Callable[[], AbstractContextManager[Session]] = Depends(  # noqa: B008
        get_session_factory
    ),
    generator: FlashcardGenerator = Depends(get_flashcard_generator),  # noqa: B008
) -> Response:
    """Trigger (or re-trigger) flashcard generation for a source.

    Allowed from any status, including ``done``/``failed`` -- a re-trigger
    on either is treated as a replace/retry: all existing ``cards`` rows for
    this source (and their cascaded ``reviews``) are deleted before
    ``status`` is reset to ``processing`` and the background job scheduled,
    so a retry never accumulates duplicate cards (decision #5). Returns
    immediately -- the LLM call happens entirely inside the scheduled
    ``BackgroundTasks`` job, never blocking this response.
    """
    source = _get_owned_source(db, source_id, user.id)

    db.execute(delete(Card).where(Card.source_id == source.id))
    source.status = "processing"
    source.error_message = None
    db.commit()

    background_tasks.add_task(_run_generation_job, source.id, session_factory, generator)

    return templates.TemplateResponse(request, "_source_status.html", {"source": source})


@router.get("/sources/{source_id}/status")
def source_status(
    source_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Return the current status fragment, polled by the processing popup."""
    source = _get_owned_source(db, source_id, user.id)
    return templates.TemplateResponse(request, "_source_status.html", {"source": source})


def _run_generation_job(
    source_id: int,
    session_factory: Callable[[], AbstractContextManager[Session]],
    generator: FlashcardGenerator,
) -> None:
    """Generate and persist flashcards for ``source_id`` on its own DB session.

    Runs in FastAPI's ``BackgroundTasks`` thread pool (or, in HTTP-seam
    tests, synchronously as part of the same request/response cycle
    Starlette's ``TestClient`` drives) -- never on the request-scoped
    session, which may already be closed by the time this runs.
    """
    with session_factory() as db:
        source = db.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
        if source is None:
            # The source was deleted out from under a scheduled job; nothing
            # left to do.
            return

        try:
            chunks = chunk_text(source.raw_text)
            generated: list[GeneratedCard] = []
            for chunk in chunks:
                generated.extend(generator.generate(chunk))
        except (FlashcardValidationError, FlashcardAPIError):
            source.status = "failed"
            source.error_message = _GENERIC_ERROR_MESSAGE
            db.commit()
            return

        now = datetime.now(UTC)
        today = now.date()
        for card in generated:
            db.add(
                Card(
                    source_id=source.id,
                    folder_id=source.folder_id,
                    front=card.question,
                    back=card.answer,
                    ease_factor=2.5,
                    interval_days=0,
                    repetitions=0,
                    due_date=today,
                    created_at=now,
                )
            )
        source.status = "done"
        source.error_message = None
        db.commit()
