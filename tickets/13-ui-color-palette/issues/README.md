# Ticket 13 — UI Color Palette: GitHub Issues

Issues created for this ticket via `/to-issues` on 2026-07-18, repo `dionferns/Memory-AI`.
Vertical tracer-bullet slices, published in dependency order.

| Slice | Issue | Title | Type | Blocked by | Label | Status |
|-------|-------|-------|------|-----------|-------|--------|
| 1 | [#112](https://github.com/dionferns/Memory-AI/issues/112) | global dark stylesheet + link into every page template | AFK | None | ready-for-agent | ⏳ Open |

## Suggested implementation order

Single slice — #112 is both the tracer bullet and the whole ticket.

## Why one slice instead of more

This ticket is a single stylesheet plus linking it into existing templates — no schema, route, or
JS changes (see plan.md's scope boundary and decisions.md #6/#7). There is no independently
demoable sub-slice smaller than "the stylesheet exists with the right custom properties, is
served, and every current page links it" — splitting "add the stylesheet" from "link it into
templates" would produce a first issue with no observable effect (an unlinked CSS file changes
nothing a user or test can see) and a second issue that's pure plumbing with no design content of
its own. One vertical slice covering both is the natural (and only sensible) tracer bullet here,
matching the user's explicit "don't make things too complicated" instruction and the same
single-issue pattern used for ticket 10 (see `tickets/10-settings/issues/README.md`).

## Notes

- No HITL issues this ticket — decisions.md already locks the role mapping, theme (dark-only, no
  toggle), and delivery mechanism (CSS custom properties in one stylesheet) directly from the
  user's instructions, so there's nothing left requiring a human design call at implementation
  time.
- No new database migration, table, or route — this ticket only adds a static asset and template
  `<head>` edits, reusing the `/static` mount already added in ticket 12.
- The template list (`login.html`, `register.html`, `subjects.html`, `cards_folder.html`,
  `cards_source.html`, `settings.html`) is current as of ticket 12 on `main`; the issue body tells
  the implementing agent to re-verify against current `main` at implementation time in case a new
  full-page template has landed since (tickets 09/11/12 were still ahead of/parallel to this
  ticket in the queue as of writing).
