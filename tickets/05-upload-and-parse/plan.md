# 05 — Upload & Parse

**Depends on:** 04. **Goal:** upload note files into a folder and extract their text into `sources`.

> Decisions locked via `/grill-me` on 2026-07-17 — see [decisions.md](decisions.md).

## Build
- Upload endpoint (multipart) into a folder owned by `current_user` (404 on cross-user access);
  accepts **PDF, Markdown, TXT** only, detected by case-insensitive filename extension (`.pdf`,
  `.md`, `.txt`) — no content-type sniffing.
- Parser (pure `(bytes, file_type) -> str` boundary, raising typed exceptions the route layer maps
  to HTTP responses):
  - **pypdf** (`PdfReader`, concatenate `extract_text()` across pages) for text PDFs; UTF-8 decode
    (`errors="replace"`) for MD/TXT.
  - No OCR / scanned PDFs / images (out of scope). After extraction, empty (post-strip) text is a
    distinct **no-extractable-text** failure from a **corrupt/unreadable PDF** failure (caught
    `pypdf` parse exceptions) — each gets its own clear message.
- Enforce a **10 MiB file-size cap**: fast-path reject on `Content-Length`, real enforcement via a
  streaming read guard (abort past `cap + 1` bytes); reject oversized uploads with a clear message.
- Enforce **per-folder filename uniqueness**, case-insensitive: a DB functional unique index on
  `(folder_id, lower(filename))`; the app attempts the insert and catches the resulting
  `IntegrityError` to surface "a file named '…' already exists in this folder" (same
  insert-then-catch pattern as ticket 03's duplicate-email handling), so notes are never silently
  overwritten or duplicated.
- All four rejection cases (unsupported type, oversized, no-extractable-text, duplicate filename)
  return **422** with a specific message, rendered as an HTMX-swappable inline error fragment (also
  used for non-HTMX full-page requests).
- Create a `sources` row storing filename, file_type, extracted `raw_text`, and `status` (initially
  `stored` — one of four values `stored | processing | done | failed`; no generation runs
  automatically, the user triggers it explicitly in ticket 06). Store extracted text only, not the
  binary.
- Chunking helper for text exceeding model context: pure `chunk_text(text, max_chars=100_000,
  overlap_chars=500) -> list[str]`, plain character-slicing with overlap, applied only when text
  exceeds `max_chars`. Chunks are **not persisted** — this ticket ships the function + unit tests;
  ticket 06 calls it directly against `raw_text` at generation time.
- Jinja + HTMX upload UI within a folder view: `hx-post` multipart form, success swaps in the
  updated sources list, failure swaps in an inline error above the form.

## Definition of done
- A supported file uploads, is parsed, and produces a `sources` row (`status=stored`) with correct
  extracted text.
- Unsupported type, oversized, no-extractable-text, corrupt-PDF, and duplicate-filename cases each
  return their own clear 422 error.

## Test seams
- **Parser unit seam:** small fixtures (text PDF, MD, TXT) + no-extractable-text and
  corrupt/unreadable-PDF failure cases; `chunk_text` unit tests (below/at/above threshold,
  overlap correctness).
- **HTTP seam:** upload happy path and each rejection case (unsupported type, oversized,
  no-extractable-text, duplicate filename), plus cross-user folder access denied.
