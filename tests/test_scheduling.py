"""Exhaustive unit tests for the pure SM-2 scheduling module.

No DB, no HTTP client — every assertion here is a hand-computed expected
value transcribed directly from ``tickets/08-sr-algorithm/decisions.md``.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from memory_ai.scheduling import SM2Result, apply_sm2, today_in_tz

TODAY = date(2026, 7, 17)


# ---------------------------------------------------------------------------
# First review from a brand-new card (ease=2.5, interval_days=0, repetitions=0)
# ---------------------------------------------------------------------------


class TestFirstReview:
    def test_again(self) -> None:
        result = apply_sm2(
            ease_factor=2.5, interval_days=0, repetitions=0, grade="again", today=TODAY
        )
        assert result.ease_factor == pytest.approx(1.7)
        assert result.interval_days == 1
        assert result.repetitions == 0
        assert result.due_date == TODAY + timedelta(days=1)

    def test_hard(self) -> None:
        result = apply_sm2(
            ease_factor=2.5, interval_days=0, repetitions=0, grade="hard", today=TODAY
        )
        assert result == SM2Result(
            ease_factor=2.36, interval_days=1, repetitions=1, due_date=TODAY + timedelta(days=1)
        )

    def test_good(self) -> None:
        result = apply_sm2(
            ease_factor=2.5, interval_days=0, repetitions=0, grade="good", today=TODAY
        )
        assert result == SM2Result(
            ease_factor=2.5, interval_days=1, repetitions=1, due_date=TODAY + timedelta(days=1)
        )

    def test_easy(self) -> None:
        result = apply_sm2(
            ease_factor=2.5, interval_days=0, repetitions=0, grade="easy", today=TODAY
        )
        assert result == SM2Result(
            ease_factor=2.6, interval_days=1, repetitions=1, due_date=TODAY + timedelta(days=1)
        )


# ---------------------------------------------------------------------------
# Each grade's ease-factor delta in isolation, from a neutral ease of 2.5
# ---------------------------------------------------------------------------


class TestEaseFactorDeltas:
    """EF' = EF + (0.1 - (5-q)*(0.08+(5-q)*0.02)); Again -0.8, Hard -0.14, Good +0, Easy +0.1."""

    @pytest.mark.parametrize(
        ("grade", "expected_ease"),
        [
            ("again", 1.7),
            ("hard", 2.36),
            ("good", 2.5),
            ("easy", 2.6),
        ],
    )
    def test_delta(self, grade: str, expected_ease: float) -> None:
        result = apply_sm2(
            ease_factor=2.5,
            interval_days=10,
            repetitions=3,
            grade=grade,  # type: ignore[arg-type]
            today=TODAY,
        )
        assert result.ease_factor == pytest.approx(expected_ease)


# ---------------------------------------------------------------------------
# Ease-floor enforcement
# ---------------------------------------------------------------------------


class TestEaseFloor:
    def test_again_floors_at_1_3(self) -> None:
        # 1.35 - 0.8 = 0.55, well below the 1.3 floor.
        result = apply_sm2(
            ease_factor=1.35, interval_days=5, repetitions=4, grade="again", today=TODAY
        )
        assert result.ease_factor == pytest.approx(1.3)

    def test_hard_floors_at_1_3(self) -> None:
        # 1.35 - 0.14 = 1.21, below the 1.3 floor.
        result = apply_sm2(
            ease_factor=1.35, interval_days=5, repetitions=4, grade="hard", today=TODAY
        )
        assert result.ease_factor == pytest.approx(1.3)

    def test_exactly_at_floor_stays_at_floor(self) -> None:
        # Already at the floor; Good (+0 delta) should leave it exactly there.
        result = apply_sm2(
            ease_factor=1.3, interval_days=5, repetitions=4, grade="good", today=TODAY
        )
        assert result.ease_factor == pytest.approx(1.3)

    def test_easy_can_still_raise_ease_from_near_floor(self) -> None:
        # 1.3 + 0.1 = 1.4, above the floor -- floor must not clamp upward results.
        result = apply_sm2(
            ease_factor=1.3, interval_days=5, repetitions=4, grade="easy", today=TODAY
        )
        assert result.ease_factor == pytest.approx(1.4)


# ---------------------------------------------------------------------------
# repetitions == 1 -> interval == 1, repetitions == 2 -> interval == 6,
# independent of which pass grade triggered the transition.
# ---------------------------------------------------------------------------


