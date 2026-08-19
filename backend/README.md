# Guest House Backend

Minimal FastAPI foundation for The Guest House Café & Pantry preorder
application.

Phase 1A provides only:

- a FastAPI application factory
- an ASGI application entry point
- `GET /health/live`
- one automated liveness test

Phase 1B adds:

- PostgreSQL connectivity through SQLAlchemy
- request-scoped database sessions
- an empty Alembic migration framework
- `GET /health/ready`
- PostgreSQL integration tests

Phase 1C adds only the production catalog domain foundation:

- categories and products
- optional product variants
- reusable modifier groups and modifier options
- product-to-modifier-group assignments
- SQLAlchemy models and a small repository boundary
- one reversible Alembic migration with PostgreSQL constraints

Phase 1C does not add seed data, catalog APIs, catalog mutation, availability,
orders, customers, checkout, Clover, payments, or frontend integration.

Phase 1D adds only the deterministic initial Guest House catalog seed. It maps
the current frontend catalog to the Phase 1C schema, converts prices to integer
cents, and models drink sizes as product variants. The seed is transactional,
idempotent, and does not delete records outside the reviewed fixture.

Phase 1E adds only the read-only production catalog API. It assembles published
categories and products with active variants and modifiers from PostgreSQL.
The React application is not connected to this endpoint during Phase 1E.

## JDS owner authentication foundation

Owner authentication is a reusable backend-for-frontend module under
`app/jds_auth`. Supabase Auth owns credentials, verified email, recovery, and
future MFA. JDS PostgreSQL owns organizations, memberships, roles, permissions,
opaque sessions, invitations, authorization, and security audit events.

Production configuration requires:

```text
SUPABASE_AUTH_URL
SUPABASE_AUTH_PUBLISHABLE_KEY
SUPABASE_AUTH_SECRET_KEY
JDS_AUTH_SESSION_PEPPER
JDS_APPLICATION_KEY
JDS_ORGANIZATION_SLUG
```

In the Supabase dashboard, disable public signups, require email confirmation,
configure custom SMTP, and customize invite/recovery templates so their links
carry `token_hash` to the corresponding frontend acceptance page. Never expose
the Supabase secret key or provider session tokens to the browser.

After applying migrations, provision the application, organization, built-in
roles, permissions, and first owner invitation deliberately:

```bash
python -m app.jds_auth.bootstrap_owner \
  --email owner@example.com \
  --application-name "JDS Commerce" \
  --organization-name "The Guest House"
```

The command is idempotent for foundation records. Owner authentication does not
initialize on customer routes and is independent of Clover OAuth.

## Requirements

- Python 3.12

## Local setup

Run these commands from the `backend` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

## Start the backend

Set a PostgreSQL connection URL before starting:

```bash
export DATABASE_URL="postgresql+psycopg://guesthouse:password@127.0.0.1:5432/guesthouse"
```

The database must already exist. Alembic creates the Phase 1C catalog tables.

```bash
uvicorn app.main:app --reload
```

The backend is available at `http://127.0.0.1:8000`.

## Clover

OAuth v2 and Hosted Checkout configuration is documented in
`../docs/CLOVER_INTEGRATION_SETUP.md`. Copy `../.env.example`, deploy the API
behind HTTPS, run `python -m app.db.migrate`, and configure the resulting
`PUBLIC_APP_URL` in Clover before connecting a merchant.

Production Render configuration and the Supabase connection procedure are
documented in `../docs/RENDER_DEPLOYMENT.md`.

Check liveness:

```bash
curl http://127.0.0.1:8000/health/live
```

Expected response:

```json
{
  "status": "ok",
  "service": "guesthouse-backend",
  "version": "0.1.0"
}
```

Check readiness:

```bash
curl http://127.0.0.1:8000/health/ready
```

Expected response with PostgreSQL available:

```json
{
  "status": "ready",
  "database": "ok"
}
```

Readiness returns HTTP `503` when `DATABASE_URL` is missing or PostgreSQL
cannot be reached.

## Alembic

Set `DATABASE_URL`, then run:

```bash
python -m app.db.migrate
alembic current
```

The guarded migration command safely adopts an existing, unversioned
revision-1 catalog schema only after validating it. Direct `alembic upgrade
head` remains appropriate for development databases already managed by
Alembic.

To verify the reversible Phase 1C migration:

```bash
alembic downgrade base
alembic upgrade head
```

## Seed the Guest House catalog

Apply migrations, set `DATABASE_URL`, and run:

```bash
python -m app.catalog.seed
```

Running the command again updates the same stable catalog records without
duplicating them. Validation and persistence run in one transaction, so a
failure leaves the database unchanged.

## Read the catalog

With PostgreSQL configured, migrated, and seeded:

```bash
curl http://127.0.0.1:8000/api/v1/catalog
```

The endpoint returns one versioned catalog document with deterministic nested
ordering. It returns only published categories and products and active
variants, modifier assignments, modifier groups, and modifier options.

## Run tests

Tests require an isolated PostgreSQL database. Tests migrate, truncate, and
roll back catalog tables, so the database must not be shared with staging or
production.

```bash
export TEST_DATABASE_URL="postgresql+psycopg://guesthouse:password@127.0.0.1:5432/guesthouse_test"
pytest
```
