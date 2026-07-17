# 12 — Notes Quiz Mode

**Depends on:** 05. **Reuses:** the LLM client boundary from 06. **Goal:** a read-through Q&A quiz
generated in one shot from a note's full text, browsed one question at a time.

## Build
- The note view (same main-editor surface as the "Convert to Flashcards" button from 06) gets a
  **"Quiz Me"** button per source, independent of flashcard generation — a source can be quizzed
  with or without ever converting to flashcards.
- On click, **one** structured/tool JSON LLM call (same injectable/mockable client pattern as 06)
  receives the source's full `raw_text` (chunked via 05's chunking helper if it exceeds context)
  and returns the **entire question set at once**: `[{question, answer}]` covering the whole note.
  No per-question follow-up calls — the LLM is invoked exactly once per quiz start.
- Processing popup while the batch generates (same polling pattern as 06), then the full question
  set loads for the session.
- Quiz UI: one question shown at a time; a **"Show Answer"** button reveals that question's answer;
  **Next / Previous** buttons navigate the pre-generated set. No free-text answer input, no
  re-querying the LLM mid-quiz, no path back to the AI after the initial call.
- The quiz set is ephemeral to the session by default — it is not persisted as `cards` and is not
  tied to SM-2 scheduling; it's a distinct, disposable artifact from flashcards, not a review mode.

## Definition of done
- Clicking "Quiz Me" on a source generates a full Q&A set in a single LLM call and starts the quiz.
- Next/Previous navigate through every question generated; Show Answer reveals/hides the answer per
  question; no additional LLM calls occur after the initial generation.

## Test seams
- **LLM boundary (mocked):** canned full-set JSON response covering multiple questions, plus a
  malformed-output failure case.
- **HTTP/session seam:** start quiz → question set loaded → next/previous navigation bounds (no
  wraparound past first/last) → show-answer toggle; verify no second LLM call happens during
  navigation.
