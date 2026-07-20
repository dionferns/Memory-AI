# PRD: Ticket 14 — Sidebar Navigation & Note Content Pane

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (decisions
> resolved in-session 2026-07-20 by agent recommendation, no `/grill-me` interview — see
> decisions.md header). GitHub issues are created at the `/to-issues` step and recorded under
> `issues/`.

## Problem Statement

The current `/subjects` page renders every subject's every folder's every note inline, all
expanded, all at once (`_subject_row.html` → `_subject_folders_section.html` → `_folder_row.html`
→ `_folder_sources_section.html`). It doesn't scale as a user's library grows, and there's no way
to focus on a single note — everything (quiz button, flashcard status, cards list) for every note
in every folder renders simultaneously. There's also no page that shows a note's actual extracted
content at all; the current UI only ever shows a note's *filename* and its flashcard-generation
status, never the text itself.

## Solution

A two-pane layout: a collapsible left sidebar tree (Subjects → Folders → Notes, each level
expanding the next on click) for navigation, and a right content pane that renders a single
selected note's content — normalized to Markdown regardless of whether the original file was PDF,
TXT, or MD — plus that note's existing actions (Convert to Flashcards, Quiz Me, View Cards).
Structural actions (create/rename/delete subject or folder, upload a note) relocate into the
sidebar tree at their respective levels. No underlying route logic for those existing features
changes — only where they're invoked from and how the page is laid out.

## User Stories

1. As a user with many subjects/folders/notes, I want a collapsible sidebar tree instead of one long expanded page, so I can navigate my library without scrolling past everything at once.
2. As a user, I want to click a note in the sidebar and see its actual content on the right, so I can read what I uploaded without downloading the original file.
3. As a user, I want a PDF's extracted text and a Markdown file's content to both display cleanly formatted, so the viewing experience is consistent regardless of what format I uploaded.
4. As a user, I want to refresh the page or share a note's URL and land directly on that note, so the right pane isn't only reachable by re-clicking through the tree.
5. As a user, I want Convert to Flashcards, Quiz Me, and View Cards to still work exactly as before, just from the note I have open, so this navigation change doesn't take away anything I already rely on.
6. As a user, I want to still create/rename/delete subjects and folders and upload notes, now from the sidebar, so I don't lose any existing capability in the new layout.
7. As a user, I want an empty sidebar level (no subjects / no folders / no notes yet) to say so clearly, so I know creating something is the next step.

## Implementation Decisions

See [decisions.md](decisions.md) for the full table. Summary:
- Subjects+folders shell eager-loaded (reusing ticket 04's pattern); notes-per-folder lazy-loaded
  on expand via a new `GET /folders/{id}/notes` fragment route.
- Note selection via HTMX `hx-get` + `hx-push-url` to a new `GET /sources/{id}/content` fragment;
  a matching full-page `GET /sources/{id}` route handles direct/refresh/shared links.
- Markdown normalization happens at the rendering layer only (no schema/storage change): all three
  source formats' `raw_text` is rendered through one Markdown-to-HTML renderer (new `markdown`
  dependency), since plain text is valid Markdown source.
- Existing per-note actions (convert/quiz/view-cards) and structural CRUD (subject/folder
  create-rename-delete, upload) are relocated into the new layout, not rebuilt.
- Styling extends ticket 13's existing `styles.css` custom properties; no new CSS framework, no JS
  framework, no client-side router.
- Minimal responsive behavior: sidebar collapses behind a toggle below ~768px.

## Suggested Issue Breakdown (for `/to-issues`)

Rough dependency-ordered slices — the `/to-issues` step should verify/refine this against current
`main`, but as a starting point:
1. Sidebar tree shell: subjects+folders eager-loaded, notes lazy-loaded per folder on expand,
   empty states at every level, placeholder right pane.
2. Note content pane: `GET /sources/{id}/content` fragment + `GET /sources/{id}` full-page route,
   Markdown rendering for all three source formats, HTMX click-to-select with `hx-push-url`.
3. Relocate existing per-note actions (Convert to Flashcards status widget, Quiz Me, View Cards
   link) into the right pane, scoped to the selected note.
4. Relocate structural CRUD (subject/folder create/rename/delete, note upload) into the sidebar
   tree; retire the old `_folder_sources_section.html` inline list once superseded.
5. Responsive collapse behavior for small viewports (could fold into slice 1 if small enough).

## Acceptance Criteria (ticket-level)

- [ ] `/subjects` renders the new sidebar + right-pane shell instead of the old flat inline list.
- [ ] Expanding a subject reveals its folders; expanding a folder lazy-loads and reveals its notes.
- [ ] Clicking a note swaps the right pane to that note's rendered content without a full page
      reload, and updates the URL to `/sources/{id}`.
- [ ] Loading `/sources/{id}` directly (fresh navigation, refresh, or shared link) renders the full
      shell with that note pre-selected and its content shown.
- [ ] A `.md` source and a `.pdf`/`.txt` source both render through the same Markdown-to-HTML path
      with no per-format special-casing visible in the output structure.
- [ ] Convert to Flashcards (all four statuses: stored/processing/done/failed), Quiz Me, and a View
      Cards link all function from the right pane for the selected note, matching their existing
      behavior from before this ticket.
- [ ] Create/rename/delete subject, create/rename/delete folder, and upload-a-note all work from
      the sidebar tree, matching their existing behavior/validation from tickets 04/05.
- [ ] Every new route enforces ownership via 404-not-403, consistent with tickets 04/07.
- [ ] Empty states render correctly at every level (no subjects / a subject with no folders / a
      folder with no notes).
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` (strict), and
      `uv run pytest` all pass in CI.

## Out of Scope

- Redesigning the flashcard review flow, the quiz-taking flow, or the settings page.
- Editing a note's content in place (still read-only display).
- Persisting sidebar expand/collapse state across page loads.
- A full mobile redesign beyond the minimal collapse-behind-toggle behavior.
- Any database schema change.
