# 08 — SM-2 Scheduler

**Depends on:** 02 (models only). Can be built in parallel with 05–07. **Goal:** the correctness-critical
spaced-repetition core as a pure, exhaustively-tested module.

## Build
- A **pure module**: `(card scheduling state, grade) → (new interval_days, ease_factor, repetitions, due_date)`
  implementing **SM-2**.
- Four grades **Again / Hard / Good / Easy** mapped to SM-2 quality values.
- First-review behavior, ease-factor floor, interval growth, and Again-resets handled per SM-2.
- A persistence helper that, given a card + grade + "now", applies the pure result to the card row and
  writes a `reviews` audit row (prev/new interval). No HTTP here.
- "Due today" computed against a supplied timezone-aware boundary (the scheduler takes `now`/tz as input,
  never reads a global clock — keeps it deterministic and testable).

## Definition of done
- The pure function passes an exhaustive table of transitions.
- Applying a grade updates the card and appends a `reviews` row.

## Test seam (pure unit)
- Exhaustive `(state, grade) → new state` table: first review, each button, due-date math, ease floor,
  Again reset. Persistence helper tested against the DB harness.
