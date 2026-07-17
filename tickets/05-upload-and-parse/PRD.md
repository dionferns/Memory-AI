# PRD: Ticket 05 — Upload & Parse

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

A user's study notes exist as PDF, Markdown, or plain-text files sitting outside the app. Nothing
useful — flashcard generation (ticket 06), Quiz Me (ticket 12) — can happen until a note's text is
inside the system, associated with a folder, and stored in a form an LLM can consume. The app also
has no way yet to reject bad input (wrong type, too large, unreadable, an accidental re-upload of
the same file) with a message the user can act on.

## Solution

An authenticated, folder-scoped upload endpoint that accepts PDF/Markdown/TXT files, extracts their
text through a pure `(bytes, file_type) -> str` parser boundary, and persists a `sources` row
(filename, file_type, extracted `raw_text`, `status="stored"`) — no binary is retained and no
generation runs automatically. Uploads are rejected with a specific, clear 422 error for four
distinct cases: unsupported file type, oversized file, no extractable text (e.g. a scanned PDF),
and a filename that already exists (case-insensitively) in the target folder. A Jinja+HTMX form on
the folder view handles the multipart upload and swaps in either the updated file list or an inline
error, without a full page reload. A pure `chunk_text` helper is also shipped for ticket 06 to use
against oversized note text at generation time.

## User Stories

1. As a user, I want to upload a PDF, Markdown, or TXT file into a folder, so that I can turn my notes into cards.
2. As a user, I want a clear error if I upload an unsupported file type, so that I know what is accepted.
3. As a user, I want a clear message if a PDF has no extractable text (e.g. a scan), so that I understand why no cards can be made from it.
4. As a user, I want a distinct clear message if a PDF is corrupt/unreadable, so that I know the problem is the file itself, not that it has no text.
5. As a user, I want oversized files rejected with a clear limit message, so that I do not wait on a file that will not process.
6. As a user, I want an error if I upload a file with the same name as one already in that folder, so that I don't silently overwrite or duplicate a note.
7. As a user, I want that duplicate-filename check to catch names that only differ by case, so that `Notes.pdf` and `notes.pdf` can't both end up in the same folder by accident.
8. As a user, I want the raw extracted text of my upload stored, so that cards remain traceable to their source.
9. As a user, I want a freshly uploaded file to just sit there as a stored note (no processing state, no cards) until I explicitly ask for flashcards in a later step, so that upload stays fast and I control when generation happens.
10. As a user, I want the upload form to submit without a full page reload and show me the updated file list or a clear inline error, so that uploading feels immediate.
11. As a user, I want to only ever upload into folders I own, so that my notes stay private and I can't be tricked into writing into someone else's folder.
12. As the developer, I want a reusable text-chunking helper available, so that ticket 06's LLM call has a documented way to handle note text longer than the model can take in one call.

## Implementation Decisions

- **File-type detection:** case-insensitive filename-extension whitelist (`.pdf`, `.md`, `.txt`).
  No content-type/magic-byte sniffing in v1.
