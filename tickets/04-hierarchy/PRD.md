# PRD: Ticket 04 — Hierarchy

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

A logged-in user (ticket 03) has an account but nowhere to put anything yet — there is no concept
of a subject or a folder, so there is no place to upload notes into, no container for cards to
belong to, and no page for the user to land on after login. Every later ticket in the ingestion
pipeline (upload, AI flashcards, card CRUD) and the review pipeline (review flows query cards by
folder/subject) needs a working, user-scoped, two-level Subject → Folder hierarchy to attach to
before any of that feature work can begin.

## Solution

Full CRUD for subjects and folders, scoped to the authenticated user via ticket 03's
`current_user` dependency, exposed through a single server-rendered `GET /subjects` page (Jinja +
HTMX) that lists a user's subjects with their folders rendered inline underneath. Subjects are
created, renamed, and deleted directly; folders are created within a subject and renamed/deleted
by id (ownership resolved via a join to their subject). Every mutation is a small HTMX round trip
that swaps in just the affected fragment — no full page reloads for create/rename, and deletes are
gated by a browser confirm dialog before the request ever fires. Deleting a subject or folder
relies entirely on the database's existing `ON DELETE CASCADE` chain to remove everything beneath
it. Any attempt to view or mutate another user's subject or folder is rejected with a 404, matching
the "don't leak existence" posture used elsewhere in the app.

## User Stories

1. As a user, I want to create a subject, so that I can group related study material (e.g. "System Design").
2. As a user, I want a clear inline error if I try to create a subject with a blank or whitespace-only name, so that I don't end up with an unusable, unlabeled subject.
3. As a user, I want a clear inline error if my subject name is unreasonably long (over 200 characters), so that pasted garbage doesn't corrupt my workspace's layout.
4. As a user, I want to be able to reuse the same subject name more than once if I want to, so that I'm not blocked by an arbitrary uniqueness rule I never asked for.
5. As a user, I want to rename a subject in place, so that I can correct or update its label without recreating it.
6. As a user, I want to cancel an in-progress rename without saving, so that an accidental click doesn't overwrite the name.
7. As a user, I want to delete a subject, so that I can remove material I no longer need.
8. As a user, I want a confirmation prompt before a subject actually gets deleted, so that I don't lose a subject (and everything inside it) from a stray click.
9. As a user, I want deleting a subject to also remove all of its folders and everything inside those folders (sources, cards), so that I never end up with orphaned data cluttering the database.
10. As a user, I want to create a folder inside one of my subjects, so that I can divide material further (e.g. "Caching" inside "System Design").
11. As a user, I want the same blank-name and length validation on folder names as on subject names, so that the rules are predictable across the hierarchy.
12. As a user, I want to rename a folder in place, so that I can reorganize as my notes grow.
13. As a user, I want to delete a folder (with the same confirmation prompt), so that I can remove material I no longer need without deleting the whole subject.
14. As a user, I want deleting a folder to also remove its sources and cards, so that I never end up with orphaned data.
15. As a user, I want to see a single page listing all my subjects, each with its folders shown underneath, so that I can navigate my material without extra clicks or page loads.
16. As a user with no subjects yet, I want to see a clear empty-state message and the create-subject form (not a blank page), so that I know what to do next.
17. As a user with a subject that has no folders yet, I want to see a clear empty-state message and the create-folder form for that subject, so that I know how to start filling it in.
18. As a user, I want my subjects and folders listed in the order I created them, so that the order is stable and predictable without needing to think about sorting.
19. As a user, I want to never be able to see, rename, or delete another user's subject or folder — including by guessing an id in the URL — so that my study material stays private.
20. As a user probing another user's subject/folder id, I want a plain "not found" response rather than a "forbidden" response, so that the app doesn't even confirm the id belongs to someone else.
21. As a user who isn't logged in, I want visiting the subjects page to redirect me to login (or, for an HTMX action, to be redirected client-side), so that the hierarchy page behaves consistently with every other protected page in the app.
22. As the developer, I want every hierarchy route to depend on the existing `current_user` dependency rather than reimplementing auth checks, so that authentication behavior stays centralized and consistent.
23. As the developer, I want folder ownership checks to go through a join on the owning subject's `user_id` (there is no `folders.user_id` column), so that authorization logic matches the actual schema rather than assuming a column that doesn't exist.
24. As the developer, I want subject/folder deletes to be a plain `DELETE` on that row with no application-level cascade logic, so that the single source of truth for cascading remains the database's `ON DELETE CASCADE` constraints from ticket 02, with no risk of the two drifting apart.
25. As the developer, I want create/rename HTMX responses to return just the changed fragment (not a full page), so that the client does the minimum work needed to reflect the change.
26. As the developer, I want a delete response to be empty with the client removing the row via its own `hx-target`/`hx-swap`, so that no unnecessary HTML is sent back for an action that just removes something.

## Implementation Decisions

- **Name validation:** a subject or folder name is required and is trimmed before validation;
  empty or whitespace-only names (after trimming) are rejected, as are names over 200 characters.
  No other character restrictions apply. This is an application-level (Pydantic/form) rule only —
  the underlying database columns carry no length constraint.
- **Duplicate names:** allowed, deliberately. No application-level uniqueness check is added for
  subject or folder names, consistent with the already-locked schema decision that neither column
  carries a database uniqueness constraint.
