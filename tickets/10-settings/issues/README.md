# Ticket 10 — Settings: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#58](https://github.com/dionferns/Memory-AI/issues/58) | settings page (view + update daily_review_cap and timezone, validated) | AFK | ticket 09 (prose reference — for cross-ticket effect criteria only) | ready-for-agent | ⏳ Open |

## Suggested implementation order

Single slice — #58 is both the tracer bullet and the whole ticket.

## Why one slice instead of two

decisions.md locks a single-form, atomic-persist design (#3/#4: both `daily_review_cap` and
`timezone` are submitted and validated together; an invalid value in either field rejects the
whole submission and persists neither field). Splitting "update cap" and "update timezone" into
two separately-buildable issues would fight that design — both would touch the same `POST
/settings` route and the same `user_settings` row, and one wouldn't be usable without the other's
form-partial and validation-rejection plumbing already existing. A single vertical slice
(settings page GET + validated POST covering both fields) is the natural tracer bullet here.

## Notes

- No HITL issues this ticket.
- Ticket 09 (review-flows) had not landed a `decisions.md`/`PRD.md`/issues on `main` as of this
  writing (parallel planning); #58 is scoped so its acceptance criteria don't require ticket 09's
  code to exist — only ticket 09's own acceptance criteria (settings changes altering review
  behavior) depend on that ticket separately.
- No new database migration — `user_settings.daily_review_cap`/`timezone` already exist from
  ticket 02, and every user already has a `user_settings` row from ticket 03's registration flow.
