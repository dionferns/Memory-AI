# 13 — UI Color Palette: Locked Decisions

Record of decisions made directly from the user's instructions in-session (small, fully-specified
styling ticket; user explicitly said "don't make things too complicated" and delegated the
dark/light mapping call to the agent — no `/grill-me` interview needed). Source of truth for this
ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Palette source values | `#1c1c1c`, `#2c4251`, `#d16666`, `#28965a` | User-supplied. The first value was typed as "cc1c1c1" in chat, which isn't a valid 6-digit hex; read as a typo for `#1c1c1c` (repeated leading `c`, matches the "near-black charcoal" role the other three colors imply is needed) |
| 2 | Theme | Dark theme only, no light/dark toggle | User said not to overcomplicate it; a toggle is a feature, not a palette application |
| 3 | Role mapping | `#1c1c1c` = page background · `#2c4251` = surface (cards/rows/forms/inputs) · `#28965a` = primary accent (buttons, links, positive/success/"done" states) · `#d16666` = destructive/warning accent (delete actions, error/failed states) | Matches conventional dark-UI roles: darkest value as base background, next-darkest as elevated surface, green as "go"/primary, red/coral as "stop"/destructive — and matches existing app semantics (e.g. ticket 06's `status=failed` vs `status=done`, ticket 07's delete confirmation) |
| 4 | Body text color | New neutral off-white (e.g. `#e8e8e8`), not part of the supplied palette | The 4 given colors are all backgrounds/accents; none are light enough for body text on a dark background. Necessary addition for readable contrast; documented here so it's not mistaken for an unauthorized 5th brand color |
| 5 | Borders/dividers | A muted mid-tone derived from `#2c4251` (e.g. lightened ~15%), not a new named color | Keeps the palette to the 4 supplied hues plus the one necessary text neutral; avoids inventing more "brand" colors |
| 6 | Delivery mechanism | One global stylesheet at `src/memory_ai/static/styles.css`, CSS custom properties (`--bg`, `--surface`, `--accent-primary`, `--accent-danger`, `--text`, `--border`) for the palette, linked via `<link rel="stylesheet" href="/static/styles.css">` added to every existing page template's `<head>` | Single source of truth for the palette (easy to swap later per the user's "I'll improve the schema later" — meaning the color *scheme*, not the DB schema); reuses the `/static` mount already added in ticket 12 |
| 7 | Scope boundary | Colors + minimal contrast/spacing polish only; no layout restructuring, no shared base/layout template refactor, no JS changes | User: "don't make things too complicated ... just improve the colour palette" |
| 8 | Testing approach | HTTP-seam tests: `GET /static/styles.css` returns 200 with the expected custom-property values present; each existing full-page route's rendered HTML includes the stylesheet `<link>` tag | Matches the project's existing test-the-HTTP-seam convention; there's no browser-rendering test harness in this repo (ticket 12 used a Node-based JS unit test for the one case that needed real execution — not applicable here since there's no JS logic to test) |

## Notes
- No new database migration, no new tables, no new routes — this ticket only adds a static asset
  and template `<head>` edits.
- Templates to update (every current full-page template as of `main` at ticket 12's merge):
  `login.html`, `register.html`, `subjects.html`, `cards_folder.html`, `cards_source.html`,
  `settings.html`. Any full-page template merged after this ticket is planned (unlikely, since
  09/11 are still ahead in the queue) should also get the link — call this out in the issue so
  whoever implements checks current `main` at implementation time, not just this list.
- "I will improve the schema later" refers to the color scheme/role mapping (decision #3), not the
  database schema — no DB work is implied or in scope here.
