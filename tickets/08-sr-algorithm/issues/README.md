# Ticket 08 — SR Algorithm: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#56](https://github.com/dionferns/Memory-AI/issues/56) | pure SM-2 module + exhaustive unit tests | AFK | None | ready-for-agent | ⏳ Open |
| 2 | [#59](https://github.com/dionferns/Memory-AI/issues/59) | persistence helper + reviews-row writing | AFK | #56 | ready-for-agent | ⏳ Open |

## Suggested implementation order

#56 → #59

#56 is the tracer bullet: it delivers `apply_sm2` and `today_in_tz` — the two pure, I/O-free
functions that implement the locked SM-2 formulas (grade→quality mapping, ease update/floor,
interval growth, Again-reset, round-half-up rounding) and the tz-aware due-date boundary, backed by
an exhaustive unit-test table. #59 is a thin composition on top: it adds `apply_grade_to_card`, which
calls #56's two functions, writes the result onto a `Card` row, and creates a `Review` audit row,
tested against ticket 02's DB harness instead of as a pure-unit test.

Only two slices instead of three, per the PRD's Further Notes: the persistence helper is a two-line
composition of the pure functions, so splitting the boundary-function and persistence-helper work
into separate issues would create artificial blocking with no parallelism benefit — they're merged
into #59.

## Notes

- No HITL issues this ticket — both slices are fully AFK-gradable (pure-function/DB-harness
  assertions, no product judgment calls).
- Neither issue touches any HTTP route or template; this ticket is consumed by ticket 09
  (review-flows), which is out of scope here.
