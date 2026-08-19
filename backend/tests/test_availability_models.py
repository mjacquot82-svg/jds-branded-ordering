from collections.abc import Iterator
from datetime import date, time

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.availability.models import (
    BusinessClosure,
    BusinessHour,
    BusinessSettings,
    ProductAvailability,
    ProductAvailabilityOverride,
)
from app.availability.repository import AvailabilityRepository
from app.catalog.models import Category, Product
from tests.test_migrations import make_alembic_config
from app.tenancy.resolver import (
    LADELS_ORGANIZATION_ID,
    resolve_internal_ladels_compatibility_context,
)


@pytest.fixture
def availability_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

    def reset_tables() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE product_availability_overrides, "
                    "product_availability, business_closures, business_hours, "
                    "business_settings, product_modifier_groups, "
                    "modifier_options, product_variants, products, "
                    "modifier_groups, categories RESTART IDENTITY CASCADE"
                )
            )

    reset_tables()
    try:
        yield engine
    finally:
        reset_tables()
        engine.dispose()


def make_product() -> Product:
    return Product(
        category=Category(
            organization_id=LADELS_ORGANIZATION_ID,
            slug="coffee",
            name="Coffee",
            description=None,
            is_published=True,
            sort_order=0,
        ),
        organization_id=LADELS_ORGANIZATION_ID,
        slug="drip-coffee",
        name="Drip Coffee",
        description=None,
        base_price_cents=350,
        image_reference=None,
        is_published=True,
        is_featured=True,
        sort_order=0,
    )


@pytest.mark.postgresql
def test_models_persist_settings_hours_closures_and_availability(
    availability_engine: Engine,
) -> None:
    with Session(availability_engine) as session:
        settings = BusinessSettings(
            organization_id=LADELS_ORGANIZATION_ID,
            timezone="America/New_York",
            ordering_enabled=True,
            minimum_lead_time_minutes=15,
            pickup_interval_minutes=5,
            maximum_advance_days=14,
        )
        settings.hours.extend(
            [
                BusinessHour(
                    weekday=0,
                    is_closed=False,
                    opens_at=time(7),
                    closes_at=time(15),
                ),
                BusinessHour(
                    weekday=1,
                    is_closed=True,
                    opens_at=None,
                    closes_at=None,
                ),
            ]
        )
        settings.closures.append(
            BusinessClosure(
                business_date=date(2026, 12, 25),
                reason="Christmas Day",
            )
        )
        product = make_product()
        product.availability = ProductAvailability(
            default_available=False,
            reason="Seasonal",
        )
        product.availability_overrides.append(
            ProductAvailabilityOverride(
                business_date=date(2026, 7, 28),
                is_available=True,
                reason=None,
            )
        )
        session.add_all([settings, product])
        session.commit()

        repository = AvailabilityRepository(
            session, resolve_internal_ladels_compatibility_context(session)
        )
        assert repository.get_business_settings() is settings
        assert repository.get_business_hour(0) is settings.hours[0]
        assert (
            repository.get_business_closure(date(2026, 12, 25))
            is settings.closures[0]
        )
        assert repository.get_product(product.id) is product
        assert repository.get_product_availability(product.id) is product.availability
        assert (
            repository.get_product_availability_override(
                product.id,
                date(2026, 7, 28),
            )
            is product.availability_overrides[0]
        )


