import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.customer_auth import current_customer
from app.jds_auth.service import AuthPrincipal


router = APIRouter(prefix="/diagnostics", tags=["runtime-diagnostics"])

TABLE_NAMES = (
    "alembic_version",
    "jds_applications",
    "organizations",
    "jds_users",
    "auth_permissions",
    "auth_roles",
    "external_identities",
    "organization_memberships",
    "owner_sessions",
    "customer_profiles",
)

TABLE_DETECTION_SQL = "SELECT pg_catalog.to_regclass(:table_name) IS NOT NULL"
INFORMATION_SCHEMA_SQL = """SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_name IN (
    'alembic_version',
    'jds_users',
    'organization_memberships',
    'auth_roles',
    'external_identities'
)
ORDER BY table_schema, table_name"""

PUBLIC_TABLES_SQL = """SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'alembic_version',
    'jds_users',
    'organization_memberships',
    'auth_roles',
    'external_identities'
  )
ORDER BY table_name"""


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def safe_database_url_identity() -> tuple[str | None, str | None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None, None
    url = make_url(database_url)
    username = url.username or ""
    project_reference = (
        username.split(".", 1)[1]
        if username.startswith("postgres.") and "." in username
        else None
    )
    return url.host, project_reference


@router.get("/database")
def database_diagnostics(
    request: Request,
    _: AuthPrincipal = Depends(current_customer),
) -> dict[str, object]:
    engine = request.app.state.db_engine
    if engine is None:
        raise HTTPException(status_code=503, detail="Database diagnostics are unavailable.")

    try:
        with engine.connect() as connection:
            runtime = connection.execute(
                text(
                    "SELECT inet_server_addr(), inet_server_port(), "
                    "pg_postmaster_start_time(), version(), current_database(), "
                    "current_user, current_schema(), current_setting('search_path')"
                )
            ).one()
            registrations = {
                name: connection.scalar(
                    text(TABLE_DETECTION_SQL),
                    {"table_name": name},
                )
                for name in TABLE_NAMES
            }
            information_schema_rows = [
                {"table_schema": row.table_schema, "table_name": row.table_name}
                for row in connection.execute(text(INFORMATION_SCHEMA_SQL))
            ]
            public_table_rows = [
                {"table_schema": row.table_schema, "table_name": row.table_name}
                for row in connection.execute(text(PUBLIC_TABLES_SQL))
            ]
            unavailable_fields: list[str] = []
            system_identifier = None
            try:
                with connection.begin_nested():
                    system_identifier = connection.scalar(
                        text("SELECT system_identifier::text FROM pg_control_system()")
                    )
            except SQLAlchemyError:
                unavailable_fields.append("pg_control_system.system_identifier")

            auth_instance_hash = None
            auth_instance_row_count = None
            try:
                with connection.begin_nested():
                    instance_ids = [
                        str(value)
                        for value in connection.scalars(
                            text("SELECT id FROM auth.instances ORDER BY id")
                        )
                    ]
                auth_instance_row_count = len(instance_ids)
                auth_instance_hash = sha256("\n".join(instance_ids))
            except SQLAlchemyError:
                unavailable_fields.extend(
                    ["auth.instances.sha256", "auth.instances.row_count"]
                )

            server_address = str(runtime[0]) if runtime[0] is not None else None
            fingerprint_source = "postgres_system_identifier"
            if system_identifier is not None:
                fingerprint_material = f"system_identifier:{system_identifier}"
            else:
                fingerprint_source = "stable_connection_identifiers"
                fingerprint_material = "|".join(
                    [
                        str(runtime[4]),
                        str(server_address),
                        str(runtime[1]),
                        str(auth_instance_hash),
                    ]
                )
            revision = None
            if registrations["alembic_version"]:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database diagnostics are unavailable.") from error

    database_url_host, supabase_project_reference = safe_database_url_identity()
    response: dict[str, object] = {
        "inet_server_addr": server_address,
        "inet_server_port": runtime[1],
        "pg_postmaster_start_time": runtime[2],
        "postgresql_version": runtime[3],
        "database": runtime[4],
        "current_user": runtime[5],
        "schema": runtime[6],
        "search_path": runtime[7],
        "database_url_host": database_url_host,
        "supabase_project_reference": supabase_project_reference,
        "database_fingerprint": {
            "sha256": sha256(fingerprint_material),
            "source": fingerprint_source,
        },
        "auth_instances_sha256": auth_instance_hash,
        "auth_instances_row_count": auth_instance_row_count,
        "unavailable_fields": unavailable_fields,
        "table_detection_sql": TABLE_DETECTION_SQL,
        "tables": registrations,
        "information_schema_rows": information_schema_rows,
        "public_table_rows": public_table_rows,
    }
    if registrations["alembic_version"]:
        response["alembic_revision"] = revision
    return response
