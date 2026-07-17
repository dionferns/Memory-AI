# Ticket 05 — Upload & Parse: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#50](https://github.com/dionferns/Memory-AI/issues/50) | file parser + chunking pure module | AFK | — | ready-for-agent | ⏳ Open |
| 2 | [#52](https://github.com/dionferns/Memory-AI/issues/52) | upload happy path + sources row + HTMX UI | AFK | #50, ticket 04 folder CRUD | ready-for-agent | ⏳ Open |
| 3 | [#55](https://github.com/dionferns/Memory-AI/issues/55) | upload rejection paths (type, size, no-text, corrupt) | AFK | #52 | ready-for-agent | ⏳ Open |
| 4 | [#60](https://github.com/dionferns/Memory-AI/issues/60) | per-folder filename-uniqueness enforcement | AFK | #52 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#50 → #52 → (#55, #60 in parallel)

#50 (the pure parser + chunking module) is the tracer bullet — it has no dependency on ticket 04 and
can be built and merged immediately. #52 (the upload happy path) needs both #50's parser and ticket
04's folder model/routes/ownership pattern (folder CRUD was still being planned in a parallel
worktree at the time these issues were published; see `tickets/04-hierarchy/issues/README.md` once
it exists on `main` for its real issue numbers). #55 (rejection paths) and #60 (filename uniqueness)
both extend the same upload route from #52 but touch disjoint concerns — HTTP error-path wiring vs.
a DB constraint + migration — so they have no dependency on each other and can be built in parallel
worktrees once #52 merges.

## Notes
- No HITL issues this ticket — every branch left open by `plan.md` was resolved by `/grill-me`
  (see [../decisions.md](../decisions.md)); nothing here is a genuine human policy call.
- #52 and, transitively, #55/#60 are blocked on ticket 04's folder CRUD landing in code (not just
  planned) — an upload route has nothing to upload into until a real, user-owned folder exists.
  These issues are written to be gradable as ready-for-agent once ticket 04's implementation is
  in `main`, without needing to be re-filed.
