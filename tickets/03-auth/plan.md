# 03 — Authentication

**Depends on:** 02. **Goal:** register/login/logout with JWT-in-cookie and bcrypt.

## Build
- Registration: email + password → bcrypt hash (passlib) → create `users` row + default `user_settings`.
- Login: verify password → issue JWT → set an **httpOnly, Secure, SameSite** cookie.
- Logout: clear the cookie.
- A `current_user` route dependency that reads/validates the JWT cookie and rejects unauthenticated requests.
- Jinja templates + HTMX for the register/login/logout forms with inline validation errors.
- Email uniqueness enforced; friendly error on duplicate. Basic password policy (min length).

## Out of scope
- Email verification, password reset, OAuth/MFA (future tickets).

## Definition of done
- A user can register, log in, hit a protected page, and log out.
- Protected routes 401/redirect when unauthenticated.

## Test seam (HTTP)
- Register → login → access protected route → logout, asserting cookie set/cleared and access control.
- Wrong password, duplicate email, unauthenticated-access cases.
