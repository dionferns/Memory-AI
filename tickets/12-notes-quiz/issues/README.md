# Ticket 12 — Notes Quiz: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#64](https://github.com/dionferns/Memory-AI/issues/64) | batch LLM quiz-generation call | AFK | ticket 05 (upload-and-parse), ticket 06 (ai-flashcards) — prose reference, not yet published as issues | ready-for-agent | ⏳ Open |
| 2 | [#65](https://github.com/dionferns/Memory-AI/issues/65) | quiz UI with client-side Next/Previous/Show Answer navigation | AFK | #64 | ready-for-agent | ⏳ Open |

## Suggested implementation order
#64 → #65

#64 is the tracer bullet: it establishes the `QuizQuestion` Pydantic schema, the synchronous
generation route, and reuse of ticket 06's LLM client boundary. #65 depends on #64's response
shape (the full embedded question set) to build the "Quiz Me" button and the pure client-side
navigation logic on top of it. Two slices are sufficient here — per decisions.md #3, this ticket
introduces no server-side session/cache mechanism to slice out separately; state storage is simply
"embed the array in the initial response," which is part of #64's route contract and #65's
rendering, not a distinct piece of infrastructure.

## Notes
- No HITL issues this ticket — both slices are ordinary AFK implementation work.
- Neither ticket 05 nor ticket 06 had published GitHub issues at the time these were created (both
  were being planned in parallel by sibling agents), so "Blocked by" on #64 references them in
  prose. Update #64's blocked-by references to real issue numbers once those tickets' issues exist.
- Per decisions.md, this ticket deliberately has **no third slice** for "session/state storage
  mechanics" — the locked decision is client-side-only state with no new server concept, so that
  work is folded into #65 rather than split out.
