# 04 — Hierarchy: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (all branches resolved by the agent's
recommendation, per user instruction). Source of truth for the hierarchy ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Name validation | Required, trimmed; rejected if empty/whitespace-only after trimming; max 200 characters; no character restrictions | Simple, user-hostile-complexity-free rule; 200 chars is generous for a subject/folder label while catching pasted-garbage input |
| 2 | Duplicate names | Allowed — no application-level uniqueness check added on top of the schema | Matches the already-locked schema decision (ticket 02 #16: no DB uniqueness constraint on `subjects.name`/`folders.name`); adding app-level uniqueness now would contradict that and isn't required by any user story |
| 3 | Route structure | Nested for creation, flat for item actions: `POST /subjects`, `GET /subjects` (main page), `PATCH /subjects/{id}`, `DELETE /subjects/{id}`; `POST /subjects/{subject_id}/folders`, `PATCH /folders/{id}`, `DELETE /folders/{id}` | Creation needs the parent in the URL; once a folder exists its id plus a DB join to `subjects` is enough to resolve ownership, so item routes don't need to stay nested |
| 4 | Authorization mechanics | Every query is scoped by `current_user.id` (subjects directly via `user_id`, folders via a join through their owning subject); a resource that doesn't exist *or* belongs to another user returns **404** | Matches REST convention of not distinguishing "not yours" from "doesn't exist" — avoids leaking which ids exist to other users |
| 5 | Delete confirmation UX | Client-side `hx-confirm` (browser `confirm()` dialog) before the DELETE request fires; no server-side confirmation step or page | Cheapest UX that still prevents accidental data loss; a full confirmation page/modal is unwarranted ceremony for a two-level hierarchy |
| 6 | HTMX response shape | Create/rename return the re-rendered HTML fragment for that single subject/folder (swapped via `hx-swap="outerHTML"`/`"beforeend"` into the list); delete returns an empty `200` body, with the triggering control's `hx-target` set to its own row and `hx-swap="outerHTML"` so the row is removed from the DOM | Keeps every mutating response minimal — the client only re-renders exactly what changed, consistent with the HTMX-partial-swap pattern already used for ticket 03's inline form errors |
| 7 | Page structure | A single `GET /subjects` page is the whole hierarchy view: subjects are loaded with their folders eagerly (one query, no N+1), and folders render inline under each subject on first load — no separate "expand" round-trip | Folder counts per subject are expected to be small (a handful), so lazy-loading folders per subject adds a network round-trip for no real benefit at this scale |
| 8 | Folder detail page | Out of scope for this ticket — folders are only ever shown inline under their subject here | Ticket 05 (upload) is the first ticket that needs a dedicated per-folder view (to host the upload UI and, later, its source/card list); building that page now would be speculative |
| 9 | Rename UX | Inline edit: clicking "rename" swaps the name's display span for an inline text-input form (HTMX swap); submitting `PATCH`es and swaps back to a display span; a cancel control reverts without saving | Avoids a modal/separate page for a one-field edit; consistent with the server-rendered-partial architecture |
| 10 | Empty states | A user with zero subjects sees an empty-state message plus the create-subject form (not a blank page); a subject with zero folders shows an empty-state message plus the create-folder form in place of a folder list | Prevents a confusing blank screen on first use; keeps the create affordance visible at every empty point |
| 11 | List ordering | Subjects and folders are ordered by `created_at` ascending (creation order) | No user story requires alphabetical or custom ordering; creation order is the simplest stable default and needs no extra sort UI |
| 12 | Validation error rendering | On a validation failure (blank/too-long name), the create/rename HTMX request re-renders just the form fragment with an inline error message — no full page reload | Matches ticket 03's established inline-HTMX-validation pattern |
| 13 | Cascade deletes | Routes simply `DELETE` the `subjects`/`folders` row; cascading removal of folders/sources/cards (and reviews) is handled entirely by the DB-level `ON DELETE CASCADE` already in the schema | Ticket 02 (decision #5) already put `ON DELETE CASCADE` on every FK in the chain — re-implementing cascade logic in the route would be redundant and a correctness risk if it drifted from the DB |
| 14 | Auth integration | Every hierarchy route depends on ticket 03's `current_user` FastAPI dependency; unauthenticated handling (302 redirect for full-page `GET`, 401 + `HX-Redirect` for HTMX requests) is inherited as-is, not reimplemented | `current_user` is documented as the reusable contract ticket 03 exists to provide; ticket 04 is its first real consumer |
| 15 | HTTP verbs via HTMX | Rename/delete use real `PATCH`/`DELETE` verbs, issued directly by HTMX (`hx-patch`, `hx-delete`) rather than a hidden method-override field | The UI already depends on HTMX/JS being present (per the locked master-PRD architecture), so there's no plain-HTML-forms-only fallback to preserve |
| 16 | Test seam | Reuses the existing HTTP seam (FastAPI `TestClient` + real test Postgres + per-test rollback) from ticket 02's harness; no new seam | Subjects/folders are ordinary CRUD over HTTP — the established seam already covers this fully |

## Notes
- Folder ownership checks always go through the owning subject's `user_id` — there is no
  `folders.user_id` column (per the locked schema), so every folder-scoped query joins `folders` to
  `subjects` and filters on `subjects.user_id == current_user.id`.
- The 200-character name cap is an application-level (Pydantic/form) validation rule only — the
  underlying `name` columns have no DB-level length constraint (ticket 02 decision #1 area), so
  raising the cap later is a code-only change.
- Ticket 05's "folder view" (mentioned in its own `plan.md`) will need a new `GET /folders/{id}`
  page; that page does not exist yet after this ticket and is explicitly deferred to ticket 05.
