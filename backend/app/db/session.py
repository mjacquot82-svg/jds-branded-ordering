from collections.abc import Generator

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.db_session_factory

    if session_factory is None:
        raise RuntimeError("Database is not configured.")

    with session_factory() as session:
        yield session
