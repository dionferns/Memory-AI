# 11 — Written-Answer Feedback

**Depends on:** 09. **Reuses:** the LLM client boundary from 06. **Goal:** free-text answer input
during review, LLM-graded against the gold answer, with the self-graded outcome driving SM-2.

## Build
- Review UI gains a free-text input as an alternate to flip-and-self-grade: user types an answer
  before the card back is revealed.
- On submit, a **structured/tool JSON** LLM call (same injectable/mockable client pattern as 06)
  receives `{question, gold_answer, user_answer}` and returns `{outcome: perfect|good|wrong,
  feedback: str}`. Malformed output → treat as a call failure, fall back to manual flip-and-grade
  for that card.
- **Outcome → SM-2 grade mapping:** `perfect → Easy`, `good → Good`, `wrong → Again`. `Hard` stays
  reachable only via manual grading; written-answer mode never emits it.
- The LLM's `feedback` text and computed outcome are shown alongside the revealed gold answer
  before the grade is (auto-)applied — user can still override the grade manually if they
  disagree.
- Applies the resulting grade through the existing ticket-08 scheduler/persistence helper — no new
  grading path, just a new input source for the grade.
- Written-answer mode vs. flip-only stays a per-review choice (toggle in the review UI), not a
  global setting.

## Definition of done
- Submitting a free-text answer in review yields an LLM outcome + feedback, and the card's
  `due_date`/`ease_factor` update per the mapped SM-2 grade — verified equivalent to grading
  manually with that mapped button.
- A malformed/failed LLM call degrades to manual flip-and-grade without losing the review session.

## Test seams
- **LLM boundary (mocked):** canned `{outcome, feedback}` responses for perfect/good/wrong, plus a
  malformed-output failure case.
- **HTTP seam:** submit written answer → outcome shown → grade applied → `due_date` matches the
  mapped manual grade; override path changes the applied grade.
