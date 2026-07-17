# Ticket 01 — Scaffold: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#2](https://github.com/dionferns/Memory-AI/issues/2) | package + uv + running /health app | AFK | — | ready-for-agent | ✅ Done — [PR #8](https://github.com/dionferns/Memory-AI/pull/8) |
| 2 | [#3](https://github.com/dionferns/Memory-AI/issues/3) | quality gates (ruff + mypy strict + pytest/coverage + pre-commit) + /health test | AFK | #2 | ready-for-agent | ✅ Done — [PR #10](https://github.com/dionferns/Memory-AI/pull/10) |
| 3 | [#4](https://github.com/dionferns/Memory-AI/issues/4) | config surface (pydantic-settings + .env.example) | AFK | #2 | ready-for-agent | ✅ Done — [PR #11](https://github.com/dionferns/Memory-AI/pull/11) |
| 4 | [#5](https://github.com/dionferns/Memory-AI/issues/5) | docker compose dev stack (app + postgres:16) | AFK | #2 | ready-for-agent | ✅ Done — [PR #12](https://github.com/dionferns/Memory-AI/pull/12) |
| 5 | [#6](https://github.com/dionferns/Memory-AI/issues/6) | GitHub Actions CI pipeline | AFK | #3, #4 | ready-for-agent | ✅ Done — [PR #13](https://github.com/dionferns/Memory-AI/pull/13) |
| 6 | [#7](https://github.com/dionferns/Memory-AI/issues/7) | branch protection on main | **HITL** | #5 | — (HITL, no agent label) | ✅ Done — required `test` check + PR-required, admins may bypass |

## Suggested implementation order
#2 → (#3, #4 in parallel) → #5 → #6

#2 is the tracer bullet everything hangs off. #3 and #4 can proceed in parallel once #2 lands.
#5 (CI) needs the gates (#3) and — to fully exercise Compose parity — #4. #6 (branch protection) is
a repo-admin policy action the user applies once CI (#5) exists.

## Notes
- The `ready-for-agent` label was created on the repo during this step (only default GitHub labels
  existed before). HITL issue #7 intentionally omits it.
- #2–#6 are merged into `main`. #3's original PR (#9) was closed unmerged after its base branch
  (`feat/02-scaffold-health-app`) was merged and went stale; the work was rebased onto `main` and
  landed via PR #10 instead.
- #7: branch protection applied to `main` — required status check `test`, PR required to merge
  (`required_approving_review_count: 0`), `enforce_admins: false` so the repo admin can bypass in
  an emergency, force-push/branch-deletion disallowed. All ticket-01 issues are now closed.
