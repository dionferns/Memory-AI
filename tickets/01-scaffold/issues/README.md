# Ticket 01 — Scaffold: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label |
|-------|-------|-------|------|-----------|-------|
| 1 | [#2](https://github.com/dionferns/Memory-AI/issues/2) | package + uv + running /health app | AFK | — | ready-for-agent |
| 2 | [#3](https://github.com/dionferns/Memory-AI/issues/3) | quality gates (ruff + mypy strict + pytest/coverage + pre-commit) + /health test | AFK | #2 | ready-for-agent |
| 3 | [#4](https://github.com/dionferns/Memory-AI/issues/4) | config surface (pydantic-settings + .env.example) | AFK | #2 | ready-for-agent |
| 4 | [#5](https://github.com/dionferns/Memory-AI/issues/5) | docker compose dev stack (app + postgres:16) | AFK | #2 | ready-for-agent |
| 5 | [#6](https://github.com/dionferns/Memory-AI/issues/6) | GitHub Actions CI pipeline | AFK | #3, #4 | ready-for-agent |
| 6 | [#7](https://github.com/dionferns/Memory-AI/issues/7) | branch protection on main | **HITL** | #5 | — (HITL, no agent label) |

## Suggested implementation order
#2 → (#3, #4 in parallel) → #5 → #6

#2 is the tracer bullet everything hangs off. #3 and #4 can proceed in parallel once #2 lands.
#5 (CI) needs the gates (#3) and — to fully exercise Compose parity — #4. #6 (branch protection) is
a repo-admin policy action the user applies once CI (#5) exists.

## Notes
- The `ready-for-agent` label was created on the repo during this step (only default GitHub labels
  existed before). HITL issue #7 intentionally omits it.
