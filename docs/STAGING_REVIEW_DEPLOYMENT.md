# Persistent staging review deployment

This package defines a synthetic, fail-closed review environment. It must use a
dedicated Netlify site, Render service, Render PostgreSQL database, and media
disk. Never clone a production environment group or restore production data.

## Netlify

Use the generated Netlify HTTPS hostname for the first review. Configure the
dedicated site to build the approved staging branch with
`netlify.staging.toml` selected through Netlify's configuration-path setting.
The staging build validates the public Render API origin
and writes same-origin `/api/*`, `/health/*`, and `/robots.txt` proxy rules ahead
of the SPA fallback. Netlify supplies the browser-facing forwarded host and
HTTPS semantics. Do not set `VITE_API_BASE_URL`; no backend secret belongs in a
`VITE_` variable.

Required Netlify environment-variable names:

```text
JDS_STAGING_API_ORIGIN
NETLIFY_CONFIG_PATH
```

## Render

Review `render.staging.yaml`, then use it only to create dedicated staging
resources after approval. Automatic deploy is disabled. The backend build is
performed from `backend`, migrations run as the pre-deploy command, Uvicorn
binds Render's assigned port, `/health/ready` is the health check, and the media
root is backed by the attached persistent disk.

Run the synthetic seed as an explicit one-off command after migrations and
before opening review access:

```text
python -m app.staging_review_seed
```

Required Render environment-variable names:

```text
DATABASE_URL
FRONTEND_URL
PUBLIC_APP_URL
JDS_ENVIRONMENT
JDS_ENABLE_STAGING_REVIEW
JDS_STAGING_INSTANCE_ID
JDS_STAGING_ALLOWED_HOSTS
JDS_STAGING_AUTH_PASSWORD
JDS_STAGING_SEED_CONFIRMATION
JDS_AUTH_PROVIDER
JDS_AUTH_SESSION_PEPPER
JDS_AUTH_SECURE_COOKIES
JDS_APPLICATION_KEY
JDS_ORGANIZATION_SLUG
JDS_STOREFRONT_SCHEME
JDS_DEFAULT_BILLING_PLAN_KEY
JDS_BILLING_ENFORCEMENT_ENABLED
JDS_LOCAL_MEDIA_ROOT
JDS_PAYMENT_MODE
JDS_OUTBOUND_INTEGRATIONS_ENABLED
PUSH_ENROLLMENT_ENABLED
PUSH_RELEASE_ENABLED
```

Do not configure Supabase, Clover, VAPID, email, or other production integration
credentials. Staging startup intentionally refuses them. Secret values belong
only in Render's secret environment configuration and a password manager.

## Initial generated-host review

Use `?review_tenant=the-guest-house` or
`?review_tenant=second-street-cafe` on the generated Netlify hostname. This
selection is restricted to the two fixed synthetic tenants, is stored in a
secure HTTP-only staging cookie, and affects public storefront resolution only.
Owner authorization and business switching remain membership-scoped.

The staging banner, disabled Clover/payment endpoints, `robots.txt`, and
`X-Robots-Tag` must be verified before sharing the URL. Upload a Design Studio
image, restart the backend, and verify the image remains available from the
persistent disk.
