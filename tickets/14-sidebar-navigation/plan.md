# 14 — Sidebar Navigation & Note Content Pane

Replace the current flat, all-expanded `/subjects` page (every subject's every folder's every
source listed inline, all at once) with a two-pane layout: a collapsible **left sidebar** tree
(Subjects → Folders → Notes) for navigation, and a **right content pane** that shows a single
note's content only once it's clicked in the sidebar. Where a note's stored format isn't already
Markdown, normalize it for display so the right pane always renders consistent, readable Markdown
output.

## Why

The current page (`subjects.html` + `_subject_row.html` + `_subject_folders_section.html` +
`_folder_row.html` + `_folder_sources_section.html`, all rendered inline and expanded) doesn't
scale — every folder's every source (with its quiz button, flashcard status, cards list) renders
on one page for every subject at once. A sidebar tree with progressive disclosure (expand a
subject to see its folders, expand a folder to see its notes, click a note to view it) is the
standard pattern for this shape of hierarchical data and keeps the page usable as a user
accumulates subjects/folders/notes.

## Scope

- Left sidebar: Subjects (level 1) → Folders (level 2, revealed on expanding a subject) → Notes
  (level 3, revealed on expanding a folder). Collapsed by default below the top level.
- Right pane: empty/placeholder state until a note is clicked; once clicked, shows that note's
  content, rendered as Markdown regardless of the source's original format (PDF/TXT/MD).
- Existing structural actions (create/rename/delete subject, create/rename/delete folder, upload a
  note) relocate into the sidebar tree at their respective levels.
- Existing per-note actions (Convert to Flashcards / status / retry, Quiz Me, view generated
  cards) relocate into the right pane, scoped to whichever note is currently selected.
- Out of scope: redesigning the flashcard review flow, the quiz-taking flow, or settings — this
  ticket is the navigation shell and note-content display only. Those existing pages/routes are
  linked to from the right pane, not rebuilt.
