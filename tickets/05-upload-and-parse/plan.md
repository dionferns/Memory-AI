# 05 — Upload & Parse

**Depends on:** 04. **Goal:** upload note files into a folder and extract their text into `sources`.

## Build
- Upload endpoint (multipart) into a folder; accepts **PDF, Markdown, TXT** only.
- Parser (pure `(bytes, file_type) → text` boundary):
  - **pypdf** for text PDFs; direct read for MD/TXT.
  - No OCR / scanned PDFs / images (out of scope) — PDFs with no extractable text fail clearly.
- Enforce a **file-size cap**; reject oversized uploads with a clear message.
- Create a `sources` row storing filename, file_type, extracted `raw_text`, and `status` (initially
  `processing` — generation is wired in ticket 06). Store extracted text only, not the binary.
- Chunking helper for text exceeding model context (used by 06).
- Jinja + HTMX upload UI within a folder view.

## Definition of done
- A supported file uploads, is parsed, and produces a `sources` row with correct extracted text.
- Unsupported type, oversized, and no-extractable-text cases return clear errors.

## Test seams
- **Parser unit seam:** small fixtures (text PDF, MD, TXT) + no-text failure case.
- **HTTP seam:** upload happy path and each rejection case.
