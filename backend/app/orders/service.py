import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.availability.repository import AvailabilityRepository
from app.availability.service import (
    PickupSchedulingService,
    SellabilityService,
)
from app.catalog.models import ModifierGroup, ModifierOption, Product, ProductVariant, SelectionType
from app.orders.constants import (
    DEFAULT_CURRENCY,
    DEFAULT_PENDING_EXPIRY_MINUTES,
    OrderStatus,
)
from app.orders.models import Order, OrderItem, OrderItemModifier
from app.orders.pricing import calculate_tax_cents
from app.orders.repository import OrderRepository
from app.orders.schemas import (
    ConfiguredOrderLineInput,
    CreatePendingOrderInput,
)
from app.tenancy.resolver import resolve_internal_ladels_compatibility_context


class OrderCreationErrorCode(str, Enum):
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    PICKUP_INVALID = "pickup_invalid"
    PRODUCT_NOT_SELLABLE = "product_not_sellable"
    VARIANT_REQUIRED = "variant_required"
    VARIANT_INVALID = "variant_invalid"
    MODIFIER_OPTION_INVALID = "modifier_option_invalid"
    MODIFIER_SELECTION_INVALID = "modifier_selection_invalid"


class OrderCreationError(ValueError):
    def __init__(self, code: OrderCreationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedLine:
    item: OrderItem
    subtotal_cents: int


class OrderCreationService:
    """Validates and persists one complete pending-order aggregate."""

    _IDEMPOTENCY_CONSTRAINT = "uq_orders_idempotency_key"

    def __init__(
        self,
        session: Session,
        *,
        pending_expiry_minutes: int = DEFAULT_PENDING_EXPIRY_MINUTES,
    ) -> None:
        if pending_expiry_minutes < 1:
            raise ValueError("pending_expiry_minutes must be positive.")
        self._session = session
        self._orders = OrderRepository(session)
        self._pending_expiry_minutes = pending_expiry_minutes

    def create_pending_order(
        self,
        request: CreatePendingOrderInput,
        *,
        now: datetime,
        customer_user_id: UUID | None = None,
    ) -> Order:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include timezone information.")

        fingerprint = self._fingerprint(request)
        with self._session.begin():
            self._availability = AvailabilityRepository(
                self._session,
                resolve_internal_ladels_compatibility_context(self._session),
            )
            self._pickup = PickupSchedulingService(self._availability)
            self._sellability = SellabilityService(self._availability)
            existing = self._orders.get_by_idempotency_key(
                request.idempotency_key
            )
            if existing is not None:
                return self._resolve_idempotent_order(existing, fingerprint)

            pickup = self._pickup.validate(
                request.requested_pickup_at,
                now=now,
            )
            if not pickup.is_valid:
                raise OrderCreationError(
                    OrderCreationErrorCode.PICKUP_INVALID,
                    pickup.message or "Pickup time is invalid.",
                )

            settings = self._availability.get_business_settings()
            assert settings is not None
            validated_lines = [
                self._validate_line(
                    line,
                    pickup_at=pickup.requested_at,
                    sort_order=index,
                )
                for index, line in enumerate(request.lines)
            ]
            subtotal_cents = sum(
                line.subtotal_cents for line in validated_lines
            )
            tax_cents = calculate_tax_cents(
                subtotal_cents, settings.tax_rate_millionths
            )
            order = Order(
                customer_user_id=customer_user_id,
                idempotency_key=request.idempotency_key,
                request_fingerprint=fingerprint,
                public_access_token=secrets.token_urlsafe(32),
                status=OrderStatus.PENDING,
                guest_name=request.customer.name,
                guest_email=request.customer.email,
                guest_phone=request.customer.phone,
                notes=request.notes,
                requested_pickup_at=pickup.requested_at,
                business_timezone=settings.timezone,
                currency=DEFAULT_CURRENCY,
                subtotal_cents=subtotal_cents,
                tax_cents=tax_cents,
                tax_name=settings.tax_name,
                tax_rate_millionths=settings.tax_rate_millionths,
                total_cents=subtotal_cents + tax_cents,
                version=1,
                expires_at=now + timedelta(
                    minutes=self._pending_expiry_minutes
                ),
                created_at=now,
                updated_at=now,
                items=[line.item for line in validated_lines],
            )
            try:
                with self._session.begin_nested():
                    self._orders.add(order)
                    self._session.flush()
            except IntegrityError as error:
                if not self._is_idempotency_key_violation(error):
                    raise
                existing = self._orders.get_by_idempotency_key(
                    request.idempotency_key
                )
                if existing is None:
                    raise RuntimeError(
                        "Idempotency conflict occurred without an existing order."
                    ) from error
                return self._resolve_idempotent_order(existing, fingerprint)

        return order

    @staticmethod
    def _resolve_idempotent_order(
        existing: Order,
        fingerprint: str,
    ) -> Order:
        if existing.request_fingerprint != fingerprint:
            raise OrderCreationError(
                OrderCreationErrorCode.IDEMPOTENCY_CONFLICT,
                "Idempotency key was already used for a different order.",
            )
        return existing

    @classmethod
    def _is_idempotency_key_violation(cls, error: IntegrityError) -> bool:
        diagnostic = getattr(error.orig, "diag", None)
        return (
            getattr(diagnostic, "constraint_name", None)
            == cls._IDEMPOTENCY_CONSTRAINT
        )

    def _validate_line(
        self,
        request: ConfiguredOrderLineInput,
        *,
        pickup_at: datetime,
        sort_order: int,
    ) -> ValidatedLine:
        product = self._orders.get_product_for_order(request.product_id)
        sellability = self._sellability.evaluate(
            request.product_id,
            at=pickup_at,
        )
        if product is None or not sellability.is_sellable:
            raise OrderCreationError(
                OrderCreationErrorCode.PRODUCT_NOT_SELLABLE,
                sellability.reason or "Product is not sellable.",
            )

        variant = self._validate_variant(product, request.variant_id)
        selected_modifiers = self._validate_modifiers(
            product,
            request.normalized_modifier_selections(),
        )
        base_unit_price_cents = (
            variant.price_cents if variant is not None else product.base_price_cents
        )
        unit_price_cents = base_unit_price_cents + sum(
            option.price_adjustment_cents * quantity
            for _, option, quantity in selected_modifiers
        )
        line_subtotal_cents = unit_price_cents * request.quantity
        item = OrderItem(
            source_product_id=product.id,
            source_variant_id=variant.id if variant is not None else None,
            product_slug=product.slug,
            product_name=product.name,
            variant_key=variant.key if variant is not None else None,
            variant_name=variant.name if variant is not None else None,
            base_unit_price_cents=base_unit_price_cents,
            unit_price_cents=unit_price_cents,
            quantity=request.quantity,
            line_subtotal_cents=line_subtotal_cents,
            sort_order=sort_order,
            modifiers=[
                OrderItemModifier(
                    source_modifier_group_id=group.id,
                    source_modifier_option_id=option.id,
                    modifier_group_key=group.key,
                    modifier_group_name=group.name,
                    modifier_option_key=option.key,
                    modifier_option_name=option.name,
                    price_adjustment_cents=option.price_adjustment_cents,
                    quantity=quantity,
                    sort_order=index,
                )
                for index, (group, option, quantity) in enumerate(selected_modifiers)
            ],
        )
        return ValidatedLine(item=item, subtotal_cents=line_subtotal_cents)

    @staticmethod
    def _validate_variant(
        product: Product,
        variant_id: int | None,
    ) -> ProductVariant | None:
        active_variants = [
            variant for variant in product.variants if variant.is_active
        ]
        if active_variants and variant_id is None:
            raise OrderCreationError(
                OrderCreationErrorCode.VARIANT_REQUIRED,
                f"{product.name} requires a variant.",
            )
        if variant_id is None:
            return None

        variant = next(
            (
                candidate
                for candidate in active_variants
                if candidate.id == variant_id
            ),
            None,
        )
        if variant is None:
            raise OrderCreationError(
                OrderCreationErrorCode.VARIANT_INVALID,
                "Variant is inactive or does not belong to the product.",
            )
        return variant

    @staticmethod
    def _validate_modifiers(
        product: Product,
        selections,
    ) -> list[tuple[ModifierGroup, ModifierOption, int]]:
        active_groups = [
            assignment.modifier_group
            for assignment in sorted(
                product.modifier_group_assignments,
                key=lambda assignment: (
                    assignment.sort_order,
                    assignment.modifier_group_id,
                ),
            )
            if assignment.is_active and assignment.modifier_group.is_active
        ]
        options_by_id = {
            option.id: (group, option)
            for group in active_groups
            for option in group.options
            if option.is_active
        }
        selected_option_ids = [selection.modifier_option_id for selection in selections]
        if len(selected_option_ids) != len(set(selected_option_ids)):
            raise OrderCreationError(OrderCreationErrorCode.MODIFIER_SELECTION_INVALID, "Modifier options must be unique.")
        quantities = {selection.modifier_option_id: selection.quantity for selection in selections}
        unknown_options = set(selected_option_ids) - options_by_id.keys()
        if unknown_options:
            raise OrderCreationError(
                OrderCreationErrorCode.MODIFIER_OPTION_INVALID,
                "A modifier option is inactive or not assigned to the product.",
            )

        selected_ids = set(selected_option_ids)
        selected: list[tuple[ModifierGroup, ModifierOption, int]] = []
        for group in active_groups:
            group_options = sorted(
                (
                    option
                    for option in group.options
                    if option.is_active and option.id in selected_ids
                ),
                key=lambda option: (option.sort_order, option.id),
            )
            if group.selection_type == SelectionType.SINGLE and len(group_options) > 1:
                raise OrderCreationError(
                    OrderCreationErrorCode.MODIFIER_SELECTION_INVALID,
                    f"{group.name} allows only one distinct option.",
                )
            if not group.allow_quantity and any(quantities[option.id] != 1 for option in group_options):
                raise OrderCreationError(OrderCreationErrorCode.MODIFIER_SELECTION_INVALID, f"{group.name} does not allow quantities.")
            selection_count = sum(quantities[option.id] for option in group_options)
            minimum = group.minimum_selections
            maximum = group.maximum_selections
            if selection_count < minimum:
                raise OrderCreationError(
                    OrderCreationErrorCode.MODIFIER_SELECTION_INVALID,
                    f"{group.name} requires at least {minimum} selection(s).",
                )
            if maximum > 0 and selection_count > maximum:
                raise OrderCreationError(
                    OrderCreationErrorCode.MODIFIER_SELECTION_INVALID,
                    f"{group.name} allows at most {maximum} selection(s).",
                )
            selected.extend((group, option, quantities[option.id]) for option in group_options)

        return selected

    @staticmethod
    def _fingerprint(request: CreatePendingOrderInput) -> str:
        payload = request.model_dump(mode="json")
        payload.pop("idempotency_key", None)
        for line in payload["lines"]:
            selections = line.get("modifier_selections")
            if selections is None:
                selections = [{"modifier_option_id": value, "quantity": 1} for value in line.pop("modifier_option_ids", [])]
            else:
                line.pop("modifier_option_ids", None)
            line["modifier_selections"] = sorted(selections, key=lambda value: value["modifier_option_id"])
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()
