# PRD: Ticket 13 — UI Color Palette

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (decided
> in-session 2026-07-18, no `/grill-me` interview needed — see decisions.md header).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

Every page in the app currently renders as unstyled default-browser HTML — no CSS exists anywhere
in the codebase. The user supplied a 4-color palette and asked for it to be applied across the UI
now, with the color *scheme itself* (which role gets which color) to be revisited later. Without
this, the app is functionally complete (tickets 01–12) but visually a wall of black-on-white
browser defaults.

## Solution

Add one global dark-themed stylesheet (`src/memory_ai/static/styles.css`) built on CSS custom
properties for the four supplied colors plus the minimal neutrals needed for contrast (body text
color, a border/divider tone), and link it from every existing full-page template's `<head>`. Pure
styling — no schema, route, or JS behavior changes.

## User Stories

1. As a user, I want the app to use a coherent dark color scheme instead of unstyled default HTML, so it looks and feels like a real product.
2. As a user, I want destructive actions (delete) and failure states (failed flashcard generation) to read visually as "danger", so I can tell them apart from normal/positive states at a glance.
3. As a user, I want primary actions and success/positive states (buttons, links, "done" status) to read visually as the "go" color, consistent across every page.
4. As a developer, I want the palette defined once as CSS custom properties, so a future color-scheme change (the user's stated next step) only touches one file.

## Implementation Decisions

See [decisions.md](decisions.md) for the full table. Summary:
- `#1c1c1c` background · `#2c4251` surface · `#28965a` primary/positive accent · `#d16666`
  destructive/danger accent · one added neutral for body text (~`#e8e8e8`) · one derived
  border/divider tone from the surface color.
- Single stylesheet, linked from every current page template's `<head>`.
- No base/layout template refactor, no light/dark toggle, no JS or schema changes.

## Acceptance Criteria (ticket-level)

- [ ] `src/memory_ai/static/styles.css` exists, defines the palette as CSS custom properties on
      `:root`, and is served at `GET /static/styles.css`.
- [ ] Every existing full-page template (`login.html`, `register.html`, `subjects.html`,
      `cards_folder.html`, `cards_source.html`, `settings.html` — re-verify this list against
      current `main` at implementation time) links the stylesheet in its `<head>`.
- [ ] Page background, surface elements (cards/rows/forms/inputs), primary/positive accents, and
      destructive/danger accents each visibly use their mapped palette color, not browser
      defaults.
- [ ] Body text remains readable (sufficient contrast) against the dark background.
- [ ] No new database migration, table, route, or JS behavior change is introduced.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` (strict), and
      `uv run pytest` all pass in CI.

## Out of Scope

- Light/dark toggle.
- Redesigning layout, spacing, or component structure beyond what's needed for the colors to read
  correctly.
- Any change to which named role gets which color (the user said they'll revisit that).
- Database schema changes of any kind.