@pytest.mark.postgresql
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: BusinessSettings(
                timezone=" ",
                minimum_lead_time_minutes=15,
                pickup_interval_minutes=5,
                maximum_advance_days=14,
            ),
            "timezone must not be blank",
        ),
        (
            lambda: BusinessSettings(
                timezone="UTC",
                minimum_lead_time_minutes=-1,
                pickup_interval_minutes=5,
                maximum_advance_days=14,
            ),
            "minimum_lead_time_minutes must be nonnegative",
        ),
        (
            lambda: BusinessSettings(
                timezone="UTC",
                minimum_lead_time_minutes=15,
                pickup_interval_minutes=1441,
                maximum_advance_days=14,
            ),
            "pickup_interval_minutes must be between 1 and 1440",
        ),
        (
            lambda: BusinessSettings(
                timezone="UTC",
                minimum_lead_time_minutes=15,
                pickup_interval_minutes=5,
                maximum_advance_days=366,
            ),
            "maximum_advance_days must be between 1 and 365",
        ),
        (
            lambda: BusinessHour(
                weekday=7,
                is_closed=True,
                opens_at=None,
                closes_at=None,
            ),
            "weekday must be between zero and six",
        ),
        (
            lambda: BusinessClosure(
                business_date=date(2026, 7, 28),
                reason=" ",
            ),
            "reason must not be blank",
        ),
    ],
)
def test_model_field_validation(factory: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.postgresql
@pytest.mark.parametrize(
    "hours",
    [
        BusinessHour(
            weekday=0,
            is_closed=False,
            opens_at=None,
            closes_at=None,
        ),
        BusinessHour(
            weekday=0,
            is_closed=False,
            opens_at=time(15),
            closes_at=time(7),
        ),
        BusinessHour(
            weekday=0,
            is_closed=True,
            opens_at=time(7),
            closes_at=time(15),
        ),
    ],
)
def test_business_hour_model_rejects_invalid_periods(
    availability_engine: Engine,
    hours: BusinessHour,
) -> None:
    with Session(availability_engine) as session:
        settings = BusinessSettings(
            organization_id=LADELS_ORGANIZATION_ID,
            timezone="UTC",
            ordering_enabled=True,
            minimum_lead_time_minutes=0,
            pickup_interval_minutes=5,
            maximum_advance_days=14,
        )
        settings.hours.append(hours)
        session.add(settings)
        with pytest.raises(ValueError):
            session.flush()


@pytest.mark.postgresql
def test_database_constraints_enforce_business_invariants(
    availability_engine: Engine,
) -> None:
    invalid_statements = [
        (
            "INSERT INTO business_settings "
            "(id, organization_id, timezone, minimum_lead_time_minutes, "
            "pickup_interval_minutes, maximum_advance_days) "
            f"VALUES (1, '{LADELS_ORGANIZATION_ID}', 'UTC', -1, 5, 14)"
        ),
    ]

    for statement in invalid_statements:
        with pytest.raises(IntegrityError):
            with availability_engine.begin() as connection:
                connection.execute(text(statement))

    with availability_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO business_settings "
                "(id, organization_id, timezone, minimum_lead_time_minutes, "
                "pickup_interval_minutes, maximum_advance_days) "
                f"VALUES (1, '{LADELS_ORGANIZATION_ID}', 'UTC', 15, 5, 14)"
            )
        )

    with pytest.raises(IntegrityError):
        with availability_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO business_settings "
                    "(organization_id, timezone) "
                    f"VALUES ('{LADELS_ORGANIZATION_ID}', 'UTC')"
                )
            )

    invalid_child_statements = [
        (
            "INSERT INTO business_hours "
            "(business_settings_id, weekday, is_closed, opens_at, closes_at) "
            "VALUES (1, 7, true, NULL, NULL)"
        ),
        (
            "INSERT INTO business_hours "
            "(business_settings_id, weekday, is_closed, opens_at, closes_at) "
            "VALUES (1, 0, false, '15:00', '07:00')"
        ),
        (
            "INSERT INTO business_closures "
            "(business_settings_id, business_date, reason) "
            "VALUES (1, '2026-12-25', ' ')"
        ),
    ]

    for statement in invalid_child_statements:
        with pytest.raises(IntegrityError):
            with availability_engine.begin() as connection:
                connection.execute(text(statement))


@pytest.mark.postgresql
def test_database_enforces_unique_daily_overrides_and_cascades(
    availability_engine: Engine,
) -> None:
    with Session(availability_engine) as session:
        product = make_product()
        product.availability = ProductAvailability(default_available=True)
        product.availability_overrides.append(
            ProductAvailabilityOverride(
                business_date=date(2026, 7, 28),
                is_available=False,
                reason="Sold out",
            )
        )
        session.add(product)
        session.commit()
        product_id = product.id

    with pytest.raises(IntegrityError):
        with availability_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO product_availability_overrides "
                    "(product_id, business_date, is_available) "
                    "VALUES (:product_id, '2026-07-28', true)"
                ),
                {"product_id": product_id},
            )

    with availability_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM products WHERE id = :product_id"),
            {"product_id": product_id},
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM product_availability"))
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM product_availability_overrides")
            )
            == 0
        )