- **Routes:** creation is nested under its parent (`POST /subjects`, `POST
  /subjects/{subject_id}/folders`); once a resource exists, its own id is enough to address it, so
  rename and delete are flat (`PATCH`/`DELETE` on `/subjects/{id}` or `/folders/{id}`). The main
  view is a single `GET /subjects` page.
- **Authorization:** every subject query is filtered by `subjects.user_id == current_user.id`
  directly; every folder query is filtered by joining `folders` to its owning `subjects` row and
  filtering on that same `user_id`, since folders carry no `user_id` column of their own. A subject
  or folder that doesn't exist, or that exists but belongs to a different user, returns **404** in
  both cases — the response never distinguishes "not yours" from "doesn't exist," so no id's
  ownership can be probed for.
- **Cascade deletes:** a subject or folder delete route issues nothing more than a `DELETE`
  statement against that row. Removal of everything beneath it (folders, sources, cards, and
  reviews) is handled entirely by the `ON DELETE CASCADE` foreign keys already established in
  ticket 02's schema — no cascade logic is duplicated in application code.
- **Page structure:** `GET /subjects` loads a user's subjects together with their folders in one
  query (no N+1, no lazy per-subject expansion round trip) and renders folders inline under each
  subject on first load.
- **Folder detail page:** explicitly out of scope for this ticket. Folders are only ever shown
  inline under their subject here; ticket 05 is the first ticket that needs a standalone
  per-folder view (to host its upload UI), and will add that page itself.
- **Rename UX:** inline edit-in-place — clicking "rename" swaps a name's display span for a small
  text-input form via an HTMX swap; submitting issues a `PATCH` and swaps back to a display span;
  a cancel control reverts to the display span without saving.
- **Delete UX:** the delete control carries an `hx-confirm` attribute, so the browser's native
  `confirm()` dialog gates the request client-side before it's ever sent; there is no server-side
  confirmation step or intermediate page. On success the response body is empty and the row is
  removed from the DOM via the control's own `hx-target`/`hx-swap="outerHTML"`.
- **Validation error rendering:** a validation failure on create or rename re-renders just the form
  fragment with an inline error message via the same HTMX request/response cycle — never a full
  page reload — matching the pattern already established for ticket 03's login/registration forms.
- **Empty states:** a user with zero subjects sees an empty-state message alongside the
  create-subject form (never a blank page); a subject with zero folders shows an empty-state
  message alongside its own create-folder form.
- **Ordering:** subjects and folders are both listed by creation order (`created_at` ascending); no
  alphabetical or custom sort is offered.
- **Verbs:** rename and delete use real `PATCH`/`DELETE` HTTP verbs issued directly by HTMX
  (`hx-patch`, `hx-delete`); no hidden-field method-override fallback is needed since the UI already
  depends on HTMX/JS being present.
- **Auth integration:** every route in this ticket depends on ticket 03's `current_user`
  dependency and inherits its unauthenticated handling unchanged — a 302 redirect to `/login` for a
  full-page `GET`, and a 401 with an `HX-Redirect: /login` header for an HTMX request.

## Testing Decisions

- **What makes a good test here:** it asserts externally observable HTTP behavior — status codes,
  response fragment content, and persisted database state (rows created/renamed/removed, cascades
  fired) — not ORM query internals or which SQL statements ran.
- **Seam:** the HTTP seam established by ticket 02's test harness (FastAPI `TestClient` + real test
  Postgres via testcontainers, each test wrapped in a transaction that's rolled back) and already
  exercised end-to-end by ticket 03. No new seam is introduced — subjects/folders are ordinary
  CRUD over HTTP with no volatile boundary (no LLM, no clock/timezone dependency) that would
  justify anything beyond the HTTP seam.
- **Modules tested:** the subject routes (create, rename, delete, list), the folder routes (create,
  rename, delete), the shared name-validation rule, the ownership/404 authorization check for both
  resource types, and the cascade-delete behavior verified at the database level after a delete
  request.
- **Prior art:** ticket 03 was the first ticket to actually exercise ticket 02's HTTP test harness
  with real request/response assertions (login/registration/logout, plus the `current_user`
  dependency). This ticket is the first to build **real, user-facing CRUD routes with persisted,
  mutable, user-owned data** on top of that same seam, and every later ticket's HTTP tests
  (upload, cards, review, settings) follow this ticket's pattern in turn.

## Out of Scope

- A dedicated per-folder detail/view page — folders render inline under their subject only; ticket
  05 introduces the first standalone folder page.
- Any uniqueness enforcement on subject or folder names, beyond what the schema already specifies
  (none).
- Bulk operations (bulk delete, bulk move, drag-and-drop reorganization).
- Nesting folders inside folders, or subjects inside subjects — the hierarchy is fixed at exactly
  two levels per the master PRD.
- Anything related to sources, cards, or reviews living inside a folder — those are delivered by
  tickets 05 onward; this ticket only builds the containers.
- Any server-side delete-confirmation step (a confirmation page, a "type the name to confirm"
  flow) beyond the client-side `hx-confirm` dialog.

## Further Notes

- This is the first ticket to build real, mutable, user-owned CRUD data on top of ticket 02's
  schema and ticket 03's auth contract — every later ticket's routes (uploads into a folder, cards
  scoped to a folder, review queries scoped to a subject) depend on the subjects/folders rows this
  ticket creates existing and being correctly user-scoped.
- The 200-character name cap and the "no uniqueness" rule are both revisitable without a migration
  — the cap is an app-level validation constant, and adding uniqueness later would require a new
  DB constraint plus a migration, not a change to this ticket's routes.
