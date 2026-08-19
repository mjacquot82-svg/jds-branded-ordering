from datetime import date
from typing import Protocol

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.availability.models import (
    BusinessClosure,
    BusinessHour,
    BusinessSettings,
    ProductAvailability,
    ProductAvailabilityOverride,
)
from app.catalog.models import Product


class AvailabilityRepositoryProtocol(Protocol):
    def get_business_settings(self) -> BusinessSettings | None: ...

    def get_business_hour(self, weekday: int) -> BusinessHour | None: ...

    def get_business_closure(
        self,
        business_date: date,
    ) -> BusinessClosure | None: ...

    def get_product(self, product_id: int) -> Product | None: ...

    def get_product_availability(
        self,
        product_id: int,
    ) -> ProductAvailability | None: ...

    def get_product_availability_override(
        self,
        product_id: int,
        business_date: date,
    ) -> ProductAvailabilityOverride | None: ...


class AvailabilityRepository:
    """Persistence primitives for sellability and pickup scheduling."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entity: object) -> None:
        self._session.add(entity)

    def get_business_settings(self) -> BusinessSettings | None:
        return self._session.get(BusinessSettings, 1)

    def get_business_hour(self, weekday: int) -> BusinessHour | None:
        return self._session.scalar(
            select(BusinessHour).where(
                BusinessHour.business_settings_id == 1,
                BusinessHour.weekday == weekday,
            )
        )

    def get_business_closure(
        self,
        business_date: date,
    ) -> BusinessClosure | None:
        return self._session.scalar(
            select(BusinessClosure).where(
                BusinessClosure.business_settings_id == 1,
                BusinessClosure.business_date <= business_date,
                or_(
                    and_(
                        BusinessClosure.reopens_on.is_(None),
                        BusinessClosure.business_date == business_date,
                    ),
                    BusinessClosure.reopens_on > business_date,
                ),
            )
        )

    def list_business_hours(self) -> list[BusinessHour]:
        return list(
            self._session.scalars(
                select(BusinessHour)
                .where(BusinessHour.business_settings_id == 1)
                .order_by(BusinessHour.weekday)
            )
        )

    def list_business_closures(self) -> list[BusinessClosure]:
        return list(
            self._session.scalars(
                select(BusinessClosure)
                .where(BusinessClosure.business_settings_id == 1)
                .order_by(BusinessClosure.business_date, BusinessClosure.id)
            )
        )

    def get_product(self, product_id: int) -> Product | None:
        return self._session.scalar(
            select(Product)
            .options(joinedload(Product.category))
            .where(Product.id == product_id)
        )

    def get_product_availability(
        self,
        product_id: int,
    ) -> ProductAvailability | None:
        return self._session.get(ProductAvailability, product_id)

    def get_product_availability_override(
        self,
        product_id: int,
        business_date: date,
    ) -> ProductAvailabilityOverride | None:
        return self._session.scalar(
            select(ProductAvailabilityOverride).where(
                ProductAvailabilityOverride.product_id == product_id,
                ProductAvailabilityOverride.business_date == business_date,
            )
        )
