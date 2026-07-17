# Ticket 02 — DB Foundation: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#20](https://github.com/dionferns/Memory-AI/issues/20) | models + Alembic + initial migration | AFK | — | ready-for-agent | ⏳ Open |
| 2 | [#21](https://github.com/dionferns/Memory-AI/issues/21) | test harness (testcontainers + rollback) + round-trip test | AFK | #20 | ready-for-agent | ⏳ Open |
| 3 | [#22](https://github.com/dionferns/Memory-AI/issues/22) | CI runs alembic upgrade head before pytest | AFK | #20 | ready-for-agent | ⏳ Open |
| 4 | [#23](https://github.com/dionferns/Memory-AI/issues/23) | Docker Compose app runs migrations before uvicorn | AFK | #20 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#20 → (#21, #22, #23 in parallel)

#20 is the tracer bullet everything hangs off — the models and initial migration must exist before
the test harness can migrate a testcontainer, CI can run `alembic upgrade head`, or Compose can run
it on startup. #21, #22, and #23 have no dependency on each other and can be built in parallel
worktrees once #20 merges.

## Notes
- No HITL issues this ticket — it's pure infrastructure, no policy/architectural decisions left
  unresolved after `/grill-me`.
