from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


def create_database_engine(database_url: str) -> Engine:
    url = make_url(database_url)

    if url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must use PostgreSQL.")

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        # Pin every session to UTC so timestamps (and day arithmetic across DST
        # changes) never depend on the database server's local time zone.
        connect_args={"options": "-c timezone=UTC"},
    )
