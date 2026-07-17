# 07 — Card CRUD: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (this is a small, simple CRUD ticket;
branches resolved by the agent's recommendation rather than an interactive interview, per user
instruction). Source of truth for the card-crud ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Editable fields | `front` and `back` only | Ticket 02's schema separates content fields from scheduling fields; edit is a content correction, not a scheduling reset |
| 2 | Fields an edit never touches | `ease_factor`, `interval_days`, `repetitions`, `due_date`, `last_reviewed_at` | Explicit restatement of plan.md's "does not disturb scheduling state" — the edit route only ever writes `front`/`back` (+ `updated_at` if one exists), never the SM-2 columns |
| 3 | Front/back emptiness | Both required; rejected (with an inline validation error) if empty/whitespace-only after trimming | An empty card is never useful; matches the same "clear inline error" pattern ticket 03 used for password length |
| 4 | Front/back max length | No app-level max length beyond the DB `TEXT` column (unbounded) | No stated requirement for a cap; the AI-generated content in ticket 06 is already unbounded text, so a new cap here would be an arbitrary, unrequested restriction |
| 5 | Edit interaction shape | HTMX partial: clicking "Edit" swaps the card's display into an inline form; submitting swaps it back to the (updated) display, no full page reload | Matches plan.md's explicit "Jinja + HTMX UI for inline edit/delete"; keeps state (scroll position, rest of the list) intact |
| 6 | Delete interaction shape | HTMX partial: clicking "Delete" swaps the card into an inline "Confirm delete? / Cancel" pair; confirming removes the card's element from the DOM (`hx-swap` remove) | Same inline-partial pattern as edit; avoids introducing a modal component for a single low-stakes confirm |
| 7 | Delete confirmation UX | Inline two-step confirm (not a modal, not a plain `confirm()` JS dialog) | Consistent with the no-SPA, server-rendered HTMX architecture; a native `confirm()` dialog would be the one non-HTMX interaction pattern in the app |
| 8 | Delete cascade | Deleting a card removes its `reviews` rows via the DB-level `ON DELETE CASCADE` FK already established in ticket 02 (decision #5); no app-level cleanup code needed | Restates ticket 02's existing schema-level guarantee so it isn't rediscovered as ambiguous here; the card-delete route just issues a single `DELETE` on `cards` |
| 9 | Card listing scope | Two list views, both user-scoped: (a) **per-source** — `GET /sources/{source_id}/cards`, the primary entry point (reachable from a source's page, e.g. right after ticket 06's "Convert to Flashcards" completes); (b) **per-folder** — `GET /folders/{folder_id}/cards`, an aggregate view of every card across every source in that folder | Resolves plan.md's "for a source (and/or folder)" — both are needed: per-source is where a user reviews freshly-generated cards for quality, per-folder is where they browse everything they've accumulated in a topic without picking a source first |
| 10 | List ordering | `created_at ascending` (oldest/first-generated first), no pagination in v1 | Simplest predictable order; no stated scale requirement that needs pagination yet |
| 11 | Authorization | Every card route resolves ownership via the `user → subject → folder → source → card` join chain and 404s (not 403) if the requesting user doesn't own the resolved card/source/folder | Matches the "cards only reachable/mutable by their owning user" requirement in plan.md; 404 (vs. 403) avoids leaking the existence of another user's resources, consistent with how ticket 04's hierarchy scoping is expected to behave |
| 12 | Route style | Plain REST-ish routes (`GET`/`PATCH`/`DELETE` under `/sources/{id}/cards` and `/cards/{id}`), reusing the `current_user` dependency from ticket 03 | No new auth/routing primitive needed; consistent with tickets 03/04's established pattern |

## Notes
- This ticket depends on ticket 06 (AI-generated cards must exist before there's anything to
  view/edit/delete) and, transitively, on ticket 04's folder/subject scoping and ticket 02's schema.
  Ticket 06 is being planned in parallel and had not yet published a PRD/issues at the time this
  ticket was grilled, so ticket 06 is referenced in prose (not by issue number) throughout this
  ticket's PRD and issues.
- No HITL branches; all decisions above were resolvable from existing tickets 02/03/06(plan) plus
  ordinary product judgment for a small CRUD surface.
