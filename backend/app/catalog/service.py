from collections import defaultdict
from datetime import datetime, timezone
import re

from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
)
from app.availability.models import ProductAvailability
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import (
    CatalogResponse,
    CatalogPricingResponse,
    CategoryResponse,
    ModifierOptionResponse,
    ProductModifierGroupResponse,
    ProductResponse,
    ProductVariantResponse,
    OwnerCatalogResponse,
    OwnerCategoryResponse,
    OwnerModifierGroupResponse,
    OwnerModifierGroupWrite,
    OwnerModifierOptionResponse,
    OwnerModifierOptionWrite,
    OwnerProductResponse,
    OwnerProductWrite,
    OwnerVariantResponse,
)

CATALOG_CONTRACT_VERSION = "1"


class CatalogService:
    def __init__(
        self,
        repository: CatalogRepository,
        *,
        tax_name: str | None = None,
        tax_rate_millionths: int | None = None,
    ) -> None:
        self._repository = repository
        self._tax_name = tax_name
        self._tax_rate_millionths = tax_rate_millionths

    def build_catalog(self) -> CatalogResponse:
        categories = self._repository.list_published_categories()
        category_ids = [category.id for category in categories]
        products = self._repository.list_published_products(category_ids)
        product_ids = [product.id for product in products]

        variants_by_product: dict[int, list[ProductVariantResponse]] = defaultdict(list)
        for variant in self._repository.list_active_variants(product_ids):
            variants_by_product[variant.product_id].append(
                ProductVariantResponse(
                    id=str(variant.id),
                    key=variant.key,
                    name=variant.name,
                    price_cents=variant.price_cents,
                    sort_order=variant.sort_order,
                )
            )

        assignments = self._repository.list_active_modifier_assignments(product_ids)
        modifier_group_ids = list(
            dict.fromkeys(group.id for _, group in assignments)
        )
        options_by_group = self._options_by_group(modifier_group_ids)
        groups_by_product = self._groups_by_product(
            assignments,
            options_by_group,
        )

        products_by_category: dict[int, list[ProductResponse]] = defaultdict(list)
        for product in products:
            products_by_category[product.category_id].append(
                self._product_response(
                    product,
                    variants_by_product[product.id],
                    groups_by_product[product.id],
                )
            )

        return CatalogResponse(
            version=CATALOG_CONTRACT_VERSION,
            generated_at=datetime.now(timezone.utc),
            pricing=CatalogPricingResponse(
                tax_name=self._tax_name,
                tax_rate_millionths=self._tax_rate_millionths,
            ),
            categories=[
                CategoryResponse(
                    id=str(category.id),
                    slug=category.slug,
                    name=category.name,
                    note=category.description or "",
                    sort_order=category.sort_order,
                    products=products_by_category[category.id],
                )
                for category in categories
            ],
        )

    def build_owner_catalog(self) -> OwnerCatalogResponse:
        categories = self._repository.list_categories()
        groups = self._repository.list_modifier_groups()
        return OwnerCatalogResponse(
            categories=[OwnerCategoryResponse(
                id=str(item.id), slug=item.slug, name=item.name,
                note=item.description or "", published=item.is_published,
                sort_order=item.sort_order,
            ) for item in categories],
            modifier_groups=[OwnerModifierGroupResponse(
                id=str(item.id), key=item.key, name=item.name,
                description=item.description or "", selection_type=item.selection_type,
                required=item.is_required, min_selections=item.minimum_selections,
                max_selections=item.maximum_selections, active=item.is_active,
                allow_quantity=item.allow_quantity,
                sort_order=item.sort_order,
                assignment_count=len(item.product_assignments),
                options=[self._owner_option_response(option) for option in sorted(
                    item.options, key=lambda value: (value.sort_order, value.name, value.id or 0)
                )],
            ) for item in groups],
            products=[self._owner_product_response(item) for item in self._repository.list_products()],
        )

    def create_modifier_group(self, payload: OwnerModifierGroupWrite) -> OwnerModifierGroupResponse:
        self._validate_group_write(payload)
        group = ModifierGroup(key=self._unique_group_key(payload.name))
        self._apply_group(group, payload)
        self._repository.add(group)
        self._repository.commit()
        return self._owner_group_response(group)

    def update_modifier_group(
        self, group_id: int, payload: OwnerModifierGroupWrite
    ) -> OwnerModifierGroupResponse:
        group = self._repository.get_modifier_group(group_id)
        if group is None:
            raise LookupError("Modifier group not found.")
        self._validate_group_write(payload)
        enabled_options = sum(option.is_active for option in group.options)
        if payload.active and group.product_assignments and enabled_options < payload.min_selections:
            raise ValueError(
                f"{group.name} needs at least {payload.min_selections} enabled options for its assigned products."
            )
        if (
            payload.active
            and group.product_assignments
            and payload.max_selections
            and not payload.allow_quantity
            and payload.max_selections > enabled_options
        ):
            raise ValueError("Maximum selections cannot exceed the number of enabled options while this group is assigned.")
        self._apply_group(group, payload)
        self._repository.commit()
        return self._owner_group_response(group)

    def create_modifier_option(
        self, group_id: int, payload: OwnerModifierOptionWrite
    ) -> OwnerModifierOptionResponse:
        group = self._repository.get_modifier_group(group_id)
        if group is None:
            raise LookupError("Modifier group not found.")
        option = ModifierOption(
            modifier_group=group,
            key=self._unique_option_key(group_id, payload.name),
        )
        self._apply_option(option, payload)
        self._repository.add(option)
        self._repository.commit()
        return self._owner_option_response(option)

    def update_modifier_option(
        self, group_id: int, option_id: int, payload: OwnerModifierOptionWrite
    ) -> OwnerModifierOptionResponse:
        option = self._repository.get_modifier_option(group_id, option_id)
        if option is None:
            raise LookupError("Modifier option not found.")
        group = self._repository.get_modifier_group(group_id)
        enabled_after = sum(
            item.is_active for item in group.options if item.id != option.id
        ) + int(payload.active)
        if group.is_active and group.product_assignments and enabled_after < group.minimum_selections:
            raise ValueError(
                f"{group.name} needs at least {group.minimum_selections} enabled options for its assigned products."
            )
        if (
            group.is_active
            and group.product_assignments
            and group.maximum_selections
            and not group.allow_quantity
            and group.maximum_selections > enabled_after
        ):
            raise ValueError("This option cannot be disabled because the group's maximum exceeds its remaining enabled options.")
        self._apply_option(option, payload)
        self._repository.commit()
        return self._owner_option_response(option)

    def create_product(self, payload: OwnerProductWrite) -> OwnerProductResponse:
        self._validate_write(payload)
        if self._repository.get_product_by_slug(payload.slug):
            raise ValueError("A product with this slug already exists.")
        if payload.lunch_special:
            self._repository.clear_lunch_special()
        product = Product()
        self._apply_product(product, payload)
        self._repository.add(product)
        self._repository.flush()
        self._replace_children(product, payload)
        self._repository.commit()
        return self._owner_product_response(product)

    def update_product(self, product_id: int, payload: OwnerProductWrite) -> OwnerProductResponse:
        product = self._repository.get_product(product_id)
        if product is None:
            raise LookupError("Product not found.")
        conflicting = self._repository.get_product_by_slug(payload.slug)
        if conflicting is not None and conflicting.id != product_id:
            raise ValueError("A product with this slug already exists.")
        self._validate_write(payload)
        if payload.lunch_special:
            self._repository.clear_lunch_special(except_product_id=product_id)
        self._apply_product(product, payload)
        self._replace_children(product, payload)
        self._repository.commit()
        return self._owner_product_response(product)

    def archive_product(self, product_id: int) -> None:
        product = self._repository.get_product(product_id)
        if product is None:
            raise LookupError("Product not found.")
        product.archived_at = datetime.now(timezone.utc)
        product.is_published = False
        self._repository.commit()

    def set_product_availability(self, product_id: int, available: bool) -> OwnerProductResponse:
        product = self._repository.get_product(product_id)
        if product is None or product.archived_at is not None:
            raise LookupError("Product not found.")
        if product.availability is None:
            product.availability = ProductAvailability(default_available=available)
        else:
            product.availability.default_available = available
        self._repository.commit()
        return self._owner_product_response(product)

    def set_lunch_special(self, product_id: int | None) -> OwnerProductResponse | None:
        self._repository.lock_lunch_special_selection()
        if product_id is None:
            self._repository.clear_lunch_special()
            self._repository.commit()
            return None
        product = self._repository.get_product_for_update(product_id)
        if product is None or product.archived_at is not None:
            raise LookupError("Product not found.")
        category = self._repository.get_category(product.category_id)
        if not product.is_published or category is None or not category.is_published:
            raise ValueError(
                "Only products visible on the customer menu can be selected as Lunch Special."
            )
        self._repository.clear_lunch_special(except_product_id=product.id)
        product.is_lunch_special = True
        self._repository.commit()
        return self._owner_product_response(product)

    def _validate_write(self, payload: OwnerProductWrite) -> None:
        if self._repository.get_category(payload.category_id) is None:
            raise ValueError("Category does not exist.")
        groups = {group.id: group for group in self._repository.list_modifier_groups()}
        if len(set(payload.modifier_group_ids)) != len(payload.modifier_group_ids):
            raise ValueError("Modifier groups must be unique.")
        if not set(payload.modifier_group_ids) <= set(groups):
            raise ValueError("Modifier group does not exist.")
        for group_id in payload.modifier_group_ids:
            group = groups[group_id]
            if not group.is_active:
                raise ValueError(f"{group.name} is disabled and cannot be assigned.")
            active_options = sum(option.is_active for option in group.options)
            required_count = group.minimum_selections
            if active_options < required_count:
                raise ValueError(
                    f"{group.name} needs at least {required_count} enabled options before assignment."
                )
            if group.maximum_selections and not group.allow_quantity and group.maximum_selections > active_options:
                raise ValueError(
                    f"{group.name} needs at least {group.maximum_selections} enabled options before assignment."
                )

    @staticmethod
    def _validate_group_write(payload: OwnerModifierGroupWrite) -> None:
        if not payload.name.strip():
            raise ValueError("Group name is required.")
        if payload.required and payload.min_selections < 1:
            raise ValueError("Required groups must have a minimum of at least one.")
        if not payload.required and payload.min_selections != 0:
            raise ValueError("Optional groups must have a minimum of zero.")
        if payload.selection_type == "single" and not payload.allow_quantity and payload.max_selections != 1:
            raise ValueError("Choose-one groups without quantities must have a maximum of one.")
        if payload.max_selections and payload.max_selections < payload.min_selections:
            raise ValueError("Maximum selections cannot be less than minimum selections.")

    @staticmethod
    def _apply_group(group: ModifierGroup, payload: OwnerModifierGroupWrite) -> None:
        group.name = payload.name
        group.description = payload.description
        group.selection_type = payload.selection_type
        group.is_required = payload.required
        group.minimum_selections = payload.min_selections
        group.maximum_selections = payload.max_selections
        group.allow_quantity = payload.allow_quantity
        group.is_active = payload.active
        group.sort_order = payload.sort_order

    @staticmethod
    def _apply_option(option: ModifierOption, payload: OwnerModifierOptionWrite) -> None:
        if not payload.name.strip():
            raise ValueError("Option name is required.")
        option.name = payload.name
        option.price_adjustment_cents = payload.price_adjustment_cents
        option.is_active = payload.active
        option.sort_order = payload.sort_order

    @staticmethod
    def _key_base(name: str, fallback: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:80] or fallback

    def _unique_group_key(self, name: str) -> str:
        base = self._key_base(name, "modifier")
        key = base
        suffix = 2
        while self._repository.modifier_group_key_exists(key):
            key = f"{base[:74]}-{suffix}"
            suffix += 1
        return key

    def _unique_option_key(self, group_id: int, name: str) -> str:
        base = self._key_base(name, "option")
        key = base
        suffix = 2
        while self._repository.modifier_option_key_exists(group_id, key):
            key = f"{base[:74]}-{suffix}"
            suffix += 1
        return key

    def _owner_group_response(self, group: ModifierGroup) -> OwnerModifierGroupResponse:
        return OwnerModifierGroupResponse(
            id=str(group.id), key=group.key, name=group.name,
            description=group.description or "", selection_type=group.selection_type,
            required=group.is_required, min_selections=group.minimum_selections,
            max_selections=group.maximum_selections, active=group.is_active,
            allow_quantity=group.allow_quantity,
            sort_order=group.sort_order,
            assignment_count=len(group.product_assignments),
            options=[self._owner_option_response(option) for option in sorted(
                group.options, key=lambda value: (value.sort_order, value.name, value.id or 0)
            )],
        )

    @staticmethod
    def _owner_option_response(option: ModifierOption) -> OwnerModifierOptionResponse:
        return OwnerModifierOptionResponse(
            id=str(option.id), key=option.key, name=option.name,
            price_adjustment_cents=option.price_adjustment_cents,
            active=option.is_active, sort_order=option.sort_order,
        )

    @staticmethod
    def _apply_product(product: Product, payload: OwnerProductWrite) -> None:
        product.slug = payload.slug.strip()
        product.name = payload.name
        product.description = payload.description
        product.base_price_cents = payload.base_price_cents
        product.category_id = payload.category_id
        product.image_reference = payload.image
        product.is_featured = payload.featured
        product.is_lunch_special = payload.lunch_special
        product.is_published = payload.published
        product.sort_order = payload.sort_order

    def _replace_children(self, product: Product, payload: OwnerProductWrite) -> None:
        existing_variants = {item.key: item for item in product.variants}
        next_variants: list[ProductVariant] = []
        for item in payload.variants:
            variant = existing_variants.get(item.key) or ProductVariant(key=item.key)
            variant.name = item.name
            variant.price_cents = item.price_cents
            variant.is_active = item.active
            variant.sort_order = item.sort_order
            next_variants.append(variant)
        product.variants[:] = next_variants
        self._repository.replace_modifier_assignments(product.id, payload.modifier_group_ids)
        if product.availability is None:
            product.availability = ProductAvailability(default_available=payload.available)
        else:
            product.availability.default_available = payload.available
        self._repository.flush()

    @staticmethod
    def _owner_product_response(product: Product) -> OwnerProductResponse:
        assignments = sorted(
            (item for item in product.modifier_group_assignments if item.is_active),
            key=lambda item: (item.sort_order, item.modifier_group_id),
        )
        return OwnerProductResponse(
            id=str(product.id), slug=product.slug, name=product.name,
            description=product.description or "", base_price_cents=product.base_price_cents,
            category_id=str(product.category_id), image=product.image_reference or "",
            available=product.availability.default_available if product.availability else True,
            featured=product.is_featured, lunch_special=product.is_lunch_special,
            published=product.is_published,
            archived=product.archived_at is not None, sort_order=product.sort_order,
            variants=[OwnerVariantResponse(
                id=str(item.id), key=item.key, name=item.name,
                price_cents=item.price_cents, sort_order=item.sort_order,
                active=item.is_active,
            ) for item in sorted(product.variants, key=lambda item: (item.sort_order, item.id or 0))],
            modifier_group_ids=[str(item.modifier_group_id) for item in assignments],
        )

    def _options_by_group(
        self,
        modifier_group_ids: list[int],
    ) -> dict[int, list[ModifierOptionResponse]]:
        result: dict[int, list[ModifierOptionResponse]] = defaultdict(list)
        for option in self._repository.list_active_modifier_options(
            modifier_group_ids
        ):
            result[option.modifier_group_id].append(
                self._option_response(option)
            )
        return result

    @staticmethod
    def _groups_by_product(
        assignments: list[tuple[ProductModifierGroup, ModifierGroup]],
        options_by_group: dict[int, list[ModifierOptionResponse]],
    ) -> dict[int, list[ProductModifierGroupResponse]]:
        result: dict[int, list[ProductModifierGroupResponse]] = defaultdict(list)
        for assignment, group in assignments:
            result[assignment.product_id].append(
                ProductModifierGroupResponse(
                    id=str(group.id),
                    key=group.key,
                    name=group.name,
                    description=group.description or "",
                    selection_type=group.selection_type,
                    required=group.is_required,
                    min_selections=group.minimum_selections,
                    max_selections=group.maximum_selections,
                    allow_quantity=group.allow_quantity,
                    sort_order=assignment.sort_order,
                    options=options_by_group[group.id],
                )
            )
        return result

    @staticmethod
    def _product_response(
        product: Product,
        variants: list[ProductVariantResponse],
        modifier_groups: list[ProductModifierGroupResponse],
    ) -> ProductResponse:
        return ProductResponse(
            id=str(product.id),
            slug=product.slug,
            name=product.name,
            description=product.description or "",
            image=product.image_reference or "",
            featured=product.is_featured,
            lunch_special=product.is_lunch_special,
            base_price_cents=product.base_price_cents,
            sort_order=product.sort_order,
            variants=variants,
            modifier_groups=modifier_groups,
        )

    @staticmethod
    def _option_response(option: ModifierOption) -> ModifierOptionResponse:
        return ModifierOptionResponse(
            id=str(option.id),
            key=option.key,
            name=option.name,
            price_adjustment_cents=option.price_adjustment_cents,
            sort_order=option.sort_order,
        )
