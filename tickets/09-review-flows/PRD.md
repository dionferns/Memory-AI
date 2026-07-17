# PRD: Ticket 09 — Review Flows

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Once cards exist (ticket 07) and the SM-2 scheduler exists as a pure module (ticket 08), a user
still has no way to actually *study* — there is no page that surfaces which cards are due, no way
to grade a card, and no guarantee that "how due a card is" agrees across the two ways a user might
study it: a single daily habit across every subject, or a focused drill on one subject before an
exam. Without a single shared source of truth for "what's due," those two views could silently
diverge (a card graded in one still showing as due in the other), which would undermine the whole
premise of spaced repetition. This ticket builds both review surfaces on top of one shared query,
so they provably cannot drift.

## Solution

A single `get_due_cards(session, user_id, subject_id=None, limit=None)` query function is the sole
read path for "what's due," ordered oldest-`due_date`-first (most overdue first, `id` as a
deterministic tiebreak). The **global daily review** (`GET /review`) calls it with
`subject_id=None, limit=<user's daily_review_cap>`; the **subject review** (`GET
/review/subjects/{subject_id}`) calls it with `subject_id=<id>, limit=None` (uncapped). Both
routes render the same Jinja+HTMX review shell: a card front, a "Show answer" action that reveals
the back plus four grade buttons (Again/Hard/Good/Easy), and grading `POST`s to a shared
`/review/{scope}/{card_id}/grade` endpoint that calls ticket 08's persistence helper, updates the
card's single `due_date` row, and HTMX-swaps in the next due card (or the empty state) without a
full page reload. Because both views read through the same function and write through the same
scheduler, grading a card in either view is immediately reflected in the other — there is no
separate "subject due list" to fall out of sync. "Due today" is evaluated against a tz-aware
boundary derived from `user_settings.timezone` (default UTC), computed by ticket 08's clock-input
scheduler and passed into the query as the comparison boundary.

## User Stories

### Global daily review

1. As a user, I want a daily review that gives me cards due today from across all my subjects, so that I keep a single study habit. (PRD.md story 28)
2. As a user, I want the daily review limited to my configured daily cap, so that I am not overwhelmed on heavy days. (PRD.md story 29)
3. As a user, I want the most-overdue cards prioritized within the cap, so that I address my biggest gaps first. (PRD.md story 30)
4. As a user, I want overflow due cards (beyond the cap) to remain due on later days rather than silently dropped, so that nothing I owe review on disappears. (PRD.md story 32)
5. As a user, when I have no cards due, I want a clear "all caught up" message instead of a blank or confusing page, so that I know I'm done for today.

### Subject review (drill)

6. As a user, I want to review all due cards within a single subject, ignoring my global cap, so that I can cram before an exam. (PRD.md story 33)
7. As a user, when a subject has no due cards, I want a clear "nothing due in this subject" message, so that I know there's nothing to drill right now.

### Sync guarantee

8. As a user, I want grading a card in subject review to update the same schedule as the global review (and vice versa), so that the two views never diverge and I never see a card as "due" in one place after I've already reviewed it in the other. (PRD.md story 34)

### Grading interaction

9. As a user, I want to see a card's front, then reveal its back on demand, so that I can test recall before checking the answer.
10. As a user, I want to grade my recall with one of four buttons (Again/Hard/Good/Easy), so that the schedule reflects how well I actually remembered the card.
11. As a user, I want the next due card to appear immediately after I grade, without a full page reload, so that reviewing a stack of cards feels fast and continuous.

### Timezone correctness

12. As a user, I want "due today" computed against my own timezone's midnight (default UTC if I haven't set one), so that my day boundary matches where I actually live and study. (PRD.md story 35)

## Implementation Decisions

See [decisions.md](decisions.md) for the full rationale table. Summary:

- **Ordering:** `ORDER BY due_date ASC, id ASC` — oldest due date first, `id` as a deterministic
  tiebreak for same-`due_date` cards.
- **Cap application:** a plain SQL `LIMIT :cap` on the global query; `LIMIT` is a no-op when the
  cap exceeds the due count, so no separate `COUNT(*)` is needed.
- **Single shared query function:** `get_due_cards(session, user_id, subject_id=None, limit=None)`
  in `memory_ai/reviews/queries.py` is the only place "what's due" is computed; the global route
  passes `limit=cap`, the subject route passes `subject_id=<id>` and no limit. This is the
  mechanism that makes user story 8 (the sync guarantee) true by construction rather than by
  convention.
- **Grading UI:** HTMX partial swaps, not full page reloads — `GET /review/{scope}` renders the
  session shell + first card front; "Show answer" swaps in the back + 4 grade buttons; each grade
  button `POST`s to `/review/{scope}/{card_id}/grade`, which returns the next card's front (or the
  empty-state partial) swapped into the same container.
