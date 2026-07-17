# 10 — Settings: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (small ticket; no open questions for
the user — all branches resolved by the agent's own reasoned recommendation, per user
instruction). Source of truth for the settings ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | `daily_review_cap` bounds | Integer, `1..500` inclusive | 1 is the smallest meaningful cap (0 would make the global review pointless and is better expressed as "review nothing" by just not reviewing); 500 comfortably exceeds any realistic single-session workload while still catching fat-fingered input (e.g. an extra zero) |
| 2 | `timezone` validation | Must be a member of Python's `zoneinfo.available_timezones()` (IANA tz database) | Standard library, no new dependency; matches the IANA names users recognize (e.g. `America/New_York`); avoids inventing a custom allow-list |
| 3 | Settings form UX | Single form (Jinja + HTMX partial submit) with both fields, inline validation errors on the same partial swap | Consistent with the auth/hierarchy forms established in tickets 03/04; one save action is simpler than per-field saves for only two fields |
| 4 | Invalid input handling | Reject the whole submission with inline field errors; no partial apply | Prevents a half-updated settings row (e.g. cap saved but timezone silently rejected) which would be confusing and hard to reason about from the UI |
| 5 | Where validation lives | App code (route handler / form-handling layer), not a DB constraint | Consistent with ticket 02 decision #6 (validate app-side, not via DB CHECK constraints); keeps error messages friendly and swappable without a migration |
| 6 | Effect of a change | Applies immediately to the next review computation (no cache/invalidation step) | `daily_review_cap` and `timezone` are read fresh from `user_settings` on each review request per ticket 09's design; nothing to invalidate |
| 7 | Timezone list presented in the UI | Full `zoneinfo.available_timezones()` set, sorted, offered as a `<select>` (or a text input with datalist) rather than a curated shortlist | Avoids maintaining a second, incomplete list that could drift from what validation actually accepts |

## Notes
- No new database migration is needed — `user_settings.daily_review_cap` (int, not null) and
  `user_settings.timezone` (string, not null) already exist from ticket 02's schema
  (`src/memory_ai/models.py`).
- This ticket only builds the settings *page* and its update endpoint(s); it does not change how
  ticket 09's review queries read `daily_review_cap`/`timezone` — it only changes the values they
  read.
- Ticket 09 (review-flows) is a dependency but has not landed yet at the time this ticket is
  planned (parallel planning); the PRD and issues reference it by ticket number, not a merged
  issue number, until it exists.
