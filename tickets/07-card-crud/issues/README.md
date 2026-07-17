# Ticket 07 — Card CRUD: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#72](https://github.com/dionferns/Memory-AI/issues/72) | view cards (per-source and per-folder listing) | AFK | ticket 06 (ai-flashcards, in prose — no issue numbers published yet), ticket 03 (auth), ticket 04 (hierarchy) | ready-for-agent | ⏳ Open |
| 2 | [#75](https://github.com/dionferns/Memory-AI/issues/75) | inline edit card (front/back only) | AFK | #72 | ready-for-agent | ⏳ Open |
| 3 | [#77](https://github.com/dionferns/Memory-AI/issues/77) | inline delete card (two-step confirm, cascades reviews) | AFK | #72 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#72 → (#75, #77 in parallel)

#72 (view cards) is the tracer bullet — it establishes both list routes (per-source, per-folder)
and the shared card-row partial template that #75 (edit) and #77 (delete) both swap into. #75 and
#77 have no dependency on each other and can be built in parallel worktrees once #72 merges.

## Notes
- No HITL issues this ticket — it's a small, well-scoped CRUD surface with no external service
  integration or ambiguous UX decisions left open (all resolved in `decisions.md`).
- This ticket is blocked on ticket 06 (ai-flashcards) actually existing on `main` — as of this
  writing, ticket 06's PRD/decisions have merged but its own implementation issues had not yet
  been published, and none of tickets 03/04/05/06 have landed application code on `main` yet
  either (only planning docs). None of #72/#75/#77 should be picked up for implementation until
  those dependencies are actually merged and working — assigning them now only grabs the numbers
  and records the plan.
- Edit (#75) and delete (#77) both intentionally reuse the exact same card-row partial from #72 so
  their HTMX swap targets stay consistent regardless of which list view (source or folder) the
  card was reached from.
