# Ticket 04 — Hierarchy: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#85](https://github.com/dionferns/Memory-AI/issues/85) | subject CRUD + hierarchy page | AFK | #29, #20 | ready-for-agent | ⏳ Open |
| 2 | [#86](https://github.com/dionferns/Memory-AI/issues/86) | folder CRUD nested under subjects | AFK | #85 | ready-for-agent | ⏳ Open |
| 3 | [#87](https://github.com/dionferns/Memory-AI/issues/87) | cross-user authorization + cascade-delete hardening | AFK | #85, #86 | ready-for-agent | ⏳ Open |
| 4 | [#88](https://github.com/dionferns/Memory-AI/issues/88) | unified hierarchy page (eager-loaded list/navigate view) | AFK | #85, #86 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#85 → #86 → (#87, #88 in parallel)

#85 (subject CRUD + hierarchy page) is the tracer bullet — it establishes the `GET /subjects`
page, the shared name-validation rule, the inline-rename/confirm-delete HTMX patterns, and the
`current_user`-scoped query shape that #86 (folder CRUD) directly reuses one level down. #86 in
turn is what #87 and #88 both build on: #87 hardens both resource types' authorization and
cascade-delete behavior, and #88 finalizes the combined page's query shape and rendering — neither
has any dependency on the other, so they can be built in parallel worktrees once #85 and #86 merge.
#85 also depends on ticket 03's `current_user` dependency (#29) and ticket 02's `subjects` table
(#20).

## Notes
- No HITL issues this ticket — every open branch from `/grill-me` (name validation, route shape,
  authorization/404 semantics, HTMX response shapes, delete confirmation, empty states, ordering)
  was a routine implementation call with an unambiguous best-practice default, not a
  policy/architectural decision requiring a human.
- #87 and #88 both intentionally test/verify behavior that #85 and #86 already build correctly
  (auth scoping is inherent to the CRUD queries; cascade deletes are inherited from ticket 02's DB
  constraints) rather than adding new production code — they exist as separate slices to give the
  cross-cutting concerns (authorization, cascade-delete correctness, N+1 avoidance) their own
  focused test coverage and review, since the same pattern applies identically across both subjects
  and folders.
- #29 (ticket 03's `current_user` dependency) is still open at the time these issues were filed;
  per this ticket's planning instructions, the routes here are designed against its documented
  contract regardless of implementation order.