class TestRepetitionIntervalTransitions:
    @pytest.mark.parametrize("grade", ["hard", "good", "easy"])
    def test_new_repetitions_1_gives_interval_1(self, grade: str) -> None:
        result = apply_sm2(
            ease_factor=2.5,
            interval_days=0,
            repetitions=0,
            grade=grade,  # type: ignore[arg-type]
            today=TODAY,
        )
        assert result.repetitions == 1
        assert result.interval_days == 1

    @pytest.mark.parametrize("grade", ["hard", "good", "easy"])
    def test_new_repetitions_2_gives_interval_6(self, grade: str) -> None:
        result = apply_sm2(
            ease_factor=2.5,
            interval_days=1,
            repetitions=1,
            grade=grade,  # type: ignore[arg-type]
            today=TODAY,
        )
        assert result.repetitions == 2
        assert result.interval_days == 6


# ---------------------------------------------------------------------------
# repetitions >= 3 growth formula, including an exact .5 rounding boundary.
# ---------------------------------------------------------------------------


class TestGrowthFormula:
    def test_round_half_up_at_exact_half_boundary(self) -> None:
        # prev_interval_days=5, new_ease_factor=2.5 -> raw product 12.5.
        # round_half_up(12.5) == 13, whereas Python's round() (banker's
        # rounding) would give 12 since 12 is the nearest even.
        result = apply_sm2(
            ease_factor=2.5, interval_days=5, repetitions=2, grade="good", today=TODAY
        )
        assert round(12.5) == 12  # sanity check: banker's rounding would differ
        assert result.repetitions == 3
        assert result.interval_days == 13
        assert result.ease_factor == pytest.approx(2.5)

    def test_growth_uses_updated_ease_and_previous_interval(self) -> None:
        # prev_interval=15, ease starts at 2.5, grade Good (delta +0) -> new
        # ease 2.5, growth = round_half_up(15 * 2.5) = round_half_up(37.5) = 38.
        result = apply_sm2(
            ease_factor=2.5, interval_days=15, repetitions=3, grade="good", today=TODAY
        )
        assert result.repetitions == 4
        assert result.interval_days == 38

    def test_growth_with_easy_grade(self) -> None:
        # ease 2.0 -> Easy delta +0.1 -> new ease 2.1; interval = round_half_up(10 * 2.1) = 21.
        result = apply_sm2(
            ease_factor=2.0, interval_days=10, repetitions=5, grade="easy", today=TODAY
        )
        assert result.repetitions == 6
        assert result.ease_factor == pytest.approx(2.1)
        assert result.interval_days == 21


# ---------------------------------------------------------------------------
# Again reset from deep repetition state.
# ---------------------------------------------------------------------------


class TestAgainResetFromDeepState:
    def test_again_resets_repetitions_and_interval_but_still_updates_ease(self) -> None:
        result = apply_sm2(
            ease_factor=2.5, interval_days=40, repetitions=5, grade="again", today=TODAY
        )
        assert result.repetitions == 0
        assert result.interval_days == 1
        # Ease is reduced by the formula (2.5 - 0.8 = 1.7), not reset to 2.5
        # and not left unchanged at 2.5.
        assert result.ease_factor == pytest.approx(1.7)
        assert result.due_date == TODAY + timedelta(days=1)


# ---------------------------------------------------------------------------
# Consecutive-grade sequences: state threads correctly across calls.
# ---------------------------------------------------------------------------


