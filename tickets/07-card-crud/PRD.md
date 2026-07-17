# PRD: Ticket 07 — Card Management (CRUD)

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Ticket 06 generates flashcards from a source via an LLM, and LLMs make mistakes: a front/back pair
can be inaccurate, awkwardly worded, or simply redundant with another card. Right now there is no
way for a user to see what was generated, fix a wrong card, or remove one they don't want. Every
card a user studies (starting with ticket 09's review flows) has to first pass through the user's
own quality control, so a working view/edit/delete surface — correctly scoped to the owning user
and safe against corrupting a card's scheduling state — has to exist before review can be trusted.

## Solution

Two Jinja+HTMX list views — per-source (`GET /sources/{source_id}/cards`, the primary entry point
right after ticket 06's generation completes) and per-folder (`GET /folders/{folder_id}/cards`, an
aggregate across every source in that folder) — render every card's front/back. Each card supports
inline HTMX edit (swap to an editable front/back form, submit via `PATCH /cards/{card_id}`) and
inline HTMX delete (swap to a "Confirm delete? / Cancel" pair, then `DELETE /cards/{card_id}`
removes the row from the DOM). Edit only ever writes `front`/`back`; every SM-2 scheduling column
(`ease_factor`, `interval_days`, `repetitions`, `due_date`, `last_reviewed_at`) is left untouched.
Delete relies on ticket 02's existing DB-level `ON DELETE CASCADE` to remove the card's `reviews`
rows. Every route resolves ownership through the `user → subject → folder → source → card` chain
via the `current_user` dependency from ticket 03, and 404s if the resolved card isn't the
requesting user's.

## User Stories

1. As a user, I want to view all cards generated from a source, so that I can check their quality
   right after conversion.
2. As a user, I want to view all cards across every source within a folder, so that I can browse
   everything I've accumulated on a topic without picking a source first.
3. As a user, I want each card's front and back both shown in the list, so that I can judge card
   quality without opening anything else.
4. As a user, I want to edit a card's front or back inline, so that I can fix an inaccurate
   AI-generated card without leaving the list.
5. As a user, I want a clear inline error if I try to save an empty front or back, so that I don't
   accidentally create a useless card.
6. As a user, I want an edit to only ever change what's shown on the card, so that fixing a typo
   never resets or corrupts my review progress on that card.
7. As a user, I want to delete a card, so that I can remove cards that are wrong or redundant.
8. As a user, I want a confirm step before a delete takes effect, so that I don't lose a card to a
   misclick.
9. As a user, I want a card's review history removed along with the card, so that no orphaned data
   lingers after I delete it.
10. As a user, I want to only ever see, edit, or delete my own cards, so that my study material
    stays private and I can't be affected by another user's data.
11. As a user attempting to reach or mutate another user's card (e.g. by guessing an ID in the
    URL), I want a not-found response rather than a permission error, so that another user's data
    isn't confirmed to exist.
12. As the developer, I want edit/delete to reuse the `current_user` dependency and HTMX-aware
    redirect behavior established in ticket 03, so that auth handling stays consistent across the
    app.

## Implementation Decisions

- **Listing:** two read routes, both scoped to `current_user` via the ownership join chain —
  `GET /sources/{source_id}/cards` (primary; the natural place to review freshly-generated cards)
  and `GET /folders/{folder_id}/cards` (aggregate across all sources in the folder). Both order by
  `created_at ascending`; no pagination in v1.
- **Edit:** `PATCH /cards/{card_id}`, HTMX partial. `front`/`back` both required, rejected with an
  inline validation error if empty/whitespace-only after trimming; no app-level max length beyond
  the existing `TEXT` column. The handler only ever writes `front`/`back` — `ease_factor`,
  `interval_days`, `repetitions`, `due_date`, `last_reviewed_at` are never part of the update
  payload or touched by the route.
- **Delete:** `DELETE /cards/{card_id}`, HTMX partial, two-step inline confirm (no modal, no
  native JS `confirm()`). Confirming issues a single `DELETE` on the `cards` row; the `reviews`
  rows are removed by the DB-level `ON DELETE CASCADE` FK already established in ticket 02 — no
  app-level cleanup code.
- **Authorization:** every route resolves the card (and, for listing, the source/folder) through
  the `user → subject → folder → source → card` chain and returns `404` (not `403`) if the
  resolved resource isn't owned by `current_user`, avoiding confirming another user's resource
  exists.
- **UI:** Jinja templates + HTMX, consistent with tickets 03/04's server-rendered, no-SPA
  architecture. Edit and delete are both inline partial swaps — no full page reload on either
  action.

## Testing Decisions

- **What makes a good test:** asserts externally observable HTTP behavior — status codes, response
  body/HTML fragment content for HTMX partials, and DB state (card row updated/removed, `reviews`
  rows removed via cascade) — not ORM internals.
- **Seam:** the HTTP seam established by ticket 02's test harness (FastAPI `TestClient` + real
  Postgres via testcontainers, transaction-rolled-back per test), the same seam tickets 03+ use. No
  new seam.
- **Modules tested:** per-source listing (happy path, empty source, cross-user 404), per-folder
  listing (happy path, aggregates across sources, cross-user 404), edit (happy path preserves all
  scheduling fields exactly, empty front/back rejected, cross-user 404), delete (happy path removes
  card and cascades to its `reviews` rows, cross-user 404).
- **Prior art:** ticket 02's test harness/fixtures and ticket 03's cross-user/ownership test
  patterns; this ticket is the first to assert that an update leaves a specific set of columns
  byte-for-byte unchanged (the scheduling fields).

## Out of Scope

- Bulk edit/delete, undo/soft-delete, or a trash/recovery flow for deleted cards.
- Card creation by hand (all v1 cards originate from ticket 06's AI generation).
- Pagination, search, or filtering within a card list beyond the source/folder scope.
- Any change to a card's scheduling state as a side effect of edit — that only ever happens via
  ticket 09's review flow.
- Reordering cards within a list.

## Further Notes

- This ticket depends on ticket 06 (cards must exist before there's anything to view/edit/delete)
  and, transitively, on ticket 04's folder/subject ownership chain and ticket 02's schema/cascade
  behavior. Ticket 06 was still being planned in parallel with this ticket and had not yet
  published issues at PRD time; this PRD references it in prose rather than by issue number.
- The per-source and per-folder list views share the same card partial template/fragment so edit
  and delete behave identically regardless of which list a card is viewed from.
