# Ticket 03 — Auth: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#27](https://github.com/dionferns/Memory-AI/issues/27) | login + JWT issuance | AFK | #20 | ready-for-agent | ⏳ Open |
| 2 | [#28](https://github.com/dionferns/Memory-AI/issues/28) | registration (auto-login) | AFK | #27 | ready-for-agent | ⏳ Open |
| 3 | [#29](https://github.com/dionferns/Memory-AI/issues/29) | current_user dependency + protected-route enforcement | AFK | #27 | ready-for-agent | ⏳ Open |
| 4 | [#30](https://github.com/dionferns/Memory-AI/issues/30) | logout | AFK | #27 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#27 → (#28, #29, #30 in parallel)

#27 (login + JWT issuance) is the tracer bullet — it establishes the JWT-issuing helper and the
`ACCESS_TOKEN_EXPIRE_MINUTES`/PyJWT plumbing that #28 (registration's auto-login), #29 (the
`current_user` dependency), and #30 (logout, clears the same cookie) all reuse. #28/#29/#30 have no
dependency on each other and can be built in parallel worktrees once #27 merges. All four also
depend on ticket 02's `users` table (#20).

## Notes
- No HITL issues this ticket.
- Registration auto-logs the user in (issues the same session cookie as login) rather than
  requiring a separate login step after signup — decided during PRD drafting as the better default
  UX; not a branch that was asked about during `/grill-me`.
