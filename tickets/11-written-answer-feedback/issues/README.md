# Ticket 11 — Written-Answer Feedback: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-17, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#68](https://github.com/dionferns/Memory-AI/issues/68) | LLM outcome-grading call + mocked tests | AFK | ticket 06 (LLM client boundary) | ready-for-agent | ⏳ Open |
| 2 | [#69](https://github.com/dionferns/Memory-AI/issues/69) | written-answer UI, per-session toggle, outcome-to-grade mapping | AFK | #68, ticket-09 [#44](https://github.com/dionferns/Memory-AI/issues/44)/[#48](https://github.com/dionferns/Memory-AI/issues/48) (review page), [#51](https://github.com/dionferns/Memory-AI/issues/51) (grading UI) | ready-for-agent | ⏳ Open |
| 3 | [#71](https://github.com/dionferns/Memory-AI/issues/71) | end-to-end grading integration + equivalence and fallback tests | AFK | #68, #69, ticket 08 (`apply_grade_to_card`), ticket-09 [#51](https://github.com/dionferns/Memory-AI/issues/51) (grading route) | ready-for-agent | ⏳ Open |

## Suggested implementation order
#68 → #69 → #71

#68 (the LLM outcome-grading call) is the tracer bullet — it establishes the mockable
`{outcome, feedback}` grading function and the single failure classification (timeout /
unparseable JSON / out-of-enum outcome all treated identically) that #69 and #71 both build on.
#69 layers the written-answer UI (toggle, textarea, submit, loading state, outcome/feedback
display, pre-selected grade button, override) on top of ticket 09's existing review page and
grading control. #71 is the integration/verification slice: it doesn't add new product surface,
it proves #69's confirm action reuses ticket 09's existing grading route (and therefore ticket 08's
`apply_grade_to_card` helper) with no new grading path, via an equivalence test against manual
grading, an override test, and a fallback test.

## Cross-ticket dependencies

- **Ticket 06 (ai-flashcards)** — #68 reuses its injectable/mockable LLM client boundary pattern.
  As of this writing, ticket 06's `plan.md`/`decisions.md` are merged to `main` but its own
  GitHub issues are not yet published, so #68's "Blocked by" references ticket 06 in prose rather
  than by issue number.
- **Ticket 09 (review-flows)** — #69 and #71 need the review page, card front/back rendering, and
  the four-button grading route/persistence call it establishes. Ticket 09's issues are now
  published: [#44](https://github.com/dionferns/Memory-AI/issues/44)/[#48](https://github.com/dionferns/Memory-AI/issues/48)
  (the due-cards query + global/subject review routes) and
  [#51](https://github.com/dionferns/Memory-AI/issues/51) (grading UI + grade-button wiring to
  ticket 08's scheduler) are referenced directly above.
- **Ticket 08 (sr-algorithm)** — #71's equivalence test calls `apply_grade_to_card(session, card,
  grade, now_utc, tz)` (see `tickets/08-sr-algorithm/decisions.md` decision #28) directly as its
  oracle; ticket 08's issues are also not yet published as of this writing.
- These "Blocked by" prose references should be updated to real issue numbers once tickets
  06/08/09 publish their own `issues/README.md` files on `main`.

## Notes
- No HITL issues this ticket — all three slices are AFK-suitable (mocked LLM boundary, no
  external service credentials needed beyond what ticket 06 already wires up).
- No new database schema is introduced by any slice; the LLM's `outcome`/`feedback` are ephemeral
  (rendered in-session only), confirmed by #71's acceptance criteria.