- **Size cap:** 10 MiB, enforced via a fast `Content-Length` check plus a real streaming read guard
  that aborts past `cap + 1` bytes (so a spoofed/missing header can't bypass the limit).
- **Parser boundary:** pure `(bytes, file_type) -> str`, raising typed exceptions
  (`UnsupportedFileType`, `FileTooLarge`, `NoExtractableText`, `UnreadableFile`) that the route layer
  translates to HTTP responses. PDFs use `pypdf.PdfReader` (`extract_text()` concatenated across
  pages); MD/TXT are UTF-8 decoded (`errors="replace"`).
- **PDF failure modes:** a caught `pypdf` parse exception yields "could not read this PDF"
  (`UnreadableFile`); a successfully parsed PDF whose extracted text is empty after stripping yields
  "no extractable text — likely a scanned/image PDF" (`NoExtractableText`) — two distinct messages
  for two distinct causes.
- **Filename uniqueness:** case-insensitive, scoped to `folder_id`, enforced with a DB functional
  unique index on `(folder_id, lower(filename))`. The app attempts the `sources` insert directly and
  catches the resulting `IntegrityError` to surface "a file named '…' already exists in this
  folder" — the same insert-then-catch pattern already locked for duplicate emails in ticket 03.
- **`sources.status`:** four string values — `stored` (written by this ticket), `processing`,
  `done`, `failed` (written later by ticket 06). Uploads only ever create rows at `stored`; a
  rejected upload creates no row at all.
- **Error response shape:** all four rejection cases return **422 Unprocessable Entity** with a
  case-specific message, rendered as an HTMX-swappable inline fragment (same fragment serves
  full-page and HTMX requests).
- **Upload UI:** Jinja form inside the folder view using `hx-post` + `hx-encoding="multipart/form-data"`;
  success swaps in the refreshed sources list, failure swaps in an inline error above the form. No
  page reload either way.
- **Authorization:** the target folder is resolved through `current_user`'s own subjects; a folder
  belonging to another user's subject 404s, matching ticket 04's authorization pattern.
- **Storage:** only extracted `raw_text` is persisted — the original binary is never stored.
- **Chunking helper:** pure `chunk_text(text, max_chars=100_000, overlap_chars=500) -> list[str]`,
  plain character-slicing with overlap, applied only when `len(text) > max_chars`. Chunks are never
  persisted — ticket 06 calls this function directly against `sources.raw_text` at generation time;
  multi-chunk LLM-call orchestration is out of scope here.

## Testing Decisions

- **What makes a good test here:** asserts externally observable behavior — the extracted text a
  given `(bytes, file_type)` pair produces, the HTTP status/message for each accept/reject case, and
  the persisted `sources` row — not `pypdf` internals or ORM query internals.
- **Seams (both apply, per the master PRD):**
  1. **File-parser pure seam:** `(bytes, file_type) -> str` unit tests with small fixtures (a text
     PDF, an MD file, a TXT file) plus the no-extractable-text and corrupt/unreadable-PDF failure
     cases, and `chunk_text` unit tests (below/at/above the threshold, overlap correctness).
  2. **HTTP seam:** ticket 02's test harness (FastAPI `TestClient` + real Postgres via
     testcontainers, transaction-rolled-back per test). Covers the upload happy path, each of the
     four rejection cases, and cross-user folder access denied.
- **Modules tested:** the parser module (pure), the chunking helper (pure), and the upload route
  (HTTP, including the DB-level uniqueness constraint firing under a concurrent-style duplicate
  insert).
- **Prior art:** ticket 02's test harness and fixtures (reused as-is); ticket 03's insert-then-catch
  `IntegrityError` pattern for the filename-uniqueness check; ticket 04's folder-ownership
  authorization pattern for the upload route.

## Out of Scope

- OCR / scanned PDFs / images embedded in PDFs; any file type other than PDF/MD/TXT.
- Persisting the original uploaded binary (only extracted text is stored).
- Automatic flashcard generation on upload — a source is only ever created at `status=stored`;
  triggering generation is ticket 06.
- Multi-chunk LLM-call orchestration (chaining/merging results across `chunk_text` chunks) — this
  ticket ships the pure helper only; consuming it is ticket 06's responsibility.
- Configurable size cap / chunk threshold via settings — both are fixed constants in v1.
- Re-uploading to replace an existing source's content (uniqueness rejects same-name uploads
  outright; there is no "overwrite" flow in v1).
- Virus/malware scanning of uploaded files.

## Further Notes

- **Blocked by ticket 04**: the upload route needs an existing, user-owned folder to upload into.
  Ticket 04 (`tickets/04-hierarchy/plan.md`) was still being planned in parallel when this PRD was
  written; see `tickets/04-hierarchy/issues/README.md` for its real issue numbers once published.
- This is the first ticket to touch file I/O and the first to add a DB constraint beyond ticket 02's
  initial schema (the functional unique index from decision above requires a new Alembic migration).
- The chunking helper is deliberately conservative (character-slicing, no NLP-aware splitting) since
  Claude's context window comfortably covers ordinary note lengths — chunking exists as a defensive
  measure for unusually long notes, not a routine path.
