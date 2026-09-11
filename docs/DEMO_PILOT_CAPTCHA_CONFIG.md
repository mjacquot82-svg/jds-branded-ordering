# Optional CAPTCHA for controlled demo pilot

M2.5 implements invite-code gating and rate limits without requiring a CAPTCHA
vendor. Enable CAPTCHA only if Marc wants bot scoring before wider sharing.

## Supported providers (config only until keys exist)

| Provider | `JDS_DEMO_CAPTCHA_PROVIDER` |
| --- | --- |
| Cloudflare Turnstile | `turnstile` |
| hCaptcha | `hcaptcha` |
| Google reCAPTCHA v2/v3 | `recaptcha` |

## Exact Marc steps

1. Create a vendor account (Turnstile recommended for low/no cost).
2. Create a site key allowed for the pilot hostname only.
3. Create a secret key; store in Render secrets / password manager — never git.
4. Set on the **pilot** API service:

```text
JDS_DEMO_CAPTCHA_PROVIDER=turnstile
JDS_DEMO_CAPTCHA_SITE_KEY=...
JDS_DEMO_CAPTCHA_SECRET_KEY=...
```

5. Redeploy API. `GET /api/v1/demo/pilot-config` should report `captcha.enabled: true` and the site key.
6. Frontend will render the widget only when enabled (wire-up may follow once keys exist; invite gate works today without CAPTCHA).

Until keys exist, leave these unset. Do not create a paid CAPTCHA plan without Marc’s approval.
