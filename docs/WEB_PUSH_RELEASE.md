# Ladel's Web Push release runbook

Web Push enrollment and sending are both off by default. PostgreSQL is the durable source of truth. The existing API triggers bounded outbox drains after a send and on Communications refresh, and its lifespan runs the same bounded drain once per minute. A process crash can delay a queued notification until the API restarts, but cannot erase it.

Generate production VAPID keys with the installed standards library (never in the browser):

```bash
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); v.save_key('vapid-private.pem'); v.save_public_key('vapid-public.pem')"
```

Store the private key contents in `WEB_PUSH_VAPID_PRIVATE_KEY`, the URL-safe unpadded public application-server key in `WEB_PUSH_VAPID_PUBLIC_KEY`, and a monitored `mailto:` or HTTPS contact in `WEB_PUSH_VAPID_SUBJECT`. Generate an independent Fernet key for `WEB_PUSH_SUBSCRIPTION_ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Private values belong only in Render secret environment variables. Never prefix them with `VITE_`, log them, or expose them through an API. The public VAPID key is returned to authenticated customers only when the release is active.

Release procedure:

1. Deploy and run Alembic revision `20260809_15` while `PUSH_ENROLLMENT_ENABLED=false` and `PUSH_RELEASE_ENABLED=false`.
2. Configure the VAPID and encryption values on the existing API service.
3. Confirm `/service-worker.js` is JavaScript (not the SPA HTML), root-scoped, and served with no-cache headers.
4. Set `PUSH_ENROLLMENT_ENABLED=true` temporarily and enroll the authenticated acceptance-test device. Sending remains blocked while `PUSH_RELEASE_ENABLED=false`.
5. In a short controlled test window, set `PUSH_RELEASE_ENABLED=true`, redeploy, send only the authoritative Lunch Special test, and inspect its accepted/failed result. Then set it back to `false` if public release is not approved.
6. For release, leave enrollment enabled and set `PUSH_RELEASE_ENABLED=true`. Confirm Communications says release-enabled, queue a controlled announcement, and verify only honest `accepted`/`failed` results.

No separate Render worker is required at expected café scale. The API response is returned only after the announcement and delivery rows commit; Web Push network calls run afterward as a bounded trigger. If that trigger is interrupted, the existing API's once-per-minute drain reclaims and drains durable work after startup. Communications also polls while work remains, without coupling delivery to ordering or payment traffic.

## Key custody and recovery

Treat the production VAPID key pair and `WEB_PUSH_SUBSCRIPTION_ENCRYPTION_KEY` as long-lived release credentials. Back them up in an access-controlled secret manager independently of Render before enrollment opens. Casual rotation is prohibited: the database intentionally does not implement a keyring for this café-scale release.

- Losing or changing the Fernet subscription-encryption key makes existing encrypted browser capabilities unreadable. Restore the exact backed-up key. If it cannot be recovered, revoke the affected database subscriptions, deploy a new key, and ask customers to enable Café notifications again.
- Changing the VAPID key pair changes the browser application-server identity. Restore the backed-up pair where possible. If rotation is unavoidable, disable release sending, deploy the new pair, revoke existing subscription rows, and ask customers to re-enable Café notifications so the browser creates a matching subscription.
- Never print private keys, subscription endpoints, `p256dh`, or auth secrets in logs or diagnostics. Only the VAPID public key may be returned to the authenticated enrollment UI.

Account opt-out and device revoke are checked again immediately before each provider call. Already-unsent work is recorded as suppressed. A narrow unavoidable race remains if provider transmission has begun before the opt-out/revoke transaction commits; provider-accepted attempts remain immutable audit history.

General announcements expire four hours after queueing by default (`PUSH_GENERAL_TTL_SECONDS=14400`, bounded to 5 minutes–24 hours). Expired work is retained in activity history and recorded as expired when dispatch resumes; disabling and later re-enabling release sending cannot resurrect it. Lunch Special announcements retain the café-day/11 p.m. cutoff. `clicked_count` is reserved but stays zero because click telemetry is intentionally not collected in the first release.
