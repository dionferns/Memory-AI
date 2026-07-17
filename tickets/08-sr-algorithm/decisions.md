# 08 — SR Algorithm: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (no open questions for the user — this
is the correctness-critical core of the app, so every branch is resolved against classic SM-2 and
recorded here precisely, including formulas). Source of truth for the sr-algorithm ticket; the
master PRD's "Spaced repetition" section is the higher-level contract this elaborates.

## Grade → SM-2 quality mapping

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Quality scale | Classic SM-2's 0–5 integer scale, never exposed to the user directly | Keeps the pure function a faithful SM-2 implementation; the four UI buttons are a curated subset of the scale |
| 2 | Again → quality | `0` | "Complete blackout" — the classic SM-2 value for total recall failure; must be `<3` so it triggers the reset branch |
| 3 | Hard → quality | `3` | Classic SM-2's pass/fail threshold value ("correct response recalled with serious difficulty"); the lowest quality that still counts as a *pass* — chosen deliberately so Hard does not reset repetitions, matching the plan's stated Again-only-reset behavior |
| 4 | Good → quality | `4` | "Correct response after a hesitation" — the standard "normal, unremarkable pass" value |
| 5 | Easy → quality | `5` | "Perfect response" — the standard "no hesitation" value |
| 6 | Quality values `1`/`2` | Unused | SM-2 defines them ("incorrect, but the correct answer felt familiar" / "incorrect, but the correct answer was easy to recall") as finer failure gradations; the four-button UI only distinguishes one failure state (Again) and three pass states, so they have no button to map to |

