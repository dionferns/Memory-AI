# 05 — Upload & Parse: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (no open questions for the user — every
branch resolved by the agent's own best-practice recommendation, staying consistent with the
locked master PRD and prior tickets' decisions). Source of truth for the upload-and-parse ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Accepted file types — detection | Filename-extension whitelist (`.pdf`, `.md`, `.txt`), case-insensitive; no magic-byte/content-type sniffing | Multipart `Content-Type` headers from browsers are unreliable; extension check is simple and matches the v1 scope (three known formats) |
| 2 | File-size cap | **10 MiB** (10 × 1024 × 1024 bytes) | Generous for a single text/PDF note while bounding memory use and pypdf parse time; easy to raise later via config if needed |
| 3 | Size-cap enforcement | Check `Content-Length` first for a fast reject, then guard the actual read by streaming up to `cap + 1` bytes and rejecting if exceeded | `Content-Length` alone can be spoofed/absent; the streaming guard is the real enforcement, the header check is just a fast path |
| 4 | PDF text extraction | `pypdf.PdfReader`, concatenate `page.extract_text()` across all pages | Locked in master PRD; simplest correct approach for text-based PDFs |
| 5 | "No extractable text" detection | After extraction, strip whitespace from the concatenated text; if empty, treat as a distinct failure (`no extractable text — likely a scanned/image PDF`) from a corrupt/unreadable PDF | User story 15 requires a specific message distinguishing "scanned PDF" from generic failure |
| 6 | Corrupt/unparseable PDF handling | Catch `pypdf` exceptions (e.g. `PdfReadError`) during parsing and surface a generic "could not read this PDF" error, separate from the no-extractable-text message | Keeps the two failure messages honest — one is "we read it but there's nothing there", the other is "we couldn't read it at all" |
| 7 | MD/TXT extraction | Decode bytes as UTF-8 (`errors="replace"`); no separate empty-content check beyond the same post-strip empty check as PDFs, using the same message | Consistent single failure path for "nothing usable was extracted", regardless of file type |
| 8 | Parser boundary shape | Pure `(bytes, file_type) -> str` function, raising a small set of typed exceptions (`UnsupportedFileType`, `FileTooLarge`, `NoExtractableText`, `UnreadableFile`) that the route layer maps to HTTP responses | Matches the master PRD's file-parser pure unit seam; keeps parsing testable without any HTTP/DB machinery |
| 9 | Per-folder filename uniqueness — comparison | Case-insensitive (`lower(filename)`), scoped to `folder_id` | Prevents `Notes.pdf` and `notes.pdf` coexisting as accidental near-duplicates in the same folder |
| 10 | Per-folder filename uniqueness — enforcement | DB-level functional unique index on `(folder_id, lower(filename))`, with the app attempting the insert and catching the resulting `IntegrityError` to surface a friendly "a file named '…' already exists in this folder" error | Same check-then-insert-race-avoidance pattern already locked for duplicate emails in ticket 03 decision #9; DB constraint is the source of truth, app catch gives a clean message |
| 11 | `sources.status` values | Four string values: `stored` (initial, set by this ticket) / `processing` / `done` / `failed` (set later by ticket 06) | Ticket 06's plan already documents sources starting at `status=stored` with no auto-generation; this ticket only ever writes `stored` (or nothing, on a rejected upload — no row is created) |
| 12 | Upload response shape (HTTP/error contract) | All four rejection cases (unsupported type, oversized, no-extractable-text, duplicate filename) return **422 Unprocessable Entity** with an HTMX-swappable error fragment containing a specific, case-appropriate message; a full-page (non-HTMX) request gets the same fragment rendered inline on the upload form | Consistent status code simplifies client handling; distinct messages satisfy user stories 14–16; mirrors ticket 03's inline-partial-swap pattern for form errors rather than inventing a new error convention |
| 13 | Upload UI mechanics | Jinja form inside the folder view with `hx-post`, `hx-encoding="multipart/form-data"`, `hx-target` set to a sources-list partial; success swaps in the updated file list, failure swaps in an inline error message above the form | Standard HTMX multipart pattern; no page reload on either success or failure |
| 14 | Chunking helper — shape | Pure `chunk_text(text: str, max_chars: int = 100_000, overlap_chars: int = 500) -> list[str]`, plain character-slicing with overlap (no sentence/paragraph-aware splitting) | Simplest correct implementation; Claude's context window is large enough that chunking is a defensive measure for unusually long notes, not a routine path — no need for smarter splitting in v1 |
| 15 | Chunking — when applied / where stored | Applied only when `len(text) > max_chars`; chunks are **never persisted** — `chunk_text` is a stateless helper ticket 06 calls at generation time directly against `sources.raw_text`. This ticket ships the function + unit tests only; multi-chunk LLM-call orchestration is ticket 06's responsibility | Keeps 05's scope to "produce text + a reusable chunking helper"; avoids a schema change (no `chunks` table) for a case the schema doesn't need to represent since nothing chunk-shaped is ever queried on its own |
| 16 | Original binary retention | Never persisted — only `raw_text` is stored, per the master PRD's explicit out-of-scope note | Already locked at the master level; restated here since this is the ticket that implements it |
| 17 | Upload authorization | Upload route resolves the target folder through `current_user`'s own subjects (folder must belong to a subject owned by the caller), 404 on cross-user access | Consistent with ticket 04's authorization pattern for subjects/folders — never leak folder existence across users |

## Notes

- **Blocked by ticket 04**: the upload route needs an existing, user-owned folder to upload into.
  Ticket 04 (`tickets/04-hierarchy/plan.md`) was still being planned in parallel at the time this
  ticket was grilled; its issues had not yet been published to `tickets/04-hierarchy/issues/README.md`
  on `main`. Ticket 05's own issues (see `issues/README.md`) reference ticket 04's folder CRUD in
  prose rather than a fixed issue number for this reason.
- The functional unique index from decision #10 (`(folder_id, lower(filename))`) and the four-value
  `status` column from decision #11 both require changes to `src/memory_ai/models.py` plus a new
  Alembic migration; that is implementation work for the issues in `issues/README.md`, not this
  planning ticket.
- Decision #2's 10 MiB cap and decision #14's 100,000-character chunk threshold are both plain
  Python constants (not new `Settings` config fields) — no stated requirement to make either
  operator-configurable in v1; can be promoted to config later if that changes.
