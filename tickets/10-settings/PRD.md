# PRD: Ticket 10 — Settings

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Ticket 09 (review-flows) reads `user_settings.daily_review_cap` and `user_settings.timezone` on
every review request, but nothing lets a user change those values after the defaults are created
at registration (ticket 03). Without a way to edit them, every user is permanently stuck with
their signup-time daily cap and timezone, which breaks the "settings apply immediately to the
next review" promise in the master PRD's Settings user stories (38-40).

## Solution

A single settings page (Jinja + HTMX) that shows the current `daily_review_cap` and `timezone`
for the logged-in user and lets them update either or both in one form submission. The submit
handler validates both fields server-side — `daily_review_cap` must be an integer in `1..500`,
`timezone` must be a valid IANA zone name per Python's `zoneinfo.available_timezones()` — and
either persists both changes in a single UPDATE to the user's `user_settings` row, or rejects the
whole submission and re-renders the form with inline errors, applying nothing. Because ticket 09's
review queries read `user_settings` fresh on every request, a successful save is visible on the
very next review page load with no separate cache/invalidation step.

## User Stories

1. As a user, I want to view my current daily review cap and timezone on a settings page, so that I know what's currently configured before changing anything.
2. As a user, I want to set my daily review cap, so that I control how many cards the global daily review serves me at once.
3. As a user, I want to set my timezone, so that the "due today" boundary matches where I live.
4. As a user, I want my settings to persist and apply immediately to my next review, so that changes take effect predictably without a delay or extra step.
5. As a user, I want a clear inline error if I enter a daily review cap that's out of range, so that I understand why my change wasn't saved.
6. As a user, I want a clear inline error if I enter a timezone that isn't a recognized name, so that I understand why my change wasn't saved.
7. As a user, I want an invalid submission to change nothing (neither field), so that I never end up with a half-updated, inconsistent settings state.
8. As a user, I want to pick my timezone from a list of valid options rather than guessing a free-text name, so that I don't have to know the exact IANA spelling.
9. As a user, I want the settings form to update inline via HTMX (no full page reload) whether the save succeeds or fails, so that the interaction feels consistent with the rest of the app (auth/hierarchy forms).
10. As the developer, I want validation to live in application code rather than a DB constraint, so that error messages stay friendly and validation logic can change without a migration.

## Implementation Decisions

- **`daily_review_cap` bounds:** integer, `1..500` inclusive, enforced in the route handler before
  any DB write. Out-of-range or non-integer input is rejected with an inline error; nothing is
  written.
- **`timezone` validation:** the submitted value must be a member of
  `zoneinfo.available_timezones()` (Python stdlib, no new dependency). The form presents this same
  set, sorted, as a `<select>` so the user picks from valid names rather than free-typing an IANA
  string.
- **Persistence:** both fields are validated together before any write; on success, a single
  `UPDATE user_settings SET daily_review_cap = ..., timezone = ..., updated_at = now() WHERE
  user_id = :user_id` commits both changes atomically. On any validation failure, no UPDATE is
  issued — the handler re-renders the form partial with the submitted (invalid) values and inline
  error text next to the offending field(s), leaving the persisted row untouched.
- **Route shape:** `GET /settings` renders the full settings page (current values pre-filled).
  `POST /settings` is an HTMX partial endpoint: on success it returns the re-rendered form partial
  with a success indicator and the new persisted values; on failure it returns the same partial
  with inline error text and the user's submitted (rejected) values, so a fixable typo doesn't
  require re-entering the other field.
- **Immediate effect:** no cache or invalidation step exists or is needed — ticket 09's
  `get_due_cards(...)` and its timezone-boundary resolution read `user_settings` directly on each
  review request, so a committed change is visible on the very next `GET /review/...` call.
- **Scope:** this ticket only builds the settings page and its GET/POST routes. It does not modify
  ticket 09's review-query code; it only changes the `user_settings` values those queries read.
  No new database migration — `user_settings.daily_review_cap` and `user_settings.timezone`
  already exist (ticket 02, `src/memory_ai/models.py`), both `NOT NULL`.

## Testing Decisions

- **What makes a good test:** asserts externally observable HTTP behavior — status codes, rendered
  form state (current values, inline error text), and DB state (`user_settings` row before/after) —
  not `zoneinfo` internals or ORM query internals.
- **Seam:** the HTTP seam established by ticket 02's test harness (FastAPI `TestClient` + real
  Postgres via testcontainers, transaction-rolled-back per test). No new seam. Where ticket 09 has
  landed, tests may also assert end-to-end effect (cap change alters the count returned by the
  global review route; timezone change shifts which cards count as due-today) at the same HTTP
  seam — this is the ticket's defining test seam per plan.md.
- **Modules tested:**
  - `GET /settings` renders the current persisted `daily_review_cap`/`timezone`.
  - `POST /settings` happy path: valid cap + valid timezone persists both and the response reflects
    the new values.
  - `POST /settings` cap out of range (e.g. `0`, `501`, non-numeric): rejected, inline error,
    `user_settings` row unchanged.
  - `POST /settings` invalid timezone (not in `zoneinfo.available_timezones()`): rejected, inline
    error, `user_settings` row unchanged.
  - `POST /settings` with one valid field and one invalid field: neither field is persisted (no
    partial apply).
  - Cross-ticket (once 09 lands): updating the cap changes the number of cards `GET
    /review/global` returns next; updating the timezone shifts which cards are counted as due
    today at the boundary.
- **Prior art:** ticket 03's auth-form testing pattern (HTTP-level assertions on inline validation
  errors and DB state) and ticket 02's test harness/fixtures.

## Out of Scope

- Any settings beyond `daily_review_cap` and `timezone` (e.g. notification preferences, theme,
  account/email/password changes — those belong to ticket 03's auth surface, not this ticket).
- A curated/shortened timezone list — the full `zoneinfo.available_timezones()` set is presented
  as-is (see decisions.md #7).
- Per-field/autosave submission — the two fields are saved together as one form (decisions.md #3).
- Any change to how ticket 09's review queries are structured — this ticket only changes the data
  those queries read, not the query code itself.
- Settings audit history / change log.

## Further Notes

- This ticket depends on ticket 09 (review-flows) for its "definition of done" acceptance
  criteria (cap change alters global review count; timezone change shifts the due-today boundary),
  but the settings page and validation logic themselves have no code dependency on ticket 09's
  routes — only on the `user_settings` table (ticket 02) and the `current_user` auth dependency
  (ticket 03). The settings page and its validation can be built and tested independently; only
  the cross-ticket "effect" assertions require ticket 09 to have landed.
- `user_settings` rows are created at registration (ticket 03) with sane defaults, so every
  logged-in user reaching `/settings` always has a row to read/update — no "settings not yet
  initialized" state to handle.
