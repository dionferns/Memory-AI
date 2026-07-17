# 07 — Card Management

**Depends on:** 06. **Goal:** let users view, edit, and delete cards (correcting AI mistakes).

> Ambiguities resolved via `/grill-me` in [decisions.md](decisions.md) (2026-07-17) — see that
> file for exact edit validation, edit/delete interaction shape, delete confirmation UX, which
> fields an edit may touch, cascade-delete behavior, and how card listing is scoped (source
> and/or folder).

## Build
- View all cards for a source (and/or folder), user-scoped.
- Edit a card's front/back.
- Delete a card.
- Jinja + HTMX UI for inline edit/delete.
- Authorization: cards only reachable/mutable by their owning user.

## Definition of done
- Full view/edit/delete of cards through the UI, correctly scoped.
- Editing does not disturb the card's scheduling state; deleting removes it and its reviews.

## Test seam (HTTP)
- Edit and delete happy paths; cross-user access denied; edit preserves scheduling fields.
