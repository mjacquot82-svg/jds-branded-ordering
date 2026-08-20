import httpx
import pytest
from uuid import uuid4

from app.jds_auth.provider import (
    IdentityProviderError,
    ProviderAuthentication,
    ProviderIdentity,
)
from app.api.v1.customer_auth import current_customer, get_customer_auth_service
from app.api.v1.catalog import ladels_compatibility_tenant
from app.jds_auth.config import AuthSettings
from app.jds_auth.service import AuthPrincipal
from app.main import create_app


class DiagnosticsProvider:
    def authenticate_access_token(self, token: str) -> ProviderAuthentication:
        if token != "valid-token":
            raise IdentityProviderError("invalid")
        return ProviderAuthentication(
            identity=ProviderIdentity(
                issuer="https://example.supabase.co/auth/v1",
                subject="identity-id",
                email="verified@example.com",
                email_verified=True,
                assurance_level="aal1",
            ),
            access_token=token,
        )


def diagnostics_app(postgresql_url: str):
    app = create_app(
        database_url=postgresql_url,
        auth_settings=AuthSettings(
            supabase_url="https://identity.example.test",
            supabase_publishable_key="publishable",
            supabase_secret_key="secret",
            session_pepper="p" * 48,
            frontend_url="http://test",
            secure_cookies=False,
        ),
        auth_provider=DiagnosticsProvider(),
    )
    app.dependency_overrides[ladels_compatibility_tenant] = lambda: object()
    return app


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_database_diagnostics_requires_authentication(postgresql_url: str) -> None:
    app = diagnostics_app(postgresql_url)
    app.dependency_overrides[get_customer_auth_service] = lambda: object()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/diagnostics/database")
    app.state.db_engine.dispose()
    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_database_diagnostics_reports_only_runtime_schema_state(
    postgresql_url: str,
) -> None:
    app = diagnostics_app(postgresql_url)
    app.dependency_overrides[current_customer] = lambda: AuthPrincipal(
        user_id=uuid4(),
        membership_id=uuid4(),
        organization_id=uuid4(),
        application_id=uuid4(),
        session_id=uuid4(),
        email="customer@example.com",
        display_name="Customer",
        role="customer",
        permissions=frozenset(),
        assurance_level="aal1",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/diagnostics/database",
        )

    app.state.db_engine.dispose()
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) <= {
        "inet_server_addr", "inet_server_port", "pg_postmaster_start_time",
        "postgresql_version", "database", "schema", "current_user", "search_path",
        "database_url_host", "supabase_project_reference", "database_fingerprint",
        "auth_instances_sha256", "auth_instances_row_count", "unavailable_fields",
        "table_detection_sql", "tables", "information_schema_rows",
        "public_table_rows", "alembic_revision",
    }
    assert len(payload["database_fingerprint"]["sha256"]) == 64
    assert payload["database_fingerprint"]["source"] in {
        "postgres_system_identifier", "stable_connection_identifiers"
    }
    assert payload["database_url_host"] is None
    assert payload["supabase_project_reference"] is None
    assert payload["table_detection_sql"] == (
        "SELECT pg_catalog.to_regclass(:table_name) IS NOT NULL"
    )
    assert all(
        set(row) == {"table_schema", "table_name"}
        for row in payload["information_schema_rows"]
    )
    assert all(
        set(row) == {"table_schema", "table_name"}
        for row in payload["public_table_rows"]
    )
    assert set(payload["tables"]) == {
        "alembic_version", "jds_applications", "organizations", "jds_users",
        "auth_permissions", "auth_roles", "external_identities",
        "organization_memberships", "owner_sessions", "customer_profiles",
    }
    assert all(isinstance(exists, bool) for exists in payload["tables"].values())
    assert not {
        "database_url", "username", "password", "token", "connection_string"
    } & set(payload)
