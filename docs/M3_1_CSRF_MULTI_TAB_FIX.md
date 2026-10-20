# M3.1: saves failing in multi-tab sessions (CSRF token rotated on session read)

Resolves the B-level item in `docs/M3_STARTER_IMAGE_LIBRARY_REPORT.md`: "`GET /api/v1/owner/auth/session` rotates the CSRF token. A second tab (or any extra session read) makes the first tab's next save fail with 403."

## Root cause

- `GET /api/v1/owner/auth/session` (`read_session` in `backend/app/api/v1/owner_auth.py`) called `AuthenticationService.rotate_csrf` (`backend/app/jds_auth/service.py`).
- `rotate_csrf` minted a new random token (`create_secret()`) and **overwrote** `owner_sessions.csrf_token_hash` on every read.
- `csrf_principal` → `verify_csrf` accepts only the token whose hash is stored, so each session read invalidated the previous token.
- The frontend calls `refreshSession()` → `fetchOwnerSession()` (`src/auth/OwnerAuthContext.jsx`) on every app load. It keeps `session.csrf_token` in memory per tab.

So when tab B opened or reloaded, every other tab of the same login was left holding a dead token, and its next write (design save, product update and so on) got `403 csrf_invalid` ("CSRF validation failed."). The customer endpoint `GET /api/v1/customer/auth/session` had the same bug through the same method.

## Fix (server-side, no migration)

- `backend/app/jds_auth/security.py`: new `derive_csrf_token(session_token, pepper)`. It computes `HMAC-SHA256(pepper, "jds.auth.csrf.v1:" + session_token)`, base64url-encoded. This is the OWASP HMAC-based synchronizer-token pattern. The prefix separates it from other uses of the pepper. `:` and `.` are not in the `token_urlsafe` alphabet, so no other peppered secret can hash to the same input.
- `backend/app/jds_auth/service.py`:
  - `_issue` (every login, org switch, staff PIN login, activation and demo signup) now sets the CSRF token to `derive_csrf_token(new_session_token)` instead of a second random value. The stored `csrf_token_hash` and `verify_csrf` are unchanged: the header must still match the peppered hash on that session's row.
  - `rotate_csrf` is replaced by `session_csrf`. It resolves the session exactly as before and returns the derived token. It writes nothing when the stored hash already matches.
  - A session issued before this deploy still has a random token hash. The first `session_csrf` call re-binds it to the derived token, once (the old behaviour, one last time). After that it is stable, so nobody is signed out by the deploy.
- `owner_auth.read_session` and `customer_auth.read_session` call `session_csrf`.

No schema change and no Alembic migration. The frontend is unchanged: it already treats the token as opaque and sends whatever the latest session or login response returned.

## Security reasoning

- **Still bound to the session.** Computing the token needs both the HttpOnly `__Host-` session cookie and the server-side pepper (at least 32 characters, enforced by `AuthSettings`). A cross-site attacker can read neither. Verification still compares against the hash stored on the session row the cookie resolves to, so another session's token (another user, another tenant, or an older session of the same user) fails.
- **Still rotated where it matters.** Every new session gets a new opaque token and therefore a new CSRF token. That covers login (session-fixation defence), organization switch (`select_organization` issues a new session), staff login and activation. Logout, idle or absolute expiry, a `security_version` bump, or membership deactivation revokes or invalidates the session, so the request fails authentication (401) before CSRF is even checked.
- **Unchanged checks.** Missing or empty header: 403. Wrong value: 403. Trusted-Origin check: 403 for a foreign origin, independent of the token. Client-supplied tenant context: 403. Cross-tenant ids: 404. Tenant resolution is untouched.
- **Why not "accept the previous token too" or a frontend retry?** Keeping a grace window of old tokens widens what is accepted and still breaks with three or more tabs. A frontend "refetch and retry on 403" would hide the bug rather than fix it, and could replay non-idempotent POSTs. The server fix removes the cause, so the frontend needs no retry.
- **Why not store the token itself?** That needs a migration and puts a usable secret in the DB. The derived token is recomputed from the cookie and never stored in usable form: only its peppered hash is stored, as before.

## Trade-offs / remaining risks

- **Longer-lived token.** The CSRF token now lives as long as the session: up to `session_absolute_hours` (12h), or 30 days for a customer "keep me signed in" session. Before, it lived until the next session read. It is only useful together with the session cookie from the same browser and the correct Origin, and it dies with the session.
- **BREACH.** The token is static per session and appears in the JSON body of the login, session and select responses. The app adds no response compression (no GZip middleware), and those responses reflect no attacker-controlled input. If an edge proxy compresses them, the classic BREACH preconditions are still largely absent. Per-response masking (random pad XOR token, as Django does) is a possible hardening follow-up.
- **Logging.** The token is sent only in the `X-CSRF-Token` header and in response bodies, never in URLs, so access logs don't capture it. Nothing in the app logs it.
- **Other tabs after logout.** Logging out in one tab revokes the shared session. Other open tabs get 401 on their next request and must sign in again, the same as before.
- **Pepper rotation** already invalidates every session (session-token hashes use the same pepper), and the CSRF tokens go with them.

## Tests

`backend/tests/test_owner_csrf_multi_tab_m31.py` (11 tests):

- Regressions (fail on 5cd7ac2, pass now):
  - Owner two-tab design and product save.
  - The session read doesn't rewrite the stored hash.
  - Customer two-tab profile save.
  - `session_csrf` is idempotent.
  - A pre-existing session is re-bound once, then stable.
- Security invariants (pass before and after):
  - Missing, empty, forged or wrong-pepper token: 403.
  - Valid token with a foreign Origin: 403.
  - Another user's token: 403.
  - Token after logout, in every tab: 401.
  - A fresh login issues a new session and CSRF token, and the old token is refused on the new session.
  - Prospect 1's valid token can't modify prospect 2's product (404) or design (tenant header 403).

Real browser (local HTTPS dev server, Chrome through Playwright, two pages in one context, prospect1): tab A edits the design, tab B opens, refocuses and reloads the same studio, then tab A clicks "Save my design".
- Old server: `PUT /api/v1/owner/design` returned 403 and the page showed "CSRF validation failed."
- Fixed server: 200, "Design saved.", and the change persisted. Tab B's saves also returned 200.

## Results

- New test file on 5cd7ac2 code: **5 failed, 6 passed**. Every regression test fails; tab A's save returns `403 csrf_invalid`. On this branch: **11 passed**.
- Full backend suite (`PGTZ=UTC`): **419 passed** (baseline 408 + 11 new).
- Security and tenant subset (`test_tenant_*`, `test_v1_platform_isolation`, `test_jds_auth`, `test_checkout_authorization`, `test_owner_db_pool_m3`, plus the new file): **111 passed**.
- Frontend: **427/427** (no frontend change). Production build OK (same >500 kB chunk warning as before).
- Alembic: no migration added; single head `20260910_33`.
