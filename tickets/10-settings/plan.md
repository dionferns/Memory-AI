# 10 — Settings

**Depends on:** 09. **Goal:** let users configure the daily cap and timezone.

## Build
- Settings page (Jinja + HTMX) to view/update `user_settings`:
  - **daily_review_cap** (int, sensible min/max validation)
  - **timezone** (validated against a known tz list)
- Persist changes; they apply immediately to the next review computation.

## Definition of done
- Updating the cap changes how many cards the global daily review returns next.
- Updating the timezone shifts the "due today" boundary accordingly.

## Test seam (HTTP)
- Update cap → global review count changes; update timezone → due-today boundary shifts; validation
  rejects bad values.
