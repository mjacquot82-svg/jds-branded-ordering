"""Provision the V1 JDS application, organization, roles, and first owner invite."""

import argparse
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.engine import create_database_engine
from app.jds_auth.config import AuthSettings
from app.jds_auth.foundation import ensure_foundation
from app.jds_auth.provider import SupabaseIdentityProvider
from app.jds_auth.service import AuthenticationService


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a JDS application owner invitation.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--application-name", required=True)
    parser.add_argument("--organization-name", required=True)
    args = parser.parse_args(argv)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")
    settings = AuthSettings.from_env()
    settings.validate()
    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session:
            with session.begin():
                ensure_foundation(session, application_key=settings.application_key, application_name=args.application_name, organization_slug=settings.organization_slug, organization_name=args.organization_name)
            AuthenticationService(session, SupabaseIdentityProvider(settings), settings).create_invitation(args.email, "owner", now=datetime.now(timezone.utc), invited_by=None)
    finally:
        engine.dispose()
    print("Initial owner invitation sent.")


if __name__ == "__main__":
    main()
