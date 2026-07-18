# Bug Hunt Guide — Memory AI

Working notes for the full-codebase bug/test-gap review requested 2026-07-18. Kept as a live
reference for this session and any follow-up session that continues the work.

## Scope

Review **only code that is actually implemented and merged to `main`**, not features still
tracked by open "ready-for-agent" issues — those are incomplete-by-design, not buggy.

As of this review (main @ `6e54cb7`):

**In scope (implemented, merged):**
- `01-scaffold`, `02-db-foundation`, `03-auth`, `04-hierarchy`, `05-upload-and-parse`,
  `06-ai-flashcards`, `07-card-crud` (view/list only — see below), `08-sr-algorithm` (pure module
  + persistence only, NOT wired to any review UI), `10-settings`, `12-notes-quiz`.
- Files: `src/memory_ai/{auth,cards,config,database,flashcards,generation,hierarchy,main,models,
  parsing,quiz,scheduling}.py`, templates/static, alembic migrations.

**Out of scope (not implemented — open issues, do not report "missing feature" as a bug):**
- `07-card-crud`: inline edit (#75) and delete (#77) — cards can currently only be viewed, not
  edited/deleted from the UI.
- `09-review-flows`: **entirely unimplemented.** No due-cards query, no grading UI, no wiring
  from `scheduling.py`'s SM-2 module to any route. Issues #44, #48, #51, #53 open.
- `11-written-answer-feedback`: entirely unimplemented. Issues #68, #69, #71 open.
- `13-ui-color-palette`: only planning docs exist (`tickets/13-ui-color-palette/`); no stylesheet
  implementation. Issue #112 open.

If something looks broken in one of the out-of-scope areas, it's because the feature doesn't
exist yet — not a bug to file.

## Process

1. Understand implemented code + its tests per area (grouped to avoid re-deriving project context
   per file — see "Review groups" below).
2. For each candidate bug: verify it's real (read the actual code path, don't guess), confirm
   it's not explained by an out-of-scope gap above, and write a concrete failure scenario
   (input/state → wrong output).
3. For each candidate test gap: confirm the behavior is genuinely untested (grep test files, don't
   assume), not just "could have more tests."
4. File one GitHub issue per confirmed bug (`gh issue create`), labeled clearly, with the failure
   scenario and file:line pointer.
5. Fix bugs in this worktree, one commit per issue where practical, referencing `Closes #<n>`.
6. Push branch, open one draft PR (or per-issue PRs if the fixes are cleanly separable) — draft,
   not merged, since this is a self-directed review not a supervised ticket implementation.

## Review groups (for delegating to subagents without re-explaining the project each time)

- **Group A — Foundation/Auth/Hierarchy**: `auth.py`, `database.py`, `config.py`, `models.py`,
  `hierarchy.py` + `tests/test_auth.py`, `test_login.py`, `test_logout.py`, `test_register.py`,
  `test_current_user.py`, `test_database.py`, `test_models.py`, `test_config.py`,
  `test_hierarchy_authorization.py`, `test_hierarchy_page.py`, `test_folders.py`,
  `test_subjects.py`, `test_db_harness.py`.
- **Group B — Ingestion pipeline**: `parsing.py`, `flashcards.py`, `generation.py` +
  `test_parsing.py`, `test_upload.py`, `test_upload_rejection.py`, `test_upload_uniqueness.py`,
  `test_flashcards.py`, `test_convert.py`, `test_convert_status.py`, `test_convert_retry.py`.
- **Group C — Cards/Quiz/Scheduling/App wiring**: `cards.py`, `quiz.py`, `scheduling.py`,
  `main.py`, templates/static + `test_cards_view.py`, `test_quiz_generator.py`,
  `test_quiz_route.py`, `test_quiz_ui.py`, `test_quiz_nav_js.py`, `test_scheduling.py`,
  `test_scheduling_persistence.py`, `test_settings.py`, `test_health.py`.

## Findings log

Bugs and test gaps found this session are tracked as GitHub issues (label: `bug`) — see
`gh issue list --label bug` for the live list rather than duplicating it here.

## Notes / gotchas learned during this review

(fill in as discovered)
