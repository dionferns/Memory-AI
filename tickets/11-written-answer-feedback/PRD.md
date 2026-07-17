# PRD: Ticket 11 — Written-Answer Feedback

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled
> 2026-07-17). GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Flip-and-self-grade review (ticket 09) asks the user to judge their own recall honestly, which is
easy to get wrong in either direction — over-crediting a vague memory as "Good," or
under-crediting an answer that was actually correct. For material where the user wants an external
check on their recall (not just their own flip-card judgment), there's no way to type an actual
answer and have it graded against the gold answer before a grade is applied. Ticket 11 adds that
path as an alternate input mode on top of the existing review flow, without touching the
scheduling core (ticket 08) or the grading endpoint (ticket 09) at all.

## Solution

A per-review-session toggle turns on "written-answer mode." With it on, each card shows a
free-text textarea instead of "Show answer." Submitting calls an LLM (via the same
injectable/mockable structured-JSON client boundary ticket 06 establishes) with
`{question, gold_answer, user_answer}` and gets back `{outcome: perfect|good|wrong, feedback}`.
The gold answer, the outcome, and the feedback are then shown alongside the same four grade
buttons ticket 09 already renders (Again/Hard/Good/Easy), with the mapped button
(`perfect→Easy`, `good→Good`, `wrong→Again`) pre-highlighted. The user confirms (or picks a
different button) and the grade is applied through ticket 08's existing
`apply_grade_to_card(session, card, grade, now_utc, tz)` persistence helper — the exact same call
ticket 09's flip-and-grade buttons make. A malformed LLM response (bad JSON, an `outcome` value
outside the three-way enum, a timeout, or any other call failure) degrades that single card to
plain flip-and-grade without losing the review session.

## User Stories

1. As a user reviewing a subject or the global queue, I want to toggle written-answer mode on for
   this review session, so that I can type my actual answer instead of just flipping the card.
2. As a user, I want written-answer mode to default to off at the start of each new review
   session, so that flip-and-grade stays the fast default and I opt into the slower, more rigorous
   mode deliberately.
3. As a user with written-answer mode on, I want a free-text box on the card front, so that I can
   type my answer before the back is revealed.
4. As a user, I want the box to lock and show a loading state after I submit, so that I know my
   answer is being graded and I don't double-submit.
5. As a user, I want to see the gold answer, a perfect/good/wrong outcome, and a short written
   explanation of the gap (or confirmation I was right) after I submit, so that I get real
   feedback, not just a pass/fail.
6. As a user, I want the grade button matching the LLM's outcome (perfect→Easy, good→Good,
   wrong→Again) pre-selected, so that in the common case I can just confirm without re-deciding.
7. As a user, I want all four grade buttons (including Hard) available and clickable even in
   written-answer mode, so that I can override the LLM's suggestion if I disagree with it.
8. As a user, I want the grade to only apply once I confirm (click a grade button), not the
   instant the LLM responds, so that I keep the final say over what gets recorded.
9. As a user, I want a slow LLM response to time out (30s) rather than hang the review session
   indefinitely, so that a flaky call doesn't block me from finishing my review.
10. As a user, I want a timed-out or malformed LLM response to fall back to a normal flip-and-grade
    view for that card (gold answer shown, no outcome/feedback, all four buttons available,
    none pre-selected) with a brief inline notice, so that one bad LLM call doesn't derail my
    whole session.
11. As a user, I want written-answer-mode grading to update `due_date`/`ease_factor` identically to
    grading the same card manually with the mapped button, so that my scheduling stays correct and
    predictable regardless of which input mode I used.
12. As the developer, I want the written-answer LLM call to reuse the exact client-boundary pattern
    from ticket 06 (injectable/mockable, structured/tool JSON, Pydantic-validated), so that there is
    one LLM-calling convention in the codebase, not two.
13. As the developer, I want the confirm action to call ticket 08's existing
    `apply_grade_to_card` helper (the same one ticket 09's grade buttons call), so that written-
    answer mode introduces no second grading/persistence path to keep in sync.
14. As the developer, I want the LLM's outcome/feedback to be ephemeral (rendered in-session, not
    persisted to the DB), so that this ticket introduces no new schema beyond what tickets 06/08/09
    already provide.

## Implementation Decisions

- **LLM call:** structured/tool JSON call using ticket 06's injectable/mockable client boundary.
  Input `{question, gold_answer, user_answer}`; output schema `{outcome: enum[perfect, good,
  wrong], feedback: str}`, `outcome` constrained by the tool's JSON schema to exactly those three
  string values.
- **Grading instructions:** grade `user_answer` against `gold_answer` for `question` using three
  bands only — `perfect` (fully correct, nothing material missing/wrong), `good` (substantially
  correct, minor omission/imprecision), `wrong` (materially incorrect, missing the key point, or
  off-topic/empty). `feedback` is 1-2 sentences addressed to the learner explaining the gap (or
  affirming correctness) — never a bare restatement of the gold answer.
- **Malformed-outcome handling:** any of — non-2xx/network/timeout error, unparseable JSON, or
  JSON that parses but has `outcome` outside `{perfect, good, wrong}` — is treated identically as a
  call failure. There is exactly one failure path: fall back to manual flip-and-grade for that
  card, with no outcome/feedback shown and no button pre-selected.