This mapping (0 / 3 / 4 / 5) is the standard adaptation used by essentially every SM-2-derived
consumer app with a 4-button grader (Anki's "Again/Hard/Good/Easy" ancestry traces to it): it
preserves SM-2's `quality < 3` reset rule exactly while giving the three pass grades meaningfully
distinct positions in the formula below.

## Ease-factor update

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 7 | Ease update formula | `EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))`, applied on **every** grade (including Again) | The unmodified classic SM-2 formula (Wozniak 1990); applying it unconditionally — not skipping it on Again — is required by the plan's explicit note that "ease factor is still reduced per the formula, not reset" |
| 8 | Ease floor | `1.3`, applied after computing `EF'` (`EF' = max(EF', 1.3)`) | Classic SM-2's floor — a card can get progressively harder but never enter a runaway-short-interval death spiral |
| 9 | Ease ceiling | None | Classic SM-2 defines no ceiling; not requested by any user story, so none is added |
| 10 | Ease precision | Stored as the raw `float` result of the formula (after flooring); no additional rounding | Matches `cards.ease_factor: Mapped[float]` (ticket 02); rounding would only lose precision the formula intentionally carries forward review-to-review |
| 11 | Ease update on Again | Same formula as pass grades (`q=0` plugged in), **not** reset to the card's default (2.5) or left unchanged | Distinguishes "this card is fundamentally hard" (permanently lower ease across repeated Agains) from "reset to fresh-card state" — matches classic SM-2 and the plan's explicit instruction |

With `q=0`: `EF' = EF - 0.8` (before flooring). With `q=3` (Hard): `EF' = EF - 0.14`. With `q=4`
(Good): `EF' = EF + 0`. With `q=5` (Easy): `EF' = EF + 0.1`.

## Repetitions / interval update

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 12 | Again (`q<3`) repetitions/interval | `repetitions → 0`, `interval_days → 1` | Matches the plan verbatim: "Again... reset repetitions to 0, interval back to 1 day"; `1` (not `0`) so the card is due again tomorrow, not "already due" — a stale, already-past due_date would misrepresent an Again as more overdue than it is |
| 13 | Pass (`q>=3`) repetitions | `repetitions → repetitions + 1` | Classic SM-2; repetitions counts consecutive passes since the last reset |
| 14 | Pass, new `repetitions == 1` (first-ever pass, or first pass after an Again) | `interval_days → 1` | Classic SM-2's first-repetition interval |
| 15 | Pass, new `repetitions == 2` | `interval_days → 6` | Classic SM-2's second-repetition interval |
| 16 | Pass, new `repetitions >= 3` | `interval_days → round_half_up(prev_interval_days * new_ease_factor)` | Classic SM-2's growth formula; uses the **already-updated** (post-floor) ease factor, and the **previous** interval (pre-update), per Wozniak's original algorithm |
| 17 | Rounding rule for #16 | Round-half-up (`floor(x + 0.5)`), not Python's built-in `round()` | Python's `round()` uses banker's-rounding (round-half-to-even), which is a surprising, non-obvious tie-break for a scheduling algorithm; round-half-up is the conventional, deterministic choice and avoids off-by-one flakiness in the exhaustive test table at exact `.5` boundaries |
| 18 | Minimum interval, all paths | `1` day | An interval of `0` would mean "due today, again" for a card just reviewed today, which reads as broken; every branch (#14/#15/#16 for growth, #12 for Again) already produces `>=1` by construction, so no explicit clamp is needed, but it is asserted as an invariant in tests |
| 19 | Maximum interval | None (uncapped) | Not requested by any user story; matches ticket-level "no cap" default of SM-2 |
| 20 | Hard's effect on repetitions/interval | Treated as a normal pass (goes through #13–#16 like Good/Easy) — the *only* difference Hard has from Good/Easy is its lower ease-factor delta (#7) | Consistent with quality mapping decision #3: Hard is quality `3`, which is `>=3`, so classic SM-2 routes it through the pass branch, not the reset branch |

## Pure function signature

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 21 | Grade representation | `Grade = Literal["again", "hard", "good", "easy"]` | Matches ticket 02 decision #6 ("plain string columns, validated in app code"); these are the exact strings persisted to `reviews.grade` |
| 22 | Pure function inputs | `ease_factor: float, interval_days: int, repetitions: int, grade: Grade, today: date` — a plain `date`, not a `datetime`/tz | Keeps the function pure and trivially exhaustible: it never resolves "what is today"; that resolution is a separate, single-purpose boundary function (#25) called once by the caller before invoking this one |
| 23 | Pure function output | A small immutable result type (`SM2Result` — frozen dataclass or `NamedTuple`) with `ease_factor: float, interval_days: int, repetitions: int, due_date: date` | Named fields keep call sites and tests self-documenting versus a bare tuple |
| 24 | `due_date` computation | `due_date = today + timedelta(days=interval_days)` (the *new* `interval_days`) | The only place "today" and "interval" combine; keeping it inside the pure function (rather than pushed to the caller) means one function is the single source of truth for the scheduling math |

## Timezone / due-date boundary

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 25 | Boundary function signature | `today_in_tz(now_utc: datetime, tz: ZoneInfo) -> date` — `now_utc` must be tz-aware (raises if naive) | Explicit, injected inputs only — no `datetime.now()`/`datetime.utcnow()` call anywhere in this module — keeps "due today" fully deterministic and unit-testable across DST/offset edge cases; matches the plan's "never reads a global clock" requirement |
| 26 | Implementation | `now_utc.astimezone(tz).date()` | Stdlib `zoneinfo`-based conversion; correct across DST transitions without a third-party dependency |
| 27 | Default timezone | UTC, supplied by the caller (ticket 10's settings / ticket 03's `user_settings` default), not hardcoded inside this module | Matches master PRD: "default UTC when unset" is a *settings* default, not a scheduling-module concern — keeps this module timezone-agnostic |

## Persistence helper

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 28 | Signature | `apply_grade_to_card(session: Session, card: Card, grade: Grade, now_utc: datetime, tz: ZoneInfo) -> Review` | Takes the ORM session, the card row, and the same explicit `now_utc`/`tz` inputs as the pure functions — no hidden clock reads here either |
| 29 | Behavior | 1) capture `prev_interval_days = card.interval_days`; 2) `today = today_in_tz(now_utc, tz)`; 3) `result = apply_sm2(card.ease_factor, card.interval_days, card.repetitions, grade, today)`; 4) write `result.ease_factor/interval_days/repetitions/due_date` onto `card`, and `card.last_reviewed_at = now_utc`; 5) construct and `session.add()` a `Review(card_id=card.id, grade=grade, reviewed_at=now_utc, prev_interval_days=prev_interval_days, new_interval_days=result.interval_days)`; 6) return the `Review` (not yet committed — commit is the caller's/route's responsibility, consistent with the rest of the codebase's session handling) | Single, explicit, linear sequence — easy to test against the ticket-02 DB harness without needing to also stand up HTTP routes (which don't exist until ticket 09) |
| 30 | No I/O beyond the passed-in `session` | The helper does not query for the card (caller passes the already-loaded `Card` row) and does not commit/flush | Keeps the helper a thin, testable seam; avoids assuming a particular transaction-boundary policy that later tickets (09) may want to control (e.g. commit only after a full grading HTTP request succeeds) |

## Module location

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 31 | File | `src/memory_ai/scheduling.py` | Follows the existing flat `src/memory_ai/*.py` layout (`config.py`, `database.py`, `models.py`); no package structure exists yet and one small pure module doesn't warrant creating one |
| 32 | Contents | `Grade` (Literal), `SM2Result` (dataclass), `apply_sm2()` (pure), `today_in_tz()` (pure boundary), `apply_grade_to_card()` (persistence helper) | Everything SM-2-related lives in one module per the plan's "pure module" framing; the persistence helper is the only piece that touches the `Session`/`Card`/`Review` ORM types |

## Notes

- This ticket has zero UI/route surface — grading buttons, the review-queue endpoints, and calling
  `apply_grade_to_card` from an actual HTTP request are ticket 09's job. This ticket delivers only
  the pure module and its exhaustive tests plus the DB-harness-backed test of the persistence
  helper.
- Worked example (useful as a sanity check when writing the exhaustive test table): a brand-new
  card (`ease_factor=2.5, interval_days=0, repetitions=0`) graded **Good** three times in a row on
  consecutive days: rep1 → `interval=1, ease=2.5`; rep2 → `interval=6, ease=2.5`; rep3 →
  `interval=round_half_up(6*2.5)=15, ease=2.5`. Graded **Again** on the 4th review instead of Good:
  `repetitions=0, interval=1, ease=2.5-0.8=1.7` (ease floored only if it would otherwise dip below
  1.3 — here it doesn't).
