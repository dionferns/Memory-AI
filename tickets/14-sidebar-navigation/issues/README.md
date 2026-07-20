# Ticket 14 — Sidebar Navigation & Note Content Pane: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-20, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#141](https://github.com/dionferns/Memory-AI/issues/141) | sidebar tree shell (subjects/folders/notes navigation) | AFK | None | ready-for-agent | ⏳ Open |
| 2 | [#142](https://github.com/dionferns/Memory-AI/issues/142) | note content pane (Markdown rendering + direct/deep link) | AFK | #141 | ready-for-agent | ⏳ Open |
| 3 | [#143](https://github.com/dionferns/Memory-AI/issues/143) | relocate per-note actions into the right pane | AFK | #142 | ready-for-agent | ⏳ Open |
| 4 | [#144](https://github.com/dionferns/Memory-AI/issues/144) | relocate structural CRUD into the sidebar tree; retire old inline partial | AFK | #141, #143 | ready-for-agent | ⏳ Open |

## Suggested implementation order

#141 → #142 → #143 → #144.

#141 (sidebar tree shell) is the tracer bullet — it swaps `/subjects`'s template output to the new
two-pane layout, adds the new lazy `GET /folders/{id}/notes` fragment route (notes no longer
eager-loaded inline with subjects+folders, per decisions.md #1), and establishes empty
states/responsive collapse. Its right pane is a placeholder only. #142 builds the note content pane
(new `GET /sources/{id}/content` fragment + `GET /sources/{id}` full page + Markdown rendering) and
wires the sidebar's note rows from #141 to click-select into it. #143 relocates the existing
per-note actions (Convert to Flashcards, Quiz Me, View Cards) into the right pane #142 built. #144
relocates the remaining structural CRUD (subject/folder create-rename-delete, note upload) into the
tree #141 built, and is ordered last because deleting the superseded
`_folder_sources_section.html` cleanly requires both the notes-list (#141) and per-note-actions
(#143) migrations to have already landed — #144's CRUD-relocation work itself only depends on #141,
but it does the final file deletion so it's sequenced after #143.

## Notes

- No HITL issues this ticket — every open branch was already resolved directly by the agent's own
  reasoned recommendation and recorded in `decisions.md` (per the user's explicit "don't ask me any
  questions" instruction, no interactive `/grill-me` interview was run for this ticket either). The
  `/to-issues` breakdown itself was likewise done by direct judgment call rather than an interactive
  quiz, consistent with that same instruction.
- The PRD's own "Suggested Issue Breakdown" proposed five rough slices (tree shell, note pane,
  relocate per-note actions, relocate structural CRUD, responsive collapse) in that order. This
  breakdown folds the responsive-collapse slice into #141 (it's a CSS-only addition to the shell
  being built there anyway — the PRD itself flagged this as foldable "if small enough"), and
  reorders the last two: the PRD listed "relocate per-note actions" before "relocate structural
  CRUD," but structural CRUD relocation (#144) is sequenced *after* per-note-action relocation
  (#143) here specifically so that the final deletion of `_folder_sources_section.html` — which
  PRD/decisions.md both call out as retired once superseded — has all of its responsibilities
  (notes list, content, per-note actions, upload form) already migrated elsewhere before the file
  is removed. The CRUD-relocation code itself doesn't require #143 to exist; only the cleanup step
  does.
- Verified against current `main` (not just the PRD's description, since `main` has moved since it
  was written): `GET /subjects` (`src/memory_ai/hierarchy.py`) currently eager-loads subjects,
  folders, *and* sources in one `selectinload` chain — #141 changes this to stop eager-loading
  sources and add the new lazy per-folder notes route, matching decisions.md #1. The upload-a-note
  form and the Quiz Me button both currently live inside `_folder_sources_section.html` alongside
  `_source_status.html`'s conversion-status widget — confirming that file's responsibilities split
  across #141 (notes list), #143 (quiz/convert/view-cards), and #144 (upload form), which is why
  #144 performs its final deletion.
- All four routes touched by this ticket (`GET /folders/{id}/notes`, `GET /sources/{id}`,
  `GET /sources/{id}/content`, and the relocated CRUD routes) reuse the existing 404-not-403
  ownership pattern already established and tested in tickets 04/07 — no new authorization logic,
  per decisions.md #15.
