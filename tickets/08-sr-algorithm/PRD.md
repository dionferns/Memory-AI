# PRD: Ticket 08 — SM-2 Scheduler

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Every review flow in the app (global capped review, per-subject uncapped review, and the
written-answer-feedback ticket's grading path) needs a single, correct, deterministic way to turn
"the user graded this card X" into "here is the card's new schedule." Getting SM-2 wrong — off-by-one
intervals, a wrong ease floor, a due-date boundary that reads a global clock instead of the caller's
timezone — would silently corrupt every user's review schedule and be hard to notice after the fact,
since bad scheduling looks like "the app is annoying" rather than an obvious bug. This ticket delivers
that logic as an isolated, exhaustively-tested pure module, decoupled from any HTTP surface, so it can
be verified completely before any review UI depends on it.

## Solution

A single new module, `src/memory_ai/scheduling.py`, containing:
- `apply_sm2(ease_factor, interval_days, repetitions, grade, today) -> SM2Result` — a pure function
  implementing classic SM-2 with the exact grade→quality mapping, ease-factor formula/floor, and
  interval-growth rules locked in `decisions.md`. No I/O, no clock reads.
- `today_in_tz(now_utc, tz) -> date` — a pure boundary function that resolves "today" for a given
  tz-aware instant and timezone. Also has no I/O and never reads a global clock.
- `apply_grade_to_card(session, card, grade, now_utc, tz) -> Review` — a thin persistence helper that
  composes the two pure functions, writes the result onto an already-loaded `Card` ORM row, and
  constructs (but does not commit) a `Review` audit row.

This ticket has no routes, no templates, and no dependency on auth/hierarchy/upload/flashcards — it
only depends on ticket 02's `Card`/`Review` models. Ticket 09 (review-flows) is the first consumer
that wires grading buttons and review queues to this module.

## User Stories

1. As a user, I want grading a card Again to bring it back soon (tomorrow), so that struggling
   material gets reinforced quickly.
2. As a user, I want grading a card Easy to push it far out, so that material I already know well
   doesn't waste my review time.
3. As a user, I want Hard/Good/Easy to all count as a "pass" that grows the interval (not just Easy),
   so that steady, unremarkable recall still makes progress toward longer intervals.
4. As a user, I want a card's difficulty (ease factor) to keep adapting even when I hit Again, so
   that a card I keep failing gets scheduled more conservatively over time rather than resetting to
   "as if new" on every failure.
5. As a user, I want "due today" computed against my own timezone's midnight (carried over from the
   master PRD's story #35), so that my day boundary is correct — this ticket delivers the underlying
   `today_in_tz` boundary function that later tickets' due-count queries will use.
6. As a user, I want my review history recorded (master PRD story #37), so that the schedule is
   auditable and future stats are possible — every grading call produces a `reviews` row with the
   before/after interval.
7. As the developer, I want the scheduling math implemented as a pure function with no I/O, so that
   every transition (first review, each grade, ease floor, Again-reset) can be exhaustively unit
   tested without a database or HTTP layer.
8. As the developer, I want the persistence helper to take an already-loaded `Card` row and explicit
   `now`/timezone inputs rather than querying or reading a clock itself, so that it stays a thin,
   fully-testable seam that later tickets (09's grading route) can call from within their own
   transaction/request-scoping without surprises.

## Implementation Decisions

Full detail and rationale for every branch below is in [decisions.md](decisions.md); this section
restates the exact formulas as the ticket's implementation contract.

**Grade → quality mapping** (never exposed to the user; the four UI buttons map to it internally):

| Grade | Quality (`q`) | SM-2 branch |
|-------|------|-------------|
| Again | 0 | fail (reset) |
| Hard | 3 | pass |
| Good | 4 | pass |
| Easy | 5 | pass |

**Ease-factor update** — applied on every grade, including Again:

```
EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
EF' = max(EF', 1.3)   # floor, no ceiling
```

No additional rounding beyond the floor; stored as the raw `float`.

**Repetitions / interval update:**

| Case | `repetitions` | `interval_days` |
|------|---------------|------------------|
| Again (`q<3`) | `→ 0` | `→ 1` |
| Pass, new `repetitions == 1` | `+1` | `→ 1` |
| Pass, new `repetitions == 2` | `+1` | `→ 6` |
| Pass, new `repetitions >= 3` | `+1` | `→ round_half_up(prev_interval_days * new_ease_factor)` |

Round-half-up (`floor(x + 0.5)`), not Python's banker's-rounding `round()`. Minimum interval is
always `1` day by construction; no maximum interval is enforced.

**`due_date` computation:** `due_date = today + timedelta(days=new_interval_days)`, computed inside
`apply_sm2` (it takes `today: date` directly — timezone resolution already happened via
`today_in_tz` before this function is called).

**Timezone boundary:** `today_in_tz(now_utc: datetime, tz: ZoneInfo) -> date` implemented as
`now_utc.astimezone(tz).date()`. Raises if `now_utc` is naive. No default-timezone logic lives here —
the caller (ultimately, ticket 10's user settings, defaulting to UTC per the master PRD) supplies
`tz`.

**Persistence helper:** `apply_grade_to_card(session, card, grade, now_utc, tz) -> Review` —
captures `prev_interval_days` before mutation, resolves `today`, calls `apply_sm2`, writes the result
onto `card` (`ease_factor`, `interval_days`, `repetitions`, `due_date`, plus `last_reviewed_at =
now_utc`), constructs a `Review(card_id, grade, reviewed_at=now_utc, prev_interval_days,
new_interval_days)`, adds it to the session, and returns it. Does not commit or flush — that
transaction boundary belongs to the caller (ticket 09's grading route).

**Module contents:** `Grade` (`Literal["again", "hard", "good", "easy"]`), `SM2Result` (frozen
dataclass/NamedTuple with `ease_factor`, `interval_days`, `repetitions`, `due_date`), `apply_sm2()`,
`today_in_tz()`, `apply_grade_to_card()` — all in `src/memory_ai/scheduling.py`, matching the existing
flat `src/memory_ai/*.py` layout.

## Testing Decisions

This ticket's primary seam, per the master PRD's testing strategy, is the **SM-2 pure-function
seam**: exhaustive unit tests over `(state, grade) → new state`, no database or HTTP involved. A
secondary, smaller seam covers the persistence helper against ticket 02's DB test harness.

**Exhaustive `apply_sm2` transition table to cover:**

- **First review from a brand-new card** (`ease_factor=2.5, interval_days=0, repetitions=0`) for
  each of the four grades — asserts `repetitions`/`interval_days` land correctly regardless of
  starting `interval_days=0`.
- **Each grade's ease-factor delta** in isolation, from a neutral starting ease (`2.5`): Again
  (`→1.7`), Hard (`→2.36`), Good (`→2.5`, unchanged), Easy (`→2.6`) — verifies the formula's four
  quality inputs independently of the interval/repetitions branch.
- **Ease floor enforcement:** a card already near the floor (e.g. `ease_factor=1.35`) graded Again
  or Hard enough times that the raw formula result would go below `1.3` — asserts the floored value,
  not the raw formula output, is what's returned.
- **`repetitions == 1 → interval == 1`** and **`repetitions == 2 → interval == 6`** transitions,
  independent of which pass grade (Hard/Good/Easy) triggered them — asserts Hard is not treated
  differently from Good/Easy for interval growth, only for the ease delta.
- **`repetitions >= 3` growth formula**, including a case chosen so the raw
  `prev_interval_days * ease_factor` lands exactly on `x.5` — asserts round-half-up, not
  Python's default banker's-rounding, is used.
- **Again reset from deep repetition state** (e.g. `repetitions=5, interval_days=40`, ease well
  above floor) — asserts `repetitions → 0`, `interval_days → 1`, and the ease factor is still
  reduced by the formula (not reset to `2.5` and not left at its pre-Again value).
- **Consecutive-grade sequences** (e.g. Good→Good→Good; Good→Good→Again→Good) — asserts state
  threads correctly across calls, since `apply_sm2` is called repeatedly with each call's output
  feeding the next call's input in real usage.
- **`due_date` arithmetic**: for a fixed `today`, asserts `due_date == today + timedelta(days=new_interval_days)`
  for at least one case per interval branch (1, 6, and a `>=3`-repetition growth case).
- **`today_in_tz` boundary cases**: a UTC instant that is "tomorrow" in a positive-offset timezone
  and "yesterday" in a negative-offset one (e.g. `2026-07-17T23:30:00Z` in `Pacific/Kiritimati`
  (+14) vs. `Pacific/Niue` (-11)); a UTC instant near a DST transition in a DST-observing timezone;
  a naive `now_utc` input raises rather than silently assuming UTC.

**Persistence helper (`apply_grade_to_card`) test seam:** ticket 02's DB harness (real test Postgres,
transaction-rolled-back per test). Asserts: the `Card` row's four scheduled fields plus
`last_reviewed_at` are updated to match a hand-computed `apply_sm2` result; a `Review` row is created
with the correct `card_id`, `grade`, `reviewed_at`, `prev_interval_days` (the card's interval
*before* this call), and `new_interval_days`; calling it twice in sequence (simulating two real
reviews) produces two `Review` rows and a `Card` state matching two chained `apply_sm2` calls.

**What makes a good test here:** asserts the exact numeric output of the pure functions against
hand-computed expected values (not "some interval increased"), since this is the one module in the
whole app where a subtly wrong number is the entire bug surface. Tests should read as a literal
transcription of the formulas in decisions.md so a future formula change is caught by name, not by
approximation.

**Prior art:** ticket 02's DB harness (test Postgres via testcontainers, rollback-per-test fixture)
for the persistence-helper tests; this ticket introduces the project's first pure-unit-test seam
(no DB, no HTTP client) alongside it.

## Out of Scope

- Any HTTP route, template, or UI — grading buttons and review-queue endpoints belong to ticket 09.
- Global-cap / per-subject due-card query logic — ticket 09.
- User-settings-driven timezone/cap values — ticket 10; this ticket's functions accept `tz` as a
  plain parameter and have no knowledge of `user_settings`.
- FSRS or any non-SM-2 scheduling algorithm (master PRD: SM-2 only for v1).
- An ease-factor ceiling or an interval cap — neither exists in classic SM-2 and neither is
  requested by any user story.
- Undo/redo of a grading action, or editing a past `reviews` row.

## Further Notes

- This ticket is intentionally "one cohesive unit" rather than several thin vertical slices — the
  three functions in `scheduling.py` only make sense together (the persistence helper is a two-line
  composition of the two pure functions), and splitting them into separate issues would create
  artificial inter-issue blocking for no parallelism benefit. `/to-issues` reflects this with a small
  number of larger slices rather than many thin ones.
- Ticket 09 (review-flows) is the first real consumer and is where `apply_grade_to_card` gets called
  from an actual grading HTTP route inside a request transaction, and where `today_in_tz` gets called
  with a real user's `user_settings.timezone`.
- The worked examples and exact floating-point deltas in `decisions.md`'s Notes section are meant to
  be used directly as test fixtures/assertions when this ticket's issues are implemented.
