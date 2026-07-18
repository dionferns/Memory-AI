"""Subject and folder CRUD routes.

Every route here depends on ticket 03's ``current_user`` dependency and
scopes its query to that user: subjects are filtered directly on
``Subject.user_id``; folders are filtered via a join to their owning
subject's ``user_id``, since ``folders`` carries no ``user_id`` column of
its own. A resource that doesn't exist *or* belongs to another user always
returns 404 -- never 403 -- so an id's ownership can never be probed for
(ticket 04 decision #4).

Create/rename return just the changed HTML fragment; delete returns an
empty body with the row removed client-side via the control's own
``hx-target``/``hx-swap="outerHTML"`` (ticket 04 decision #6).

A subject's row is split into a header fragment (name + rename/delete
controls) and a folders-section fragment nested inside the same ``<li>``,
so that renaming a subject only swaps its header -- the folder list
underneath is untouched by that round trip.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile

from memory_ai import parsing
from memory_ai.auth import current_user
from memory_ai.database import get_db
from memory_ai.models import Folder, Source, Subject, User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Ticket 04 decision #1: required, trimmed, empty/whitespace-only rejected,
# max 200 characters, no other character restrictions. Applies identically
# to subject and folder names.
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


def _get_owned_folder(db: Session, folder_id: int, user_id: int) -> Folder:
    """Fetch a folder scoped to ``user_id`` via a join to its owning subject.

    ``folders`` carries no ``user_id`` column of its own (ticket 04 decision
    #4 / #23), so ownership is resolved by joining to ``subjects`` and
    filtering on that row's ``user_id``. A folder that doesn't exist, or
    whose owning subject belongs to another user, raises a plain 404.
    """
    folder = db.execute(
        select(Folder)
        .join(Subject, Folder.subject_id == Subject.id)
        .where(Folder.id == folder_id, Subject.user_id == user_id)
    ).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404)
    return folder


@router.get("/subjects")
def subjects_page(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Render the full ``/subjects`` hierarchy page for the current user.

    Subjects are loaded together with their folders via ``selectinload``:
    one query for the user's subjects, one follow-up query for all their
    folders in a single ``IN (...)`` -- not one query per subject (ticket 04
    decision #7).
    """
    subjects = (
        db.execute(
            select(Subject)
            .where(Subject.user_id == user.id)
            .options(selectinload(Subject.folders).selectinload(Folder.sources))
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
    """Return a subject's display-mode header fragment (used by rename-cancel)."""
    subject = _get_owned_subject(db, subject_id, user.id)
    return templates.TemplateResponse(request, "_subject_header_view.html", {"subject": subject})


@router.get("/subjects/{subject_id}/edit")
def edit_subject_form(
    subject_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Swap a subject's display header for its inline rename form."""
    subject = _get_owned_subject(db, subject_id, user.id)
    return templates.TemplateResponse(request, "_subject_header_edit.html", {"subject": subject})


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
    (ticket 04 decision #12). On success, swaps back to the display header.
    """
    subject = _get_owned_subject(db, subject_id, user.id)

    trimmed, error = _clean_name(name)
    if error:
        return templates.TemplateResponse(
            request,
            "_subject_header_edit.html",
            {"subject": subject, "error": error, "name": name},
        )

    subject.name = trimmed
    db.commit()

    return templates.TemplateResponse(request, "_subject_header_view.html", {"subject": subject})


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


@router.post("/subjects/{subject_id}/folders")
def create_folder(
    subject_id: int,
    request: Request,
    name: str = Form(...),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Create a folder nested under a subject owned by the current user.

    404s if the parent subject doesn't exist or isn't owned by the current
    user, before any name validation runs. On validation failure, re-renders
    just the create-folder-form fragment for that subject with an inline
    error. On success, returns the new folder's row fragment (appended
    out-of-band to that subject's folder list) plus a fresh create form.
    """
    subject = _get_owned_subject(db, subject_id, user.id)

    trimmed, error = _clean_name(name)
    if error:
        return templates.TemplateResponse(
            request,
            "_create_folder_form.html",
            {"subject": subject, "error": error, "name": name},
        )

    folder = Folder(subject_id=subject.id, name=trimmed, created_at=datetime.now(UTC))
    db.add(folder)
    db.commit()

    return templates.TemplateResponse(
        request,
        "_create_folder_result.html",
        {"subject": subject, "folder": folder},
    )


@router.get("/folders/{folder_id}")
def view_folder(
    folder_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Return a folder's display-mode row fragment (used by rename-cancel)."""
    folder = _get_owned_folder(db, folder_id, user.id)
    return templates.TemplateResponse(request, "_folder_row.html", {"folder": folder})


@router.get("/folders/{folder_id}/edit")
def edit_folder_form(
    folder_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Swap a folder's display row for its inline rename form."""
    folder = _get_owned_folder(db, folder_id, user.id)
    return templates.TemplateResponse(request, "_folder_edit_row.html", {"folder": folder})


@router.patch("/folders/{folder_id}")
def rename_folder(
    folder_id: int,
    request: Request,
    name: str = Form(...),
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Rename a folder owned (via its subject) by the current user.

    On validation failure, re-renders the inline edit form with an error.
    On success, swaps back to the display row.
    """
    folder = _get_owned_folder(db, folder_id, user.id)

    trimmed, error = _clean_name(name)
    if error:
        return templates.TemplateResponse(
            request,
            "_folder_edit_row.html",
            {"folder": folder, "error": error, "name": name},
        )

    folder.name = trimmed
    db.commit()

    return templates.TemplateResponse(request, "_folder_row.html", {"folder": folder})


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Delete a folder owned (via its subject) by the current user.

    Issues nothing more than a ``DELETE`` on the folder row -- cascading
    removal of its sources/cards (and, from ticket 05 on, reviews) is
    handled entirely by the DB's ``ON DELETE CASCADE`` foreign keys. Returns
    an empty body; the client removes the row itself via its own
    ``hx-target``/``hx-swap="outerHTML"``.
    """
    folder = _get_owned_folder(db, folder_id, user.id)
    db.delete(folder)
    db.commit()
    return Response(status_code=200)


# --- POST /folders/{folder_id}/sources (upload) -----------------------------

# Decision #3 (05-upload-and-parse): a fast reject based on the declared
# ``Content-Length`` header, ahead of the real streaming-read guard below.
# Multipart bodies carry some boilerplate (boundaries, per-part headers)
# beyond the raw file bytes, so this threshold is deliberately generous
# (well above `parsing.MAX_FILE_SIZE_BYTES`) to avoid rejecting a
# legitimate near-cap-size file on overhead alone -- it only exists to
# short-circuit *obviously* oversized uploads before spending time parsing
# the body at all. The streaming guard below is the actual enforcement.
_CONTENT_LENGTH_FAST_REJECT_BYTES = parsing.MAX_FILE_SIZE_BYTES + 64 * 1024

_SUPPORTED_TYPES_MESSAGE = "unsupported file type (accepted types: pdf, md, txt)"


def _size_limit_message() -> str:
    limit_mib = parsing.MAX_FILE_SIZE_BYTES // (1024 * 1024)
    return f"file too large (limit: {limit_mib} MiB)"


def _list_sources(db: Session, folder_id: int) -> list[Source]:
    return list(
        db.execute(
            select(Source)
            .where(Source.folder_id == folder_id)
            .order_by(Source.created_at.asc(), Source.id.asc())
        )
        .scalars()
        .all()
    )


def _render_sources_section(
    request: Request,
    db: Session,
    folder: Folder,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    sources = _list_sources(db, folder.id)
    return templates.TemplateResponse(
        request,
        "_folder_sources_section.html",
        {"folder": folder, "sources": sources, "error": error},
        status_code=status_code,
    )


@router.post("/folders/{folder_id}/sources")
async def upload_source(
    folder_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Upload a PDF/MD/TXT file into a folder owned by the current user.

    Parses the upload through :mod:`memory_ai.parsing`'s pure ``(bytes,
    file_type) -> str`` boundary and, on success, persists a ``sources`` row
    at ``status="stored"`` -- only the extracted text is kept, the original
    bytes are discarded once parsed. Every rejection (unsupported type,
    oversized file, no extractable text, unreadable/corrupt file) returns a
    422 with a case-specific message, rendered as the same HTMX-swappable
    sources-section fragment (with an inline error) that a successful
    upload's refreshed sources list also uses, so the fragment always swaps
    cleanly into ``#folder-{id}-sources-section`` either way. No ``sources``
    row is created on any rejection.

    Size enforcement is two-layered per ticket 05 decision #3: a fast reject
    on a clearly-oversized declared ``Content-Length`` (checked before the
    body is ever parsed), then a real streaming-read guard (reading at most
    ``MAX_FILE_SIZE_BYTES + 1`` bytes from the received upload) so a
    spoofed or missing header can't bypass the cap.
    """
    folder = _get_owned_folder(db, folder_id, user.id)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > _CONTENT_LENGTH_FAST_REJECT_BYTES:
            return _render_sources_section(
                request, db, folder, error=_size_limit_message(), status_code=422
            )

    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        return _render_sources_section(
            request, db, folder, error="No file was uploaded.", status_code=422
        )

    filename = upload.filename or ""
    file_type = filename.rsplit(".", 1)[-1] if "." in filename else ""

    # The real enforcement: read at most cap+1 bytes from the (already
    # fully-received) upload stream, regardless of what `Content-Length`
    # claimed.
    data = await upload.read(parsing.MAX_FILE_SIZE_BYTES + 1)
    if len(data) > parsing.MAX_FILE_SIZE_BYTES:
        return _render_sources_section(
            request, db, folder, error=_size_limit_message(), status_code=422
        )

    try:
        raw_text = parsing.parse_file(data, file_type)
    except parsing.UnsupportedFileType:
        return _render_sources_section(
            request, db, folder, error=_SUPPORTED_TYPES_MESSAGE, status_code=422
        )
    except parsing.FileTooLarge:
        return _render_sources_section(
            request, db, folder, error=_size_limit_message(), status_code=422
        )
    except parsing.UnreadableFile:
        return _render_sources_section(
            request,
            db,
            folder,
            error="could not read this PDF -- the file may be corrupt.",
            status_code=422,
        )
    except parsing.NoExtractableText:
        return _render_sources_section(
            request,
            db,
            folder,
            error="no extractable text -- likely a scanned/image PDF.",
            status_code=422,
        )

    source = Source(
        folder_id=folder.id,
        filename=filename,
        file_type=file_type.lower(),
        raw_text=raw_text,
        status="stored",
        created_at=datetime.now(UTC),
    )

    # Insert-then-catch, not a pre-check `SELECT`: the DB's functional
    # unique index on `(folder_id, lower(filename))` is the source of
    # truth (ticket 05 decision #10), matching the same pattern already
    # locked for duplicate emails in ticket 03. Scoped in its own
    # SAVEPOINT (`begin_nested`) rather than a bare `db.rollback()`, since
    # `db` is itself already wrapped in an outer transaction in tests
    # (ticket 21's harness) -- rolling back just this SAVEPOINT leaves any
    # outer transaction untouched either way.
    nested = db.begin_nested()
    try:
        db.add(source)
        db.flush()
    except IntegrityError:
        nested.rollback()
        return _render_sources_section(
            request,
            db,
            folder,
            error=f"a file named '{filename}' already exists in this folder.",
            status_code=422,
        )
    else:
        nested.commit()

    db.commit()

    return _render_sources_section(request, db, folder)
