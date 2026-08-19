import pytest
from fastapi import Request
from sqlalchemy import text

from app.db.engine import create_database_engine
from app.db.session import get_db_session
from app.main import create_app


@pytest.mark.postgresql
def test_postgresql_connectivity(postgresql_url: str) -> None:
    engine = create_database_engine(postgresql_url)

    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()


@pytest.mark.postgresql
def test_request_scoped_session_uses_application_database(postgresql_url: str) -> None:
    application = create_app(database_url=postgresql_url)
    request = Request({"type": "http", "app": application})
    session_dependency = get_db_session(request)

    session = next(session_dependency)
    try:
        assert session.scalar(text("SELECT 1")) == 1
    finally:
        session_dependency.close()
        application.state.db_engine.dispose()
