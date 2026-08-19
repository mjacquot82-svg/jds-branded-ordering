import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
)
from app.catalog.seed_data import (
    GUEST_HOUSE_CATALOG,
    CatalogSeed,
    validate_catalog_seed,
)
from app.db.engine import create_database_engine
from app.db.session import create_session_factory
from app.tenancy.context import TenantContext
from app.tenancy.resolver import resolve_internal_ladels_compatibility_context


def seed_catalog(
    session: Session,
    catalog: CatalogSeed = GUEST_HOUSE_CATALOG,
) -> None:
    """Upsert the reviewed Guest House catalog in one transaction."""

    with session.begin():
        tenant = resolve_internal_ladels_compatibility_context(session)
        validate_catalog_seed(catalog)
        categories = _seed_categories(session, tenant, catalog)
        modifier_groups = _seed_modifier_groups(session, tenant, catalog)
        _seed_products(session, tenant, catalog, categories, modifier_groups)


def _seed_categories(
    session: Session,
    tenant: TenantContext,
    catalog: CatalogSeed,
) -> dict[str, Category]:
    existing = {
        category.slug: category
        for category in session.scalars(
            select(Category).where(
                Category.organization_id == tenant.organization_id,
                Category.slug.in_(
                    category_seed.slug for category_seed in catalog.categories
                )
            )
        )
    }

    for sort_order, category_seed in enumerate(catalog.categories):
        category = existing.get(category_seed.slug)
        if category is None:
            category = Category(
                organization_id=tenant.organization_id,
                slug=category_seed.slug,
            )
            session.add(category)
            existing[category_seed.slug] = category

        category.name = category_seed.name
        category.description = category_seed.description
        category.is_published = True
        category.sort_order = sort_order

    session.flush()
    return existing


def _seed_modifier_groups(
    session: Session,
    tenant: TenantContext,
    catalog: CatalogSeed,
) -> dict[str, ModifierGroup]:
    existing = {
        group.key: group
        for group in session.scalars(
            select(ModifierGroup).where(
                ModifierGroup.organization_id == tenant.organization_id,
                ModifierGroup.key.in_(
                    group_seed.key for group_seed in catalog.modifier_groups
                )
            )
        )
    }

    for sort_order, group_seed in enumerate(catalog.modifier_groups):
        group = existing.get(group_seed.key)
        if group is None:
            group = ModifierGroup(
                organization_id=tenant.organization_id,
                key=group_seed.key,
            )
            session.add(group)
            existing[group_seed.key] = group

        group.name = group_seed.name
        group.description = None
        group.selection_type = group_seed.selection_type
        group.is_required = group_seed.is_required
        group.minimum_selections = group_seed.minimum_selections
        group.maximum_selections = group_seed.maximum_selections
        group.is_active = True
        group.sort_order = sort_order
        session.flush()

        options_by_key = {
            option.key: option
            for option in session.scalars(
                select(ModifierOption).where(
                    ModifierOption.modifier_group_id == group.id,
                    ModifierOption.key.in_(
                        option_seed.key for option_seed in group_seed.options
                    ),
                )
            )
        }
        for option_sort_order, option_seed in enumerate(group_seed.options):
            option = options_by_key.get(option_seed.key)
            if option is None:
                option = ModifierOption(
                    modifier_group=group,
                    key=option_seed.key,
                )
                session.add(option)

            option.name = option_seed.name
            option.price_adjustment_cents = option_seed.price_adjustment_cents
            option.is_active = True
            option.sort_order = option_sort_order

    session.flush()
    return existing


def _seed_products(
    session: Session,
    tenant: TenantContext,
    catalog: CatalogSeed,
    categories: dict[str, Category],
    modifier_groups: dict[str, ModifierGroup],
) -> None:
    existing = {
        product.slug: product
        for product in session.scalars(
            select(Product).where(
                Product.organization_id == tenant.organization_id,
                Product.slug.in_(
                    product_seed.slug for product_seed in catalog.products
                )
            )
        )
    }

    for sort_order, product_seed in enumerate(catalog.products):
        product = existing.get(product_seed.slug)
        if product is None:
            product = Product(
                organization_id=tenant.organization_id,
                slug=product_seed.slug,
            )
            session.add(product)
            existing[product_seed.slug] = product

        product.category = categories[product_seed.category_slug]
        product.name = product_seed.name
        product.description = product_seed.description
        product.base_price_cents = product_seed.base_price_cents
        product.image_reference = product_seed.image_reference
        product.is_published = True
        product.is_featured = product_seed.is_featured
        product.sort_order = sort_order
        product.archived_at = None
        session.flush()

        variants_by_key = {
            variant.key: variant
            for variant in session.scalars(
                select(ProductVariant).where(
                    ProductVariant.product_id == product.id,
                    ProductVariant.key.in_(
                        variant_seed.key for variant_seed in product_seed.variants
                    ),
                )
            )
        }
        for variant_sort_order, variant_seed in enumerate(product_seed.variants):
            variant = variants_by_key.get(variant_seed.key)
            if variant is None:
                variant = ProductVariant(product=product, key=variant_seed.key)
                session.add(variant)

            variant.name = variant_seed.name
            variant.price_cents = variant_seed.price_cents
            variant.is_active = True
            variant.sort_order = variant_sort_order

        assignments_by_group_id = {
            assignment.modifier_group_id: assignment
            for assignment in session.scalars(
                select(ProductModifierGroup).where(
                    ProductModifierGroup.product_id == product.id,
                    ProductModifierGroup.modifier_group_id.in_(
                        modifier_groups[key].id
                        for key in product_seed.modifier_group_keys
                    ),
                )
            )
        }
        for assignment_sort_order, group_key in enumerate(
            product_seed.modifier_group_keys
        ):
            group = modifier_groups[group_key]
            assignment = assignments_by_group_id.get(group.id)
            if assignment is None:
                assignment = ProductModifierGroup(
                    product=product,
                    modifier_group=group,
                )
                session.add(assignment)

            assignment.is_active = True
            assignment.sort_order = assignment_sort_order


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to seed the catalog.")

    engine = create_database_engine(database_url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            seed_catalog(session)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
