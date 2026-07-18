# 13 — UI Color Palette

A pure visual styling pass over the existing app. Every page currently renders as unstyled
default-browser HTML (no CSS anywhere in `src/memory_ai/templates` or a `static/` stylesheet
besides `quiz.js`). This ticket adds one global dark-themed stylesheet using a user-supplied
4-color palette and links it from every existing page template. No schema changes, no new
routes, no new interaction/behavior — colors and basic layout polish only. The user has said
they'll revisit the color *scheme itself* (i.e. which named colors map to what) later; this
ticket just needs to apply the given palette sensibly now.

## Supplied palette

- `#1c1c1c` — near-black charcoal
- `#2c4251` — dark slate blue
- `#d16666` — muted coral/red
- `#28965a` — muted green

## Scope

- One global stylesheet (`src/memory_ai/static/styles.css`), dark theme only (no light/dark
  toggle).
- Link it from every existing full-page template's `<head>`.
- Map the four supplied colors to background/surface/destructive-accent/positive-accent roles.
- Add the minimal supporting neutrals (text color, borders) needed for readable contrast on a
  dark background — the palette itself has no light color for text, so this ticket has to pick
  one.
- Out of scope: dark/light toggle, per-component redesign, layout restructuring, any DB/schema
  change, JS behavior change.