- **Timeout:** 30s client-side timeout on the LLM call. While in flight: submit button shows a
  "Grading..." state, textarea is locked, no other action available on that card. Timeout routes
  through the same malformed/failure fallback above, plus a brief inline notice ("Grading is
  taking too long — showing the answer instead").
- **Toggle scope:** per-review-session, not per-card, not a global/account setting (ticket 10 does
  not own this). Implemented as view-level session state (e.g. a query param or session-scoped
  flag on the review page), defaulting to off at the start of every new review session. No DB
  migration.
- **UI flow:** (1) written-answer-mode-on card front shows a textarea + "Submit Answer" button in
  place of "Show answer"; (2) on submit, textarea locks and a loading state shows; (3) on LLM
  response, reveal gold answer + outcome badge + feedback text + the same four grade buttons
  ticket 09 renders, with the mapped button pre-highlighted; (4) user clicks a grade button
  (confirming the pre-selection or overriding it) to apply the grade and advance — matching ticket
  09's existing "grade button click → HTMX swap to next card" interaction, so there is one grading
  interaction pattern across both modes.
- **Override interaction:** no separate "this seems wrong" control — all four grade buttons are
  always shown; clicking a non-pre-selected button simply changes the selection before confirm.
  Hard remains reachable only this way (written-answer mode's own mapping never auto-selects it),
  matching plan.md.
- **Grading integration:** no new grading endpoint, no new persistence path. The confirm action
  calls the exact same `apply_grade_to_card(session, card, grade, now_utc, tz)` helper (ticket 08
  decision #28) that ticket 09's `POST /review/{scope}/{card_id}/grade` route already calls — this
  ticket only changes what triggers that route/call and what grade value is pre-seeded into the
  UI before the user confirms it. The backend is unaware written-answer mode exists.
- **No new schema:** the LLM's `outcome`/`feedback` are never persisted — only the resulting grade
  and the `reviews` row ticket 08's helper already writes matter for scheduling.

## Testing Decisions

- **What makes a good test:** asserts externally observable behavior — the LLM boundary returns
  the right outcome/feedback shape (or the right failure classification) for canned inputs; the
  HTTP/UI seam asserts that submitting a written answer ultimately produces the same
  `due_date`/`ease_factor` change as grading manually with the mapped button, and that a
  malformed/timed-out LLM call falls back to flip-and-grade without losing the session — not
  prompt-string internals or the exact wording of `feedback`.
- **LLM boundary (mocked):** same mockable client pattern as ticket 06. Canned `{outcome,
  feedback}` responses for `perfect`/`good`/`wrong`, plus: unparseable JSON, valid JSON with an
  out-of-enum `outcome`, and a simulated timeout — all three asserted to hit the identical
  fallback path.
- **HTTP seam:** submit a written answer → outcome/feedback rendered → the pre-selected grade
  button matches the mapping → confirming applies the grade → `due_date`/`ease_factor` match what
  grading the same card manually with that mapped button would produce (equivalence test against
  ticket 08's persistence helper, reused directly rather than reimplemented for this ticket's
  tests). Override test: submit a written answer, click a different grade button than the
  pre-selected one, confirm, and assert the *overridden* grade (not the LLM's mapped grade) is what
  gets applied. Fallback test: simulate an LLM failure mid-session and assert the card renders
  plain flip-and-grade with all four buttons unselected and the session continues normally to the
  next card afterward.
- **Prior art:** ticket 06's mockable LLM client seam (reused directly, not reinvented); ticket 09's
  HTTP/HTMX review-flow test harness and grading route; ticket 08's DB-harness-backed persistence
  helper tests, reused as the equivalence oracle above.

## Out of Scope

- Persisting the LLM's `outcome`/`feedback` to the database (e.g. an answer-history table) — v1
  shows it in-session only.
- A global or per-card (as opposed to per-session) written-answer setting; that would live in
  ticket 10 if ever added, and isn't requested here.
- Any change to the SM-2 scheduling core (ticket 08) or the review-queue query/cap/ordering logic
  (ticket 09) — this ticket is additive UI + a new grade *source*, not a new grade *path*.
- Streaming/partial LLM responses, retry-with-backoff on failure (a single attempt within the 30s
  timeout, then fallback, is the whole retry policy for v1).
- Multi-language or non-English grading nuance beyond whatever the base LLM already handles.
- A "Hard" auto-mapping from any outcome — Hard stays manual-only in written-answer mode, per
  plan.md and decisions.md.

## Further Notes

- This ticket cannot land before both ticket 06 (LLM client boundary) and ticket 09 (review flows,
  including the `apply_grade_to_card` call site and the four-button grading UI it renders) are
  merged — it has no independent HTTP surface of its own to stand up first; it is purely additive
  to ticket 09's review page and reuses ticket 06's client seam verbatim.
- Ticket 08's `apply_grade_to_card(session, card, grade, now_utc, tz) -> Review` signature
  (recorded in `tickets/08-sr-algorithm/decisions.md` decision #28) is the exact call this ticket's
  confirm action makes — no wrapper or adapter layer is introduced around it.
- As of this PRD's writing, tickets 06 and 09 are themselves still mid-planning (parallel sibling
  work); this PRD and the issues that follow are written against their `plan.md`/`decisions.md`
  descriptions, not yet-merged issue numbers. Cross-ticket "Blocked by" references in this
  ticket's issues use prose until 06's and 09's issue numbers exist on `main`.
