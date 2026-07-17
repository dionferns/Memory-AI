# 04 — Subjects & Folders

**Depends on:** 03. **Goal:** the two-level Subject → Folder hierarchy, user-scoped CRUD.

## Build
- Subjects: create, list, rename, delete — all scoped to `current_user`.
- Folders: create (within a subject), list, rename, delete — scoped via the owning subject.
- Cascade deletes: deleting a subject removes its folders (and their sources/cards); deleting a folder
  removes its sources/cards.
- Jinja + HTMX UI: a navigable list of subjects, each expandable to its folders; inline create/rename/delete.
- Authorization: a user can never see or mutate another user's subjects/folders (404/403 on cross-user access).

## Definition of done
- Full CRUD for subjects and folders through the UI, correctly scoped and cascading.

## Test seam (HTTP)
- CRUD happy paths; cross-user access denied; cascade-on-delete verified in the DB.
