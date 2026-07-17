# 09 — Review Flows: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (no open questions for the user;
resolved by the agent's recommendation, per instruction, against master
[PRD.md](../../PRD.md) and the plan.md's of tickets 07 and 08). Source of truth for the
review-flows ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Ordering | `ORDER BY due_date ASC` (oldest due date first = most-overdue first) | Directly matches PRD story 30 ("most-overdue cards prioritized within the cap") and plan.md's "most-overdue first" |
| 2 | Tie-breaking (same `due_date`) | Secondary `ORDER BY id ASC` | Deterministic and stable across repeated queries/tests (e.g. pagination-free "first N") with zero extra schema; no product requirement favors any other tiebreak, so pick the cheapest deterministic one |
| 3 | Cap application | `LIMIT min(cap, due_count)` expressed simply as SQL `LIMIT :cap` (a `LIMIT` larger than the result set is a no-op, so no need to pre-compute `due_count` in Python) | Lets Postgres handle the "give me at most N" semantics directly; avoids a redundant `COUNT(*)` query on every review page load |
| 4 | Shared query code | A single function, `get_due_cards(session, user_id, subject_id=None, limit=None)` in a new `memory_ai/reviews/queries.py`, used by both the global route (`subject_id=None, limit=cap`) and the subject route (`subject_id=<id>, limit=None`) | Per PRD.md line 116-117 "global and subject review are different queries over the same rows, so their schedules cannot drift" — enforced by construction: one function, two call sites, no duplicated SQL to drift apart |
| 5 | Grading UI interaction shape | HTMX partial swap, not full page reload: `GET /review/{scope}` renders the session shell + first card front; a "Show answer" button does an HTMX swap to reveal the back + 4 grade buttons; each grade button `POST`s to `/review/{scope}/{card_id}/grade`, and the response is the *next* card's front (or the empty-state partial), swapped into the same container | Smoothest UX for a rapid card-after-card loop (per PRD's Jinja+HTMX architecture already established in ticket 03); avoids a full-page round trip per card, which would be noticeably slower for a session of dozens of cards |
| 6 | Zero-due-cards empty state | Render a dedicated "You're all caught up" partial/page (same template for both global and subject scope, parameterized by scope name) instead of an empty list or a redirect | Matches PRD story 32 framing (overflow cards "remain due", not hidden) — the empty state is a legitimate, expected outcome, not an error, so it gets its own friendly copy rather than a bare empty table |
| 7 | Timezone-boundary integration | Call ticket 08's `now`/tz-aware "due" boundary helper (exact function name/signature TBD — not yet in `tickets/08-sr-algorithm/decisions.md` as of this writing; ticket 08 was still mid-planning). Planned call shape: `get_due_cards(..., as_of=<tz-aware "today" boundary from ticket 08>)`, where ticket 09 is responsible only for resolving `user_settings.timezone` (default UTC per PRD story 35) and passing that boundary in — ticket 08 owns the actual midnight-boundary math per its plan.md ("scheduler takes now/tz as input, never reads a global clock") | Keeps the tz-math correctness-critical logic single-sourced in ticket 08 (already scoped there); ticket 09 only supplies the input and consumes the query result — no timezone arithmetic duplicated here |

## TODO (confirm once ticket 08 lands)

- **Confirm exact call signature** of ticket 08's pure/persistence helpers once
  `tickets/08-sr-algorithm/decisions.md` exists on `main`:
  - The "due" boundary helper (name, params, return type) referenced in decision #7.
  - The grading/persistence helper that `POST /review/{scope}/{card_id}/grade` will call
    (expected shape per 08's plan.md: `(card scheduling state, grade, now) → persists new
    interval_days/ease_factor/repetitions/due_date + writes a reviews row`; exact function name
    and whether it takes a `Card` ORM instance vs. discrete fields is unconfirmed).
  - If the actual signature differs meaningfully from what's assumed here (e.g. it returns a
    result object the caller must apply, rather than mutating/persisting itself), the
    grading route in ticket 09's issues will need a one-line signature update — flagged here
    so it isn't rediscovered as a surprise.

## Notes

- Tickets 07 (card-crud) and 08 (sr-algorithm) are both being planned in parallel as of this
  writing and have no `decisions.md` on `main` yet. This ticket's PRD and issues are written
  against their `plan.md` descriptions and the master PRD.md's spaced-repetition section
  (PRD.md lines 135-140), not against confirmed function signatures.
- Ticket 09 needs card row access (title/front/back) from ticket 07's card model, and the
  `due_date`/scheduling fields established by ticket 02 (`Card` model) and mutated by ticket 08.
  No new schema is introduced by ticket 09 — it is purely a query + UI layer over existing
  `Card`/`user_settings` state.
