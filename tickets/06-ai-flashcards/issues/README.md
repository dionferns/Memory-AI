# Ticket 06 — AI Flashcards: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#73](https://github.com/dionferns/Memory-AI/issues/73) | LLM client boundary + structured output validation | AFK | ticket 05 (prose — not yet published) | ready-for-agent | ⏳ Open |
| 2 | [#76](https://github.com/dionferns/Memory-AI/issues/76) | convert-to-flashcards trigger + BackgroundTasks job + status transitions | AFK | #73, ticket 05 (prose — not yet published) | ready-for-agent | ⏳ Open |
| 3 | [#78](https://github.com/dionferns/Memory-AI/issues/78) | processing-popup polling UI + Convert to Flashcards button | AFK | #76 | ready-for-agent | ⏳ Open |
| 4 | [#81](https://github.com/dionferns/Memory-AI/issues/81) | malformed-output/API-failure handling + replace-on-retrigger | AFK | #76, #78 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#73 → #76 → #78 → #81

#73 is the tracer bullet — it establishes the `FlashcardGenerator` boundary (real Anthropic
implementation + validation) that #76's background job calls. #76 wires that boundary into the
actual trigger endpoint, `BackgroundTasks` job, and card persistence/status transitions on the
happy path. #78 builds the user-facing polling popup and button against #76's endpoints. #81 closes
the loop by hardening #76's job against malformed output/API errors and extending the trigger to
support replace-on-retrigger, reusing #78's Retry button.

Both #73 and #76 are also blocked, at the ticket level, on ticket 05 (upload-and-parse) — this
ticket's dependency per `tickets/README.md`. Ticket 05 was still being planned in parallel as of
this writing and had not yet published GitHub issues, so no ticket-06 issue references a specific
ticket-05 issue number; this README should be updated with real numbers once ticket 05's
`issues/README.md` exists on `main`.

## Notes
- No HITL issues this ticket — all four slices are AFK-suitable (implementation follows directly
  from decisions.md; no open judgment calls requiring a human in the loop).
- 3–5 slices were targeted per the `/to-issues` convention; 4 was chosen to keep the LLM boundary
  (#73), the core generation pipeline (#76), the UI (#78), and the failure/retry hardening (#81)
  each independently reviewable and testable, rather than folding failure-handling into #76 as one
  large PR.
