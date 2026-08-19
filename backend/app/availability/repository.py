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
from app.tenancy.context import TenantContext


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

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    @property
    def tenant(self) -> TenantContext:
        return self._tenant

    def add(self, entity: object) -> None:
        if isinstance(
            entity,
            (
                BusinessSettings,
                BusinessHour,
                BusinessClosure,
                ProductAvailability,
                ProductAvailabilityOverride,
            ),
        ):
            existing = entity.organization_id
            if existing is not None and existing != self._tenant.organization_id:
                raise ValueError("Availability entity belongs to another organization.")
            entity.organization_id = self._tenant.organization_id
        self._session.add(entity)

    def get_business_settings(self) -> BusinessSettings | None:
        return self._session.scalar(
            select(BusinessSettings).where(
                BusinessSettings.organization_id == self._tenant.organization_id
            )
        )

    def get_business_hour(self, weekday: int) -> BusinessHour | None:
        return self._session.scalar(
            select(BusinessHour).where(
                BusinessHour.organization_id == self._tenant.organization_id,
                BusinessHour.weekday == weekday,
            )
        )

    def get_business_closure(
        self,
        business_date: date,
    ) -> BusinessClosure | None:
        return self._session.scalar(
            select(BusinessClosure).where(
                BusinessClosure.organization_id == self._tenant.organization_id,
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
                .where(BusinessHour.organization_id == self._tenant.organization_id)
                .order_by(BusinessHour.weekday)
            )
        )

    def list_business_closures(self) -> list[BusinessClosure]:
        return list(
            self._session.scalars(
                select(BusinessClosure)
                .where(BusinessClosure.organization_id == self._tenant.organization_id)
                .order_by(BusinessClosure.business_date, BusinessClosure.id)
            )
        )

    def get_business_closure_by_id(self, closure_id: int) -> BusinessClosure | None:
        return self._session.scalar(
            select(BusinessClosure).where(
                BusinessClosure.organization_id == self._tenant.organization_id,
                BusinessClosure.id == closure_id,
            )
        )

    def get_product(self, product_id: int) -> Product | None:
        return self._session.scalar(
            select(Product)
            .options(joinedload(Product.category))
            .where(
                Product.organization_id == self._tenant.organization_id,
                Product.id == product_id,
            )
        )

    def get_product_availability(
        self,
        product_id: int,
    ) -> ProductAvailability | None:
        return self._session.scalar(
            select(ProductAvailability).where(
                ProductAvailability.organization_id == self._tenant.organization_id,
                ProductAvailability.product_id == product_id,
            )
        )

    def get_product_availability_override(
        self,
        product_id: int,
        business_date: date,
    ) -> ProductAvailabilityOverride | None:
        return self._session.scalar(
            select(ProductAvailabilityOverride).where(
                ProductAvailabilityOverride.organization_id
                == self._tenant.organization_id,
                ProductAvailabilityOverride.product_id == product_id,
                ProductAvailabilityOverride.business_date == business_date,
            )
        )
