from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.availability.models import ProductAvailability
from app.catalog.models import Category, ModifierGroup, Product, ProductModifierGroup, ProductVariant, SelectionType
from app.customers.models import CustomerProfile
from app.jds_auth.models import JdsUser
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.models import Order, OrderItem


class CustomerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def user(self, user_id: UUID) -> JdsUser | None:
        return self.session.get(JdsUser, user_id)

    def lock_user(self, user_id: UUID) -> JdsUser | None:
        return self.session.scalar(
            select(JdsUser)
            .where(JdsUser.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def profile(self, user_id: UUID) -> CustomerProfile | None:
        return self.session.get(CustomerProfile, user_id)

    def add(self, value: object) -> None:
        self.session.add(value)

    def latest_order_phone(self, user_id: UUID) -> str:
        return self.session.scalar(
            select(Order.guest_phone)
            .where(Order.customer_user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(1)
        ) or ""

    def orders(self, user_id: UUID) -> list[Order]:
        return list(self.session.scalars(
            select(Order).options(selectinload(Order.items)).where(
                Order.customer_user_id == user_id
            ).order_by(Order.created_at.desc(), Order.id.desc())
        ).all())

    def order(self, user_id: UUID, order_id: int) -> Order | None:
        return self.session.scalar(
            select(Order).options(
                selectinload(Order.items).selectinload(OrderItem.modifiers)
            ).where(Order.customer_user_id == user_id, Order.id == order_id)
        )

    def quick_order_product_ids(self, user_id: UUID, *, limit: int = 6) -> list[int]:
        """Rank currently public products from this customer's paid purchases."""
        purchased_quantity = func.sum(OrderItem.quantity)
        latest_purchase_at = func.max(Order.created_at)
        return list(self.session.scalars(
            select(OrderItem.source_product_id)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.source_product_id)
            .join(Category, Category.id == Product.category_id)
            .outerjoin(
                ProductAvailability,
                ProductAvailability.product_id == Product.id,
            )
            .where(
                Order.customer_user_id == user_id,
                Order.status == OrderStatus.PAID,
                Order.fulfillment_status != FulfillmentStatus.CANCELLED,
                Category.is_published.is_(True),
                Product.is_published.is_(True),
                Product.archived_at.is_(None),
                func.coalesce(ProductAvailability.default_available, True).is_(True),
            )
            .group_by(OrderItem.source_product_id)
            .order_by(
                purchased_quantity.desc(),
                latest_purchase_at.desc(),
                OrderItem.source_product_id.asc(),
            )
            .limit(limit)
        ).all())

    def quick_order_configurations(self, user_id: UUID, *, limit: int = 6) -> list[dict]:
        """Rank paid exact configurations and retain only current-catalog-valid ones."""
        items = self.session.scalars(
            select(OrderItem).join(Order).options(selectinload(OrderItem.modifiers)).where(
                Order.customer_user_id == user_id,
                Order.status == OrderStatus.PAID,
                Order.fulfillment_status != FulfillmentStatus.CANCELLED,
            )
        ).all()
        aggregates: dict[tuple, dict] = {}
        for item in items:
            if item.source_product_id is None:
                continue
            modifier_key = tuple(sorted(
                (modifier.source_modifier_option_id, modifier.quantity or 1)
                for modifier in item.modifiers
                if modifier.source_modifier_option_id is not None
            ))
            key = (item.source_product_id, item.source_variant_id, modifier_key)
            aggregate = aggregates.setdefault(key, {"count": 0, "latest": item.order.created_at})
            aggregate["count"] += item.quantity
            aggregate["latest"] = max(aggregate["latest"], item.order.created_at)

        ranked = sorted(aggregates, key=lambda key: (-aggregates[key]["count"], -aggregates[key]["latest"].timestamp(), key[0], key[1] or 0, key[2]))
        result = []
        for product_id, variant_id, modifier_key in ranked:
            product = self.session.scalar(select(Product).options(
                selectinload(Product.category), selectinload(Product.availability),
                selectinload(Product.variants),
                selectinload(Product.modifier_group_assignments).selectinload(ProductModifierGroup.modifier_group).selectinload(ModifierGroup.options),
            ).where(Product.id == product_id))
            if product is None or not product.is_published or product.archived_at is not None or not product.category.is_published or (product.availability and not product.availability.default_available):
                continue
            active_variants = {variant.id: variant for variant in product.variants if variant.is_active}
            if bool(active_variants) != bool(variant_id) or (variant_id and variant_id not in active_variants):
                continue
            groups = [assignment.modifier_group for assignment in product.modifier_group_assignments if assignment.is_active and assignment.modifier_group.is_active]
            options = {option.id: (group, option) for group in groups for option in group.options if option.is_active}
            if any(option_id not in options for option_id, _ in modifier_key):
                continue
            valid = True
            for group in groups:
                selected = [(options[option_id][1], quantity) for option_id, quantity in modifier_key if option_id in options and options[option_id][0].id == group.id]
                total = sum(quantity for _, quantity in selected)
                if (group.selection_type == SelectionType.SINGLE and len(selected) > 1) or (not group.allow_quantity and any(quantity != 1 for _, quantity in selected)) or total < group.minimum_selections or (group.maximum_selections > 0 and total > group.maximum_selections):
                    valid = False
                    break
            if not valid:
                continue
            base = active_variants[variant_id].price_cents if variant_id else product.base_price_cents
            result.append({
                "product_id": str(product_id), "variant_id": str(variant_id) if variant_id else None,
                "modifiers": [{"option_id": str(option_id), "option_name": options[option_id][1].name, "quantity": quantity} for option_id, quantity in modifier_key],
                "unit_price_cents": base + sum(options[option_id][1].price_adjustment_cents * quantity for option_id, quantity in modifier_key),
            })
            if len(result) == limit:
                break
        return result
