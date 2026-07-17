# 09 — Review Flows

**Depends on:** 07 and 08. **Goal:** the global daily review and per-subject drill, sharing one schedule.

## Build
- **Global daily review:** query cards where `due_date <= today` (user's timezone midnight) across all
  subjects, ordered **most-overdue first**, limited to the user's **daily cap** (`min(cap, due)`).
  Overflow cards remain due (pile up).
- **Per-subject review:** same query filtered to one subject, **uncapped** (all due cards).
- Both views grade a card with **Again/Hard/Good/Easy**, calling the ticket-08 scheduler, which updates the
  single `due_date` — so the two views stay in sync automatically (no separate copies).
- Jinja + HTMX review UI: show a card front, reveal back, four grade buttons, advance to next.
- Timezone-aware "today" from `user_settings.timezone` (default UTC).

## Definition of done
- Global review respects the cap and ordering; subject review is uncapped.
- Grading in either view updates the same schedule (verified: a card graded in subject review is no longer
  due in the global review).

## Test seam (HTTP)
- Cap enforcement + most-overdue ordering; subject-review uncapped; **sync test**: grade in one view,
  assert the other view reflects the new due_date; timezone boundary correctness.
