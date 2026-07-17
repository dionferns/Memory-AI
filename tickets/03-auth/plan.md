# 03 — Authentication

**Depends on:** 02. **Goal:** register/login/logout with JWT-in-cookie and bcrypt.

> Decisions locked via `/grill-me` on 2026-07-17 — see [decisions.md](decisions.md).

## Build
- Registration: email + password (min 8 chars) → bcrypt hash (passlib, default work factor) →
  insert `users` row + default `user_settings` row in one transaction. Duplicate email relies on
  the DB unique constraint, catching `IntegrityError` for a friendly form error (no pre-check
  SELECT).
- Login: verify password → issue a **PyJWT** HS256 token (claims: `sub`=user id, `exp`) signed
  with `JWT_SECRET` → set it in a cookie named `access_token`
  (**httpOnly**, `SameSite=Lax`, `Secure` only when `ENVIRONMENT=production`, `Max-Age` matching
  the token's expiry).
- Session length: 7 days, via a new `ACCESS_TOKEN_EXPIRE_MINUTES` setting in `config.py` (default
  10080).
- Logout: clear the `access_token` cookie. No server-side revocation store — accepted v1
  limitation, bounded by the 7-day expiry.
- A `current_user` route dependency that reads/validates the JWT cookie and rejects unauthenticated
  requests: full-page `GET`s get a 302 redirect to `/login`; HTMX partial requests (`HX-Request`
  header present) get a 401 with `HX-Redirect: /login` so htmx follows it client-side.
- Jinja templates + HTMX for the register/login/logout forms with inline validation errors.

## Out of scope
- Email verification, password reset, OAuth/MFA (future tickets).
- Server-side token revocation/blacklisting.

## Definition of done
- A user can register, log in, hit a protected page, and log out.
- Protected routes redirect (full page) or 401+`HX-Redirect` (HTMX) when unauthenticated.

## Test seam (HTTP)
- Register → login → access protected route → logout, asserting cookie set/cleared and access control.
- Wrong password, duplicate email, unauthenticated-access cases (both full-page and HTMX request styles).