class TestChainedSequences:
    def test_good_good_good(self) -> None:
        # Worked example from decisions.md's Notes section.
        state = apply_sm2(
            ease_factor=2.5, interval_days=0, repetitions=0, grade="good", today=TODAY
        )
        assert state == SM2Result(2.5, 1, 1, TODAY + timedelta(days=1))

        state = apply_sm2(
            ease_factor=state.ease_factor,
            interval_days=state.interval_days,
            repetitions=state.repetitions,
            grade="good",
            today=TODAY,
        )
        assert state == SM2Result(2.5, 6, 2, TODAY + timedelta(days=6))

        state = apply_sm2(
            ease_factor=state.ease_factor,
            interval_days=state.interval_days,
            repetitions=state.repetitions,
            grade="good",
            today=TODAY,
        )
        # round_half_up(6 * 2.5) == round_half_up(15.0) == 15
        assert state == SM2Result(2.5, 15, 3, TODAY + timedelta(days=15))

    def test_good_good_good_again(self) -> None:
        # Same as above, but graded Again on what would have been the 4th
        # review instead of Good. Matches decisions.md's worked example:
        # repetitions=0, interval=1, ease=2.5-0.8=1.7.
        state = apply_sm2(2.5, 0, 0, "good", TODAY)
        state = apply_sm2(state.ease_factor, state.interval_days, state.repetitions, "good", TODAY)
        state = apply_sm2(state.ease_factor, state.interval_days, state.repetitions, "good", TODAY)
        assert state == SM2Result(2.5, 15, 3, TODAY + timedelta(days=15))

        state = apply_sm2(state.ease_factor, state.interval_days, state.repetitions, "again", TODAY)
        assert state.repetitions == 0
        assert state.interval_days == 1
        assert state.ease_factor == pytest.approx(1.7)

    def test_good_good_again_good(self) -> None:
        state = apply_sm2(2.5, 0, 0, "good", TODAY)
        assert state == SM2Result(2.5, 1, 1, TODAY + timedelta(days=1))

        state = apply_sm2(state.ease_factor, state.interval_days, state.repetitions, "good", TODAY)
        assert state == SM2Result(2.5, 6, 2, TODAY + timedelta(days=6))

        state = apply_sm2(state.ease_factor, state.interval_days, state.repetitions, "again", TODAY)
        assert state.repetitions == 0
        assert state.interval_days == 1
        assert state.ease_factor == pytest.approx(1.7)

        state = apply_sm2(state.ease_factor, state.interval_days, state.repetitions, "good", TODAY)
        # From (ease=1.7, interval=1, repetitions=0): Good delta +0 -> ease
        # 1.7 unchanged; new repetitions=1 -> interval=1.
        assert state.repetitions == 1
        assert state.interval_days == 1
        assert state.ease_factor == pytest.approx(1.7)
        assert state.due_date == TODAY + timedelta(days=1)


# ---------------------------------------------------------------------------
# due_date arithmetic, one case per interval branch.
# ---------------------------------------------------------------------------


class TestDueDateArithmetic:
    def test_interval_1_branch(self) -> None:
        result = apply_sm2(2.5, 0, 0, "good", TODAY)
        assert result.interval_days == 1
        assert result.due_date == TODAY + timedelta(days=1)

    def test_interval_6_branch(self) -> None:
        result = apply_sm2(2.5, 1, 1, "good", TODAY)
        assert result.interval_days == 6
        assert result.due_date == TODAY + timedelta(days=6)

    def test_interval_growth_branch(self) -> None:
        result = apply_sm2(2.5, 6, 2, "good", TODAY)
        assert result.interval_days == 15
        assert result.due_date == TODAY + timedelta(days=15)

    def test_again_branch(self) -> None:
        result = apply_sm2(2.5, 40, 5, "again", TODAY)
        assert result.interval_days == 1
        assert result.due_date == TODAY + timedelta(days=1)


# ---------------------------------------------------------------------------
# today_in_tz boundary cases.
# ---------------------------------------------------------------------------


class TestTodayInTz:
    def test_positive_and_negative_offset_straddle_utc_day_boundary(self) -> None:
        # 2026-07-17T10:30:00Z: Pacific/Kiritimati (+14) has already rolled
        # into "tomorrow" (2026-07-18); Pacific/Niue (-11) is still on
        # "yesterday" (2026-07-16), relative to the UTC calendar date.
        now_utc = datetime(2026, 7, 17, 10, 30, tzinfo=ZoneInfo("UTC"))

        assert today_in_tz(now_utc, ZoneInfo("Pacific/Kiritimati")) == date(2026, 7, 18)
        assert today_in_tz(now_utc, ZoneInfo("Pacific/Niue")) == date(2026, 7, 16)

    def test_dst_transition_case(self) -> None:
        # America/New_York springs forward at 2026-03-08 02:00 local (07:00 UTC).
        before_dst = datetime(2026, 3, 8, 4, 30, tzinfo=ZoneInfo("UTC"))
        after_dst = datetime(2026, 3, 8, 7, 30, tzinfo=ZoneInfo("UTC"))
        tz = ZoneInfo("America/New_York")

        assert today_in_tz(before_dst, tz) == date(2026, 3, 7)
        assert today_in_tz(after_dst, tz) == date(2026, 3, 8)

    def test_naive_datetime_raises(self) -> None:
        naive = datetime(2026, 7, 17, 12, 0)
        with pytest.raises(ValueError, match="naive"):
            today_in_tz(naive, ZoneInfo("UTC"))

    def test_utc_instant_same_day_in_utc_itself(self) -> None:
        now_utc = datetime(2026, 7, 17, 12, 0, tzinfo=ZoneInfo("UTC"))
        assert today_in_tz(now_utc, ZoneInfo("UTC")) == date(2026, 7, 17)
