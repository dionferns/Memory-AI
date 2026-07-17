"""Pure, I/O-free SM-2 spaced-repetition scheduling math.

This module contains only pure functions: no database session, no HTTP,
and no reads of a global clock (``datetime.now()`` / ``datetime.utcnow()``).
Every input the math depends on — the prior schedule state, the grade, and
"today" itself — is passed in explicitly by the caller.

The exact formulas here are locked in ``tickets/08-sr-algorithm/decisions.md``
and restated in ``tickets/08-sr-algorithm/PRD.md``; this module is a literal
transcription of those formulas. The persistence helper that writes an
``apply_sm2`` result onto a ``Card``/``Review`` ORM pair lives in a separate
ticket (09-sr-algorithm's persistence-helper issue), not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import floor
from typing import Literal
from zoneinfo import ZoneInfo

Grade = Literal["again", "hard", "good", "easy"]

_GRADE_TO_QUALITY: dict[Grade, int] = {
    "again": 0,
    "hard": 3,
    "good": 4,
    "easy": 5,
}

_EASE_FLOOR = 1.3


@dataclass(frozen=True)
class SM2Result:
    """The updated schedule state produced by a single ``apply_sm2`` call."""

    ease_factor: float
    interval_days: int
    repetitions: int
    due_date: date


def _round_half_up(value: float) -> int:
    """Round-half-up (``floor(x + 0.5)``), not Python's banker's-rounding."""
    return floor(value + 0.5)


def apply_sm2(
    ease_factor: float,
    interval_days: int,
    repetitions: int,
    grade: Grade,
    today: date,
) -> SM2Result:
    """Apply one graded review to a card's SM-2 schedule state.

    Pure function: no I/O, no clock reads. ``today`` is the caller-resolved
    "today" (see ``today_in_tz``) against which the new ``due_date`` is
    computed.
    """
    quality = _GRADE_TO_QUALITY[grade]

    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(new_ease, _EASE_FLOOR)

    if quality < 3:
        new_repetitions = 0
        new_interval_days = 1
    else:
        new_repetitions = repetitions + 1
        if new_repetitions == 1:
            new_interval_days = 1
        elif new_repetitions == 2:
            new_interval_days = 6
        else:
            new_interval_days = _round_half_up(interval_days * new_ease)

    due_date = today + timedelta(days=new_interval_days)

    return SM2Result(
        ease_factor=new_ease,
        interval_days=new_interval_days,
        repetitions=new_repetitions,
        due_date=due_date,
    )


def today_in_tz(now_utc: datetime, tz: ZoneInfo) -> date:
    """Resolve "today" for a tz-aware instant in the given timezone.

    Never reads a global clock; ``now_utc`` must be supplied by the caller
    and must be timezone-aware. Raises ``ValueError`` if ``now_utc`` is
    naive (no ``tzinfo``).
    """
    if now_utc.tzinfo is None or now_utc.tzinfo.utcoffset(now_utc) is None:
        raise ValueError("now_utc must be timezone-aware, got a naive datetime")
    return now_utc.astimezone(tz).date()
