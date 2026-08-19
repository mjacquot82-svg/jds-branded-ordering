"""Idempotently reconcile production JDS roles and permissions."""

import os

from sqlalchemy.orm import Session

from app.db.engine import create_database_engine
from app.jds_auth.foundation import ensure_foundation


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to provision JDS authorization.")

    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            ensure_foundation(
                session,
                application_key=os.getenv("JDS_APPLICATION_KEY", "jds-commerce"),
                application_name=os.getenv("JDS_APPLICATION_NAME", "JDS Commerce"),
                organization_slug=os.getenv("JDS_ORGANIZATION_SLUG", "the-guest-house"),
                organization_name=os.getenv("JDS_ORGANIZATION_NAME", "The Guest House"),
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
