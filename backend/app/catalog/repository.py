from collections.abc import Sequence
import hashlib

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
)
from app.availability.models import ProductAvailability
from app.tenancy.context import TenantContext


class CatalogRepository:
    """Database access primitives for catalog persistence and public reads."""

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    @property
    def tenant(self) -> TenantContext:
        return self._tenant

    @property
    def lunch_special_lock_key(self) -> int:
        digest = hashlib.blake2b(
            self._tenant.organization_id.bytes,
            digest_size=8,
            person=b"jds-lunch",
        ).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    def add(self, entity: object) -> None:
        if isinstance(entity, (Category, Product, ModifierGroup)):
            existing = entity.organization_id
            if existing is not None and existing != self._tenant.organization_id:
                raise ValueError("Catalog entity belongs to another organization.")
            entity.organization_id = self._tenant.organization_id
        self._session.add(entity)

    def lock_lunch_special_selection(self) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": self.lunch_special_lock_key},
        )

    def get_category_by_slug(self, slug: str) -> Category | None:
        return self._session.scalar(
            select(Category).where(
                Category.organization_id == self._tenant.organization_id,
                Category.slug == slug,
            )
        )

    def get_product_by_slug(self, slug: str) -> Product | None:
        return self._session.scalar(
            select(Product).where(
                Product.organization_id == self._tenant.organization_id,
                Product.slug == slug,
            )
        )

    def get_product(self, product_id: int) -> Product | None:
        return self._session.scalar(
            select(Product).where(
                Product.organization_id == self._tenant.organization_id,
                Product.id == product_id,
            )
        )

    def get_product_for_update(self, product_id: int) -> Product | None:
        return self._session.scalar(
            select(Product).where(
                Product.organization_id == self._tenant.organization_id,
                Product.id == product_id,
            ).with_for_update()
        )

    def get_category(self, category_id: int) -> Category | None:
        return self._session.scalar(
            select(Category).where(
                Category.organization_id == self._tenant.organization_id,
                Category.id == category_id,
            )
        )

    def list_products(self) -> Sequence[Product]:
        return self._session.scalars(
            select(Product)
            .options(
                joinedload(Product.availability),
                selectinload(Product.variants),
                selectinload(Product.modifier_group_assignments),
            )
            .where(
                Product.organization_id == self._tenant.organization_id,
                Product.archived_at.is_(None),
            ).order_by(
                Product.category_id, Product.sort_order, Product.name, Product.id
            )
        ).all()

    def list_modifier_groups(self) -> Sequence[ModifierGroup]:
        return self._session.scalars(
            select(ModifierGroup)
            .options(
                joinedload(ModifierGroup.options),
                selectinload(ModifierGroup.product_assignments),
            )
            .where(ModifierGroup.organization_id == self._tenant.organization_id)
            .order_by(
                ModifierGroup.sort_order, ModifierGroup.name, ModifierGroup.id
            )
        ).unique().all()

    def get_modifier_group(self, group_id: int) -> ModifierGroup | None:
        return self._session.scalar(
            select(ModifierGroup)
            .options(
                selectinload(ModifierGroup.options),
                selectinload(ModifierGroup.product_assignments),
            )
            .where(
                ModifierGroup.organization_id == self._tenant.organization_id,
                ModifierGroup.id == group_id,
            )
        )

    def get_modifier_option(self, group_id: int, option_id: int) -> ModifierOption | None:
        return self._session.scalar(
            select(ModifierOption).join(ModifierGroup).where(
                ModifierGroup.organization_id == self._tenant.organization_id,
                ModifierOption.id == option_id,
                ModifierOption.modifier_group_id == group_id,
            )
        )

    def modifier_group_key_exists(self, key: str) -> bool:
        return self._session.scalar(
            select(func.count()).select_from(ModifierGroup).where(
                ModifierGroup.organization_id == self._tenant.organization_id,
                ModifierGroup.key == key,
            )
        ) > 0

    def modifier_option_key_exists(self, group_id: int, key: str) -> bool:
        return self._session.scalar(
            select(func.count()).select_from(ModifierOption).join(ModifierGroup).where(
                ModifierGroup.organization_id == self._tenant.organization_id,
                ModifierOption.modifier_group_id == group_id,
                ModifierOption.key == key,
            )
        ) > 0

    def replace_modifier_assignments(
        self, product_id: int, modifier_group_ids: Sequence[int]
    ) -> None:
        product = self.get_product(product_id)
        if product is None:
            raise LookupError("Product not found.")
        scoped_group_ids = set(
            self._session.scalars(
                select(ModifierGroup.id).where(
                    ModifierGroup.organization_id == self._tenant.organization_id,
                    ModifierGroup.id.in_(modifier_group_ids),
                )
            )
        )
        if scoped_group_ids != set(modifier_group_ids):
            raise ValueError("Modifier group belongs to another organization.")
        self._session.execute(
            delete(ProductModifierGroup).where(ProductModifierGroup.product_id == product_id)
        )
        for sort_order, group_id in enumerate(modifier_group_ids):
            self.add(ProductModifierGroup(
                product_id=product_id,
                modifier_group_id=group_id,
                is_active=True,
                sort_order=sort_order,
            ))

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def clear_lunch_special(self, *, except_product_id: int | None = None) -> None:
        statement = update(Product).where(
            Product.organization_id == self._tenant.organization_id,
            Product.is_lunch_special.is_(True),
        )
        if except_product_id is not None:
            statement = statement.where(Product.id != except_product_id)
        self._session.execute(statement.values(is_lunch_special=False))

    def get_modifier_group_by_key(self, key: str) -> ModifierGroup | None:
        return self._session.scalar(
            select(ModifierGroup).where(
                ModifierGroup.organization_id == self._tenant.organization_id,
                ModifierGroup.key == key,
            )
        )

    def list_categories(self) -> Sequence[Category]:
        return self._session.scalars(
            select(Category)
            .where(Category.organization_id == self._tenant.organization_id)
            .order_by(Category.sort_order, Category.id)
        ).all()

    def list_published_categories(self) -> Sequence[Category]:
        return self._session.scalars(
            select(Category)
            .where(
                Category.organization_id == self._tenant.organization_id,
                Category.is_published.is_(True),
            )
            .order_by(Category.sort_order, Category.name, Category.id)
        ).all()

    def list_published_products(
        self,
        category_ids: Sequence[int],
    ) -> Sequence[Product]:
        return self._session.scalars(
            select(Product)
            .outerjoin(ProductAvailability, ProductAvailability.product_id == Product.id)
            .where(
                Product.category_id.in_(category_ids),
                Product.organization_id == self._tenant.organization_id,
                Product.is_published.is_(True),
                Product.archived_at.is_(None),
                func.coalesce(ProductAvailability.default_available, True).is_(True),
            )
            .order_by(
                Product.category_id,
                Product.sort_order,
                Product.name,
                Product.id,
            )
        ).all()

    def list_active_variants(
        self,
        product_ids: Sequence[int],
    ) -> Sequence[ProductVariant]:
        return self._session.scalars(
            select(ProductVariant).join(Product)
            .where(
                Product.organization_id == self._tenant.organization_id,
                ProductVariant.product_id.in_(product_ids),
                ProductVariant.is_active.is_(True),
            )
            .order_by(
                ProductVariant.product_id,
                ProductVariant.sort_order,
                ProductVariant.name,
                ProductVariant.id,
            )
        ).all()

    def list_active_modifier_assignments(
        self,
        product_ids: Sequence[int],
    ) -> list[tuple[ProductModifierGroup, ModifierGroup]]:
        return [
            (assignment, group)
            for assignment, group in self._session.execute(
                select(ProductModifierGroup, ModifierGroup)
                .join(
                    ModifierGroup,
                    ProductModifierGroup.modifier_group_id == ModifierGroup.id,
                )
                .join(Product, Product.id == ProductModifierGroup.product_id)
                .where(
                    Product.organization_id == self._tenant.organization_id,
                    ModifierGroup.organization_id == self._tenant.organization_id,
                    ProductModifierGroup.product_id.in_(product_ids),
                    ProductModifierGroup.is_active.is_(True),
                    ModifierGroup.is_active.is_(True),
                )
                .order_by(
                    ProductModifierGroup.product_id,
                    ProductModifierGroup.sort_order,
                    ModifierGroup.name,
                    ModifierGroup.id,
                )
            ).all()
        ]

    def list_active_modifier_options(
        self,
        modifier_group_ids: Sequence[int],
    ) -> Sequence[ModifierOption]:
        return self._session.scalars(
            select(ModifierOption).join(ModifierGroup)
            .where(
                ModifierGroup.organization_id == self._tenant.organization_id,
                ModifierOption.modifier_group_id.in_(modifier_group_ids),
                ModifierOption.is_active.is_(True),
            )
            .order_by(
                ModifierOption.modifier_group_id,
                ModifierOption.sort_order,
                ModifierOption.name,
                ModifierOption.id,
            )
        ).all()
