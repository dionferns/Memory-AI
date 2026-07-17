# Ticket 09 — Review Flows: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#44](https://github.com/dionferns/Memory-AI/issues/44) | shared due-cards query + global capped review | AFK | tickets 07 (card model) and 08 (scheduler/tz boundary) | ready-for-agent | ⏳ Open |
| 2 | [#48](https://github.com/dionferns/Memory-AI/issues/48) | subject-level uncapped review (reuses shared query) | AFK | #44 | ready-for-agent | ⏳ Open |
| 3 | [#51](https://github.com/dionferns/Memory-AI/issues/51) | grading UI + grade-button wiring to ticket 08 scheduler | AFK | #44, #48, ticket 08 (grading/persistence helper) | ready-for-agent | ⏳ Open |
| 4 | [#53](https://github.com/dionferns/Memory-AI/issues/53) | sync-guarantee + cap/ordering/tz test suite | AFK | #44, #48, #51 | ready-for-agent | ⏳ Open |

## Suggested implementation order

#44 → #48 → #51 → #53.

Slice 1 (the shared `get_due_cards` query function plus the global daily review route) is the
tracer bullet — it establishes the single query function that slice 2 (subject review) reuses
directly, per decisions.md's core guarantee that the two views cannot drift because they share one
function. Slice 3 (grading + HTMX wiring) depends on both review routes existing so grading has
somewhere to redirect/advance to, and on ticket 08's persistence helper existing. Slice 4 (the
required sync test from plan.md, plus the cap/ordering/tz tests called out in the PRD's Testing
Decisions) is written last since it exercises all three prior slices end-to-end across both views.

All four slices are additionally blocked by ticket 07 (card model/CRUD, for card content to
render) and ticket 08 (SM-2 scheduler + tz-boundary helper, for grading and "due" computation),
which are being planned in parallel and had no numbered, mergeable issues at the time these were
written — see each issue's "Blocked by" section for the prose reference and decisions.md's TODO
for the exact call-signature confirmation.

## Notes

- No HITL issues this ticket — all four slices are AFK-executable once tickets 07 and 08 land,
  though slice 1 and slice 3 authors should re-check `tickets/08-sr-algorithm/decisions.md` (once
  it exists) against the assumed call shapes noted in `decisions.md`'s TODO section before wiring
  the actual function calls.
- Slices 1 and 2 are split from slice 3 (grading) rather than combined, because the read-only due
  list (slices 1-2) can be built and reviewed independently of the write path (grading, slice 3),
  and because slice 3 is the piece most exposed to ticket 08's still-unconfirmed signature — an
  isolated slice keeps that risk contained to one issue instead of spreading it across the whole
  ticket.
