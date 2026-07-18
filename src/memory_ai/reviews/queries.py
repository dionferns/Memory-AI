"""The single shared "what's due" query (ticket 09 decision #4).

``get_due_cards`` is the sole read path for due cards: the global daily
review route (``GET /review``) and the per-subject review route
(``GET /review/subjects/{subject_id}``) both call this exact function --
never a separately-written query -- so their notions of "what's due" cannot
drift apart (ticket 09 PRD: "global and subject review are different
queries over the same rows, so their schedules cannot drift").
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_ai.models import Card, Folder, Source, Subject


def get_due_cards(
    session: Session,
    user_id: int,
    subject_id: int | None = None,
    limit: int | None = None,
    *,
    as_of: date,
) -> list[Card]:
    """Return ``user_id``'s due cards, most-overdue-first.

    A card is "due" when ``Card.due_date <= as_of`` -- ``as_of`` is a
    tz-aware "today" boundary the caller resolves via ticket 08's
    ``today_in_tz`` helper against the user's own ``user_settings.timezone``
    (ticket 09 decision #7); this function does no timezone math of its own.

    Ordering is ``due_date ASC, id ASC`` (ticket 09 decisions #1/#2): the
    most-overdue card first, with ``id`` as a deterministic tiebreak for
    cards sharing the same ``due_date``.

    ``subject_id=None`` (the default) returns cards across every subject
    the user owns; passing a ``subject_id`` scopes to that one subject only,
    via the ``cards -> sources -> folders -> subjects`` ownership chain
    (matching ``cards.py``'s existing join pattern) -- a ``subject_id`` the
    caller doesn't own simply yields no rows here, since callers are
    expected to have already 404'd on subject ownership before calling.

    ``limit=None`` (the default) is uncapped; passing a ``limit`` applies a
    plain SQL ``LIMIT``, which is a no-op when it exceeds the due count
    (ticket 09 decision #3) -- no separate ``COUNT(*)`` is needed.
    """
    stmt = (
        select(Card)
        .join(Source, Card.source_id == Source.id)
        .join(Folder, Source.folder_id == Folder.id)
        .join(Subject, Folder.subject_id == Subject.id)
        .where(Subject.user_id == user_id, Card.due_date <= as_of)
        .order_by(Card.due_date.asc(), Card.id.asc())
    )
    if subject_id is not None:
        stmt = stmt.where(Subject.id == subject_id)
    if limit is not None:
        stmt = stmt.limit(limit)

    return list(session.execute(stmt).scalars().all())
