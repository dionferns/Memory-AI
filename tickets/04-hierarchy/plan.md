# 04 — Subjects & Folders

**Depends on:** 03. **Goal:** the two-level Subject → Folder hierarchy, user-scoped CRUD.

> Decisions locked via `/grill-me` on 2026-07-17 — see [decisions.md](decisions.md).

## Build
- Subjects: `POST /subjects` (create), `GET /subjects` (main hierarchy page, subjects + their
  folders eagerly loaded), `PATCH /subjects/{id}` (rename), `DELETE /subjects/{id}` — all scoped
  to `current_user.id` directly via `subjects.user_id`.
- Folders: `POST /subjects/{subject_id}/folders` (create, nested under its subject),
  `PATCH /folders/{id}` (rename), `DELETE /folders/{id}` — scoped via a join from `folders` to the
  owning `subjects` row and filtered on `subjects.user_id == current_user.id` (there is no
  `folders.user_id` column).
- Name validation: required, trimmed, rejected if empty/whitespace-only after trimming, max 200
  characters, no other character restrictions. No app-level uniqueness check — duplicate
  subject/folder names are allowed, matching the schema's lack of a uniqueness constraint.
- Authorization: a subject/folder that doesn't exist *or* belongs to another user returns **404**
  (never a 403 that would leak existence).
- Cascade deletes: deleting a subject or folder issues a plain `DELETE` against that row; removal
  of folders/sources/cards/reviews underneath is handled entirely by the DB's `ON DELETE CASCADE`
  (already in place from ticket 02) — no cascade logic in the route itself.
- Jinja + HTMX UI on a single `GET /subjects` page: subjects list with folders rendered inline
  underneath each (no lazy-load round trip). Inline create forms, inline rename-in-place editing
  (swap name → input → name), and `hx-delete` + `hx-confirm` (browser confirm dialog) for deletes.
  Create/rename responses swap in just the affected HTML fragment; delete responses are empty and
  remove the row via `hx-swap="outerHTML"` on the row's own target. Validation failures re-render
  the form fragment with an inline error, no full page reload.
- Empty states: zero subjects shows an empty-state message plus the create-subject form; a subject
  with zero folders shows an empty-state message plus its create-folder form.
- Ordering: subjects and folders listed by `created_at` ascending.
- Every route depends on ticket 03's `current_user` dependency, inheriting its unauthenticated
  handling (302 redirect for full-page `GET`, 401 + `HX-Redirect` for HTMX requests) unchanged.
- Out of scope here: a dedicated per-folder detail page — folders only render inline under their
  subject on this page; ticket 05 adds the first standalone folder view (for upload UI).

## Definition of done
- Full CRUD for subjects and folders through the UI, correctly scoped and cascading.

## Test seam (HTTP)
- CRUD happy paths (create/rename/delete for both subjects and folders); validation failures
  (blank name, too-long name); cross-user access denied (404, not 403) for both subjects and
  folders; cascade-on-delete verified in the DB (deleting a subject removes its folders, and
  transitively their sources/cards; deleting a folder removes its sources/cards).
- Reuses ticket 02's HTTP test harness (`TestClient` + real Postgres + per-test rollback) — no new
  seam.