- **Empty state:** a dedicated "all caught up" / "nothing due in this subject" partial, scoped by
  which view triggered it, rather than an empty list — framed as a legitimate, expected outcome
  matching the "overflow cards remain due, not hidden" principle.
- **Timezone boundary:** ticket 09 resolves `user_settings.timezone` (default UTC) and passes the
  resulting "today" boundary into `get_due_cards`; ticket 08 owns the actual midnight-boundary math
  per its own plan (scheduler takes `now`/tz as input, never reads a global clock). **Open TODO:**
  the exact function name/signature of ticket 08's boundary helper and persistence/grading helper
  are unconfirmed as of this writing — both tickets 07 and 08 are still mid-planning in parallel
  worktrees with no `decisions.md` on `main` yet. Ticket 09's issues are scoped against 07's and
  08's `plan.md` descriptions and the master PRD.md's spaced-repetition section; the exact call
  signature is flagged as a one-line integration risk to confirm once 08's `decisions.md` lands, not
  a blocker to writing the issues now.

## Testing Decisions

- **What makes a good test:** asserts externally observable HTTP behavior — response status,
  which cards appear in the rendered/JSON review payload and in what order, DB state of
  `due_date`/`interval_days`/etc. after grading, and cross-view consistency — not HTMX swap
  internals, template markup, or SQLAlchemy query-plan internals.
- **Seam:** the HTTP seam established by ticket 02's test harness (FastAPI `TestClient` + real
  Postgres via testcontainers, transaction-rolled-back per test), the same seam used by ticket 03
  onward. No new seam.
- **Required test — cap enforcement:** seed more due cards across subjects than the user's
  `daily_review_cap`; assert the global review returns exactly `cap` cards.
- **Required test — most-overdue ordering:** seed cards with distinct `due_date`s in the past;
  assert the global review returns them oldest-`due_date`-first.
- **Required test — subject review uncapped:** seed a subject with more due cards than the global
  cap; assert subject review returns all of them, not just `cap`.
- **Required test — sync guarantee (explicit, per plan.md):** grade a card via the subject-review
  endpoint, then assert the global-review endpoint no longer returns that card as due (and vice
  versa) — proves the two views share one schedule rather than drifting.
- **Required test — timezone boundary:** a card due exactly at a user's local midnight is
  correctly included/excluded depending on the configured `user_settings.timezone`, distinct from
  a naive UTC-only comparison (e.g. a card that would be "due" under UTC but not yet due under the
  user's own timezone, or vice versa).
- **Required test — empty state:** zero due cards in a scope returns the "all caught up" /
  "nothing due" response rather than an error or an empty-but-unlabeled list.
- **Modules tested:** `get_due_cards` (ordering, cap, subject filter, tz boundary) at the query
  level or through the HTTP seam; the grading routes (happy path, next-card advance, empty-state
  transition, cross-view sync) at the HTTP seam.
- **Prior art:** ticket 02's test harness and fixtures; ticket 03's pattern of asserting on
  HTTP status/response shape plus DB state; ticket 08's exhaustive pure-function table tests cover
  SM-2 correctness itself, so ticket 09's tests focus on query/ordering/cap/sync/tz behavior, not
  re-deriving SM-2 math.

## Out of Scope

- The SM-2 scheduling math itself (interval/ease-factor/repetitions computation) — owned entirely
  by ticket 08; this ticket only calls it.
- Card content editing/deletion — owned by ticket 07; this ticket only reads card rows to render
  them and calls ticket 08 to grade them.
- Configuring the daily cap or timezone — owned by ticket 10 (settings); this ticket reads
  `user_settings.daily_review_cap`/`timezone` but does not provide UI to change them.
- Free-text/written-answer grading — owned by ticket 11, which extends this ticket's grading path
  later.
- A "new cards per day" sub-limit separate from the daily review cap (explicitly out of scope per
  master PRD.md).
- Any non-SM-2 scheduling algorithm (e.g. FSRS) — v1 is SM-2 only per master PRD.md.
- Review history/analytics views beyond the `reviews` audit rows ticket 08 already writes.

## Further Notes

- This ticket is the first to combine ticket 07's card-reading surface with ticket 08's
  scheduling-writing surface into a single user-facing flow; it is the point where "cards exist"
  becomes "cards are actually studied."
- The single shared query function (`get_due_cards`) is the load-bearing design choice of this
  ticket: every other decision (route shape, HTMX interaction, empty state) sits on top of it, but
  the sync guarantee (user story 8) specifically depends on both routes never having their own
  independent "what's due" logic.
- Because tickets 07 and 08 were still being planned in parallel at the time this PRD was written,
  the exact scheduler/persistence-helper call signature referenced in Implementation Decisions is
  a confirm-before-merge TODO for whichever issue implements the grading route, not a design
  decision left open on ticket 09's own side.
