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
from sqlalchemy import delete, select, update
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

# Upper bound on how many chunks a single source may fan out into before we
# refuse to run the generation job at all (issue #125). Each chunk is a
# separate, sequential LLM call that can emit up to `flashcards.MAX_CARDS`
# cards, so an uncapped near-cap 10 MiB upload (~106 chunks at
# `parsing.DEFAULT_MAX_CHARS`) could spawn a multi-minute job producing
# thousands of cards. Capping at 50 bounds one conversion to <=50 sequential
# calls and <=50 * MAX_CARDS (5000) cards; at 100_000 chars/chunk that is
# ~5M characters of notes -- far larger than any realistic study document,
# while still rejecting the pathological max-size case before any LLM call
# is made.
MAX_CHUNKS_PER_SOURCE = 50

# Shown on a source that was left in `processing` by a background job that
# never got to run to completion -- distinct from `_GENERIC_ERROR_MESSAGE` so
# the user can tell "the last attempt was interrupted" apart from "the last
# attempt failed on its own" (issue #125).
_INTERRUPTED_ERROR_MESSAGE = (
    "Flashcard generation was interrupted by a server restart. Please try again."
)


def reconcile_interrupted_jobs(db: Session) -> int:
    """Fail out any source stuck in ``processing`` from a prior process's run.

    FastAPI's ``BackgroundTasks`` are purely in-memory: if the process exits
    (deploy, crash, worker recycle) after ``convert_source`` commits
    ``status="processing"`` but before ``_run_generation_job`` finishes, that
    job is gone -- nothing will ever flip the source out of ``processing``,
    and the existing per-job exception handling (issue #117) can't help
    because the job never ran on this process. Call this once at application
    startup, before any request is served, so any such leftover row is
    deterministically flipped to ``failed`` with a clear message instead of
    being stuck forever. Returns the number of sources reconciled.

    This does not attempt to recover or resume the interrupted generation --
    the user retries via the normal "Convert to Flashcards" button, which
    ticket 06 decision #5/#13 already specifies as the retry path. It also
    does not change the delete-before-generate ordering in ``convert_source``
    (that's an explicit ticket 06 decision, not a bug) -- it only ensures a
    source can't be silently stuck past the one moment ("startup") where we
    can be certain no other process is still running that job.
    """
    result = db.execute(
        update(Source)
        .where(Source.status == "processing")
        .values(status="failed", error_message=_INTERRUPTED_ERROR_MESSAGE)
    )
    db.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


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

    if source.status == "processing":
        raise HTTPException(status_code=409, detail="Flashcard generation is already in progress.")

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
            if len(chunks) > MAX_CHUNKS_PER_SOURCE:
                # The source is too large to convert without an unbounded
                # fan-out of LLM calls (issue #125). Fail fast -- before any
                # generate() call -- and surface it exactly like a validation
                # failure: status="failed", generic message, zero cards.
                source.status = "failed"
                source.error_message = _GENERIC_ERROR_MESSAGE
                db.commit()
                return
            generated: list[GeneratedCard] = []
            for chunk in chunks:
                generated.extend(generator.generate(chunk))
        except (FlashcardValidationError, FlashcardAPIError):
            source.status = "failed"
            source.error_message = _GENERIC_ERROR_MESSAGE
            db.commit()
            return
        except Exception:
            # Any other unexpected failure while generating (e.g. a bug in
            # the generator) must still flip status away from "processing" --
            # otherwise the processing popup polls forever with no way for
            # the user to recover short of a full re-trigger. See issue
            # #117. No DB writes have happened yet at this point, so no
            # rollback is needed before recording the failure.
            source.status = "failed"
            source.error_message = _GENERIC_ERROR_MESSAGE
            db.commit()
            raise

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
        try:
            source.status = "done"
            source.error_message = None
            db.commit()
        except Exception:
            # The insert/commit itself failed (e.g. a DB error) -- the
            # session's transaction is now unusable, so it must be rolled
            # back before it can record the failure. This is the one branch
            # where a rollback is both necessary and safe: the source's own
            # "processing" state was already durably committed by
            # `convert_source` before this job ran, so undoing this
            # in-flight transaction can't lose anything but the never-
            # persisted card inserts. See issue #117.
            db.rollback()
            source.status = "failed"
            source.error_message = _GENERIC_ERROR_MESSAGE
            db.commit()
            raise
