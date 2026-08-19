"""Explicit import entry point for the reviewed Cafe Pricing catalog.

The normal catalog seed command remains unchanged. This command must be invoked
deliberately after the staging review is approved.
"""

import os

from app.catalog.cafe_pricing_seed_data import CAFE_PRICING_CATALOG
from app.catalog.seed import seed_catalog
from app.db.engine import create_database_engine
from app.db.session import create_session_factory


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to import the catalog.")

    engine = create_database_engine(database_url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            seed_catalog(session, CAFE_PRICING_CATALOG)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
