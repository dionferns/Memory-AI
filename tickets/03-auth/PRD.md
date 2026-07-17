# PRD: Ticket 03 — Authentication

> Ticket-scoped PRD derived from [plan.md](plan.md) + [decisions.md](decisions.md) (grilled 2026-07-17).
> GitHub issues are created at the `/to-issues` step and recorded under `issues/`.

## Problem Statement

As a user, I have no way to create an account or keep my study material private. Every later
ticket (subjects/folders, uploads, cards, review) needs to know who is making the request and
scope all data to that user, so a working register/login/logout flow with session enforcement has
to exist before any user-facing feature can be built safely.

## Solution

Email/password registration and login, bcrypt-hashed passwords, a signed JWT carried in an
httpOnly session cookie, and a `current_user` route dependency that every later protected route
depends on. Registering creates both the `users` row and its default `user_settings` row in one
transaction. Unauthenticated access to a protected route redirects to `/login` for full-page loads
and returns an HTMX-aware redirect for partial requests. Logout simply clears the cookie.

## User Stories

1. As a new user, I want to register with an email and password, so that I have a private account for my study material.
2. As a user, I want a clear error if I register with an email that's already taken, so that I know to log in instead.
3. As a user, I want a clear error if my password is too short (under 8 characters), so that I set a reasonably secure password.
4. As a user, I want my password stored as a bcrypt hash, not plaintext, so that a database breach doesn't expose my credentials.
5. As a user, I want a default `user_settings` row created automatically when I register, so that daily-review-cap and timezone settings work immediately without a separate setup step.
6. As a returning user, I want to log in with my email and password, so that I can access my subjects, folders, and cards.
7. As a user, I want a clear error on a wrong password, so that I know the login failed and why.
8. As a user, I want my session carried in an httpOnly cookie, so that my auth token can't be read or stolen by page scripts.
9. As a user on a shared machine, I want my cookie to only be sent over HTTPS in production, so that it can't be intercepted on an insecure network.
10. As a user, I want my session to stay valid for about a week without re-logging in, so that I'm not repeatedly interrupted during normal daily use.
11. As a user, I want to log out, so that my session ends on a shared machine.
12. As a user, I want visiting a protected page while logged out to send me to the login page, so that I'm not shown a confusing error instead of a clear next step.
13. As a user interacting via an HTMX partial action while logged out (e.g. a session that expired mid-use), I want to be redirected to login automatically, so that the app degrades gracefully instead of showing a broken partial update.
14. As a user, I want every later route (subjects, folders, sources, cards, reviews, settings) to only ever operate on my own data, so that my study material stays private. (This ticket delivers the `current_user` dependency those routes will depend on; the scoping itself happens in tickets 04+.)
15. As the developer, I want the JWT signed with the existing `JWT_SECRET` config value, so that no new secret-management surface is introduced.
16. As the developer, I want session length configurable via an environment setting, so that it can be tuned without a code change.

## Implementation Decisions

- **Password hashing:** bcrypt via passlib, default work factor. Minimum password length 8
  characters; no other complexity rules enforced.
- **Registration:** attempt the `users` insert directly and rely on the DB's unique constraint on
  `email`; catch the resulting `IntegrityError` and surface a friendly "email already registered"
  form error rather than pre-checking with a SELECT (avoids a check-then-insert race). The
  `user_settings` row (with sane defaults for `daily_review_cap`/`timezone`) is inserted in the
  same DB transaction as the `users` row.
- **JWT:** PyJWT, algorithm HS256, signed with the existing `JWT_SECRET` config value. Claims are
  minimal: `sub` (user id) and `exp`. A new `ACCESS_TOKEN_EXPIRE_MINUTES` setting is added to
  `memory_ai/config.py` (default `10080`, i.e. 7 days).
- **Cookie:** name `access_token`; `httpOnly=True`; `SameSite=Lax`; `Secure=True` only when
  `ENVIRONMENT=production` (the `ENVIRONMENT` setting already exists from ticket 01); `Max-Age`
  matches the JWT's expiry.
- **`current_user` dependency:** reads and validates the `access_token` cookie (signature + `exp`).
  On failure/absence: if the request has an `HX-Request` header (HTMX), respond `401` with an
  `HX-Redirect: /login` header; otherwise respond with a `302` redirect to `/login`. On success,
  loads the `User` row from the DB by `sub` and returns it for the route to use.
- **Logout:** clears the `access_token` cookie. No server-side revocation/blacklist store exists in
  v1 — a "logged out" token remains cryptographically valid until its `exp`. This is an accepted
  limitation, bounded by the 7-day expiry.
- **UI:** Jinja templates + HTMX for register/login/logout forms, with inline validation errors
  rendered via HTMX partial swaps (no full page reload on a validation failure).

## Testing Decisions

- **What makes a good test:** asserts externally observable HTTP behavior — status codes, cookie
  presence/absence/attributes, redirect targets, and DB state (user + settings rows exist) — not
  JWT library internals or ORM query internals.
- **Seam:** the HTTP seam established by ticket 02's test harness (FastAPI `TestClient` + real
  Postgres via testcontainers, transaction-rolled-back per test). No new seam.
- **Modules tested:** registration (happy path, duplicate email, short password), login (happy
  path, wrong password), logout (cookie cleared), `current_user` dependency (valid session,
  missing cookie, expired/invalid token — both as a full-page request and as an HTMX request
  asserting the different response shape).
- **Prior art:** ticket 02's test harness and fixtures; this ticket is the first to actually
  exercise them with real request/response assertions.

## Out of Scope

- Email verification, password reset, OAuth/social login, multi-factor auth.
- Server-side token revocation/blacklisting.
- Rate limiting on login/registration attempts.
- Any route-level authorization beyond "is this a valid session" — per-resource ownership
  scoping (a user can only see their own subjects/folders/etc.) is delivered by tickets 04+, which
  depend on the `current_user` dependency this ticket provides.

## Further Notes

- This ticket is the first to write real user-facing HTTP routes and templates; it's also the
  first ticket to actually exercise ticket 02's test harness end-to-end.
- `ACCESS_TOKEN_EXPIRE_MINUTES` joins `DATABASE_URL`, `ANTHROPIC_API_KEY`, `JWT_SECRET`,
  `ENVIRONMENT` in `.env.example`.
