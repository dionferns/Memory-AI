# 03 — Auth: Locked Decisions

Record of decisions resolved via `/grill-me` on 2026-07-17 (remaining branches resolved by the
agent's recommendation, per user instruction). Source of truth for the auth ticket.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | JWT library | PyJWT | Minimal, does exactly what's needed for HS256 encode/decode |
| 2 | Session length | 7 days, configurable via a new `ACCESS_TOKEN_EXPIRE_MINUTES` setting (default 10080) | Balances re-login friction against stolen-token exposure for a no-revocation v1 |
| 3 | Cookie `SameSite` | `Lax` | Blocks cross-site subrequests while still working on normal top-level navigation |
| 4 | Cookie `Secure` flag | `True` only when `ENVIRONMENT=production` | Lets local dev (plain HTTP via Compose) work while prod stays HTTPS-only |
| 5 | JWT algorithm | HS256, signed with the existing `JWT_SECRET` config value | Matches the single-secret (not keypair) config already committed in ticket 01 |
| 6 | JWT claims | Minimal: `sub` (user id), `exp` | Routes fetch the full `User` row from the DB via `sub`; no need to duplicate email/etc. in the token |
| 7 | Password hashing | passlib's default bcrypt work factor | No stated need to override; passlib's default is a reasonable modern default |
| 8 | Password policy | Minimum length 8 characters, no other complexity rules | Simple, avoids user-hostile complexity rules with no stated requirement for more |
| 9 | Duplicate email handling | Attempt the insert, rely on the DB unique constraint, catch the `IntegrityError` and surface a friendly form error | Avoids a check-then-insert race condition; single round trip in the common (non-duplicate) case |
| 10 | Unauthenticated protected-route handling | Full-page `GET` requests: 302 redirect to `/login`. HTMX partial requests (`HX-Request` header present): 401 with an `HX-Redirect: /login` response header | Matches the Jinja+HTMX server-rendered architecture — HTMX auto-follows `HX-Redirect`, full-page loads get a normal browser redirect |
| 11 | Logout mechanism | Clear the cookie only; no server-side token revocation/blacklist store | No revocation infra is in scope for v1; the 7-day expiry (#2) bounds the exposure of a token that "logged out" but wasn't actually invalidated |
| 12 | Cookie name | `access_token` | Simple, self-describing |
| 13 | `user_settings` creation | Same DB transaction as the `users` insert at registration (already locked in ticket 02 decision #14) | Consistency with the ticket-02 schema decision — restated here since this is the ticket that implements it |

## Notes
- `ACCESS_TOKEN_EXPIRE_MINUTES` is added to `memory_ai/config.py`'s `Settings` alongside the
  existing `JWT_SECRET`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ENVIRONMENT` fields.
- The known limitation from #11 (no server-side revocation) is accepted for v1; flagged here so
  it isn't rediscovered as a "bug" later.
