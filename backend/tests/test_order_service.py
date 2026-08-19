from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from threading import Barrier, Lock
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.availability.models import (
    BusinessHour,
    BusinessSettings,
    ProductAvailability,
    ProductAvailabilityOverride,
)
from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
    SelectionType,
)
from app.customers.schemas import GuestCustomerInput
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem, OrderItemModifier
from app.orders.repository import OrderRepository
from app.orders.schemas import (
    ConfiguredOrderLineInput,
    CreatePendingOrderInput,
    ModifierSelectionInput,
)
from app.orders.service import (
    OrderCreationError,
    OrderCreationErrorCode,
    OrderCreationService as TenantOrderCreationService,
)
from app.jds_auth.models import Organization
from app.tenancy.resolver import (
    LADELS_ORGANIZATION_ID,
    LADELS_ORGANIZATION_NAME,
    LADELS_ORGANIZATION_SLUG,
)
from app.tenancy.context import TenantContext, TenantResolutionSource
from tests.test_migrations import make_alembic_config


LADELS_TENANT = TenantContext(
    organization_id=LADELS_ORGANIZATION_ID,
    organization_slug=LADELS_ORGANIZATION_SLUG,
    source=TenantResolutionSource.LADELS_COMPATIBILITY,
)


def OrderCreationService(session: Session, **kwargs) -> TenantOrderCreationService:
    return TenantOrderCreationService(session, LADELS_TENANT, **kwargs)


@pytest.fixture
def prepared_order_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

    def reset_tables() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE order_item_modifiers, order_items, orders, "
                    "product_availability_overrides, product_availability, "
                    "business_closures, business_hours, business_settings, "
                    "product_modifier_groups, modifier_options, "
                    "product_variants, products, modifier_groups, categories "
                    "RESTART IDENTITY CASCADE"
                )
            )

    reset_tables()
    try:
        yield engine
    finally:
        reset_tables()
        engine.dispose()


def local_datetime(hour: int, minute: int = 0) -> datetime:
    return datetime(
        2026,
        7,
        28,
        hour,
        minute,
        tzinfo=ZoneInfo("America/New_York"),
    )


def seed_order_dependencies(session: Session) -> dict[str, int]:
    organization = session.scalar(
        select(Organization).where(Organization.slug == LADELS_ORGANIZATION_SLUG)
    )
    if organization is None:
        organization = Organization(
            id=LADELS_ORGANIZATION_ID,
            slug=LADELS_ORGANIZATION_SLUG,
            name=LADELS_ORGANIZATION_NAME,
        )
        session.add(organization)
        session.flush()
    organization_id = organization.id
    settings = BusinessSettings(
        organization_id=organization_id,
        timezone="America/New_York",
        ordering_enabled=True,
        minimum_lead_time_minutes=15,
        pickup_interval_minutes=5,
        maximum_advance_days=14,
    )
    settings.hours.append(
        BusinessHour(
            weekday=1,
            is_closed=False,
            opens_at=time(7),
            closes_at=time(15),
        )
    )
    category = Category(
        organization_id=organization_id,
        slug="espresso",
        name="Espresso",
        description=None,
        is_published=True,
        sort_order=0,
    )
    latte = Product(
        organization_id=organization_id,
        category=category,
        slug="latte",
        name="Latte",
        description="Espresso with steamed milk.",
        base_price_cents=525,
        image_reference="latte",
        is_published=True,
        is_featured=True,
        sort_order=0,
    )
    small = ProductVariant(
        product=latte,
        key="small",
        name="Small",
        price_cents=525,
        is_active=True,
        sort_order=0,
    )
    large = ProductVariant(
        product=latte,
        key="large",
        name="Large",
        price_cents=650,
        is_active=True,
        sort_order=1,
    )
    milk = ModifierGroup(
        organization_id=organization_id,
        key="milk",
        name="Milk",
        description=None,
        selection_type=SelectionType.SINGLE,
        is_required=True,
        minimum_selections=1,
        maximum_selections=1,
        is_active=True,
        sort_order=0,
    )
    whole = ModifierOption(
        modifier_group=milk,
        key="whole",
        name="Whole milk",
        price_adjustment_cents=0,
        is_active=True,
        sort_order=0,
    )
    oat = ModifierOption(
        modifier_group=milk,
        key="oat",
        name="Oat",
        price_adjustment_cents=85,
        is_active=True,
        sort_order=1,
    )
    flavours = ModifierGroup(
        organization_id=organization_id,
        key="flavours",
        name="Flavour shots",
        description=None,
        selection_type=SelectionType.MULTIPLE,
        is_required=False,
        minimum_selections=0,
        maximum_selections=3,
        allow_quantity=True,
        is_active=True,
        sort_order=1,
    )
    vanilla = ModifierOption(
        modifier_group=flavours,
        key="vanilla",
        name="Vanilla",
        price_adjustment_cents=75,
        is_active=True,
        sort_order=0,
    )
    caramel = ModifierOption(
        modifier_group=flavours,
        key="caramel",
        name="Caramel",
        price_adjustment_cents=75,
        is_active=True,
        sort_order=1,
    )
    sugar = ModifierGroup(
        organization_id=organization_id,
        key="sugar",
        name="Sugar",
        description=None,
        selection_type=SelectionType.SINGLE,
        is_required=False,
        minimum_selections=0,
        maximum_selections=3,
        allow_quantity=True,
        is_active=True,
        sort_order=2,
    )
    sugar_option = ModifierOption(
        modifier_group=sugar,
        key="sugar",
        name="Sugar",
        price_adjustment_cents=0,
        is_active=True,
        sort_order=0,
    )
    sweetener = ModifierOption(
        modifier_group=sugar,
        key="sweetener",
        name="Sweetener",
        price_adjustment_cents=0,
        is_active=True,
        sort_order=1,
    )
    latte.modifier_group_assignments.extend(
        [
            ProductModifierGroup(
                modifier_group=milk,
                is_active=True,
                sort_order=0,
            ),
            ProductModifierGroup(
                modifier_group=flavours,
                is_active=True,
                sort_order=1,
            ),
            ProductModifierGroup(
                modifier_group=sugar,
                is_active=True,
                sort_order=2,
            ),
        ]
    )
    latte.availability = ProductAvailability(default_available=True)
    session.add_all([settings, category, milk, flavours, sugar])
    session.commit()

    return {
        "category": category.id,
        "product": latte.id,
        "small": small.id,
        "large": large.id,
        "milk": milk.id,
        "whole": whole.id,
        "oat": oat.id,
        "flavours": flavours.id,
        "vanilla": vanilla.id,
        "caramel": caramel.id,
        "sugar": sugar.id,
        "sugar_option": sugar_option.id,
        "sweetener": sweetener.id,
    }


def make_request(ids: dict[str, int], **overrides: object) -> CreatePendingOrderInput:
    values = {
        "idempotency_key": "order-request-123",
        "customer": GuestCustomerInput(
            name="Jessie Guest",
            email="jessie@example.com",
            phone="+15551234567",
        ),
        "requested_pickup_at": local_datetime(8, 30),
        "notes": "Extra hot",
        "lines": [
            ConfiguredOrderLineInput(
                product_id=ids["product"],
                variant_id=ids["large"],
                modifier_option_ids=[ids["oat"], ids["vanilla"]],
                quantity=2,
            )
        ],
    }
    values.update(overrides)
    return CreatePendingOrderInput(**values)


@pytest.mark.postgresql
def test_creates_authoritatively_priced_pending_order_with_snapshots(
    prepared_order_engine: Engine,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        order = OrderCreationService(session).create_pending_order(
            make_request(ids),
            now=local_datetime(8),
        )

        assert order.id is not None
        assert order.status == OrderStatus.PENDING
        assert order.guest_name == "Jessie Guest"
        assert order.requested_pickup_at == local_datetime(8, 30)
        assert order.business_timezone == "America/New_York"
        assert order.subtotal_cents == 1620
        assert order.tax_cents == 211
        assert order.total_cents == 1831
        assert len(order.public_access_token) >= 32
        assert len(order.items) == 1

        item = order.items[0]
        assert item.product_name == "Latte"
        assert item.variant_name == "Large"
        assert item.base_unit_price_cents == 650
        assert item.unit_price_cents == 810
        assert item.quantity == 2
        assert item.line_subtotal_cents == 1620
        assert [
            (modifier.modifier_group_key, modifier.modifier_option_key)
            for modifier in item.modifiers
        ] == [("milk", "oat"), ("flavours", "vanilla")]

        assert session.scalar(select(Order).where(Order.id == order.id)) is order
        assert session.scalar(select(OrderItem).where(OrderItem.order_id == order.id))
        assert session.scalar(
            select(OrderItemModifier).where(
                OrderItemModifier.order_item_id == item.id
            )
        )


@pytest.mark.postgresql
def test_quantity_is_independent_from_distinct_option_cardinality(
    prepared_order_engine: Engine,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        base_line = dict(product_id=ids["product"], variant_id=ids["large"], quantity=1)

        order = OrderCreationService(session).create_pending_order(
            make_request(ids, idempotency_key="single-quantity", lines=[ConfiguredOrderLineInput(
                **base_line,
                modifier_selections=[
                    ModifierSelectionInput(modifier_option_id=ids["oat"], quantity=1),
                    ModifierSelectionInput(modifier_option_id=ids["sugar_option"], quantity=2),
                    ModifierSelectionInput(modifier_option_id=ids["vanilla"], quantity=2),
                    ModifierSelectionInput(modifier_option_id=ids["caramel"], quantity=1),
                ],
            )]),
            now=local_datetime(8),
        )
        assert order.items[0].unit_price_cents == 960
        assert [(item.modifier_option_key, item.quantity) for item in order.items[0].modifiers] == [
            ("oat", 1), ("vanilla", 2), ("caramel", 1), ("sugar", 2),
        ]

        with pytest.raises(OrderCreationError, match="one distinct option"):
            OrderCreationService(session).create_pending_order(
                make_request(ids, idempotency_key="two-sugars", lines=[ConfiguredOrderLineInput(
                    **base_line,
                    modifier_selections=[
                        ModifierSelectionInput(modifier_option_id=ids["oat"], quantity=1),
                        ModifierSelectionInput(modifier_option_id=ids["sugar_option"], quantity=1),
                        ModifierSelectionInput(modifier_option_id=ids["sweetener"], quantity=1),
                    ],
                )]),
                now=local_datetime(8),
            )

        with pytest.raises(OrderCreationError, match="does not allow quantities"):
            OrderCreationService(session).create_pending_order(
                make_request(ids, idempotency_key="milk-quantity", lines=[ConfiguredOrderLineInput(
                    **base_line,
                    modifier_selections=[ModifierSelectionInput(modifier_option_id=ids["oat"], quantity=2)],
                )]),
                now=local_datetime(8),
            )

        with pytest.raises(OrderCreationError, match="at most 3"):
            OrderCreationService(session).create_pending_order(
                make_request(ids, idempotency_key="too-much-sugar", lines=[ConfiguredOrderLineInput(
                    **base_line,
                    modifier_selections=[
                        ModifierSelectionInput(modifier_option_id=ids["oat"], quantity=1),
                        ModifierSelectionInput(modifier_option_id=ids["sugar_option"], quantity=4),
                    ],
                )]),
                now=local_datetime(8),
            )


@pytest.mark.postgresql
def test_idempotent_replay_returns_existing_order_and_rejects_conflict(
    prepared_order_engine: Engine,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        service = OrderCreationService(session)
        request = make_request(ids)

        first = service.create_pending_order(request, now=local_datetime(8))
        replay = service.create_pending_order(request, now=local_datetime(8))

        conflicting = make_request(
            ids,
            lines=[
                ConfiguredOrderLineInput(
                    product_id=ids["product"],
                    variant_id=ids["large"],
                    modifier_option_ids=[ids["oat"], ids["vanilla"]],
                    quantity=3,
                )
            ],
        )
        with pytest.raises(OrderCreationError) as error:
            service.create_pending_order(
                conflicting,
                now=local_datetime(8),
            )
        assert replay.id == first.id
        assert error.value.code == OrderCreationErrorCode.IDEMPOTENCY_CONFLICT
        assert session.scalar(select(text("count(*)")).select_from(Order)) == 1


@pytest.mark.postgresql
@pytest.mark.parametrize("identical_payloads", [True, False])
def test_concurrent_idempotency_key_race_returns_order_or_domain_conflict(
    prepared_order_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    identical_payloads: bool,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)

    barrier = Barrier(2)
    call_counts: dict[int, int] = {}
    call_counts_lock = Lock()
    original_lookup = OrderRepository.get_by_idempotency_key

    def synchronized_lookup(
        repository: OrderRepository,
        idempotency_key: str,
    ) -> Order | None:
        result = original_lookup(repository, idempotency_key)
        thread_key = id(repository)
        with call_counts_lock:
            call_count = call_counts.get(thread_key, 0)
            call_counts[thread_key] = call_count + 1
        if call_count == 0:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(
        OrderRepository,
        "get_by_idempotency_key",
        synchronized_lookup,
    )

    requests = [make_request(ids), make_request(ids)]
    if not identical_payloads:
        requests[1] = make_request(
            ids,
            lines=[
                ConfiguredOrderLineInput(
                    product_id=ids["product"],
                    variant_id=ids["large"],
                    modifier_option_ids=[ids["oat"], ids["vanilla"]],
                    quantity=3,
                )
            ],
        )

    def create_order(
        request: CreatePendingOrderInput,
    ) -> tuple[str, int | OrderCreationErrorCode]:
        with Session(prepared_order_engine, expire_on_commit=False) as session:
            try:
                order = OrderCreationService(session).create_pending_order(
                    request,
                    now=local_datetime(8),
                )
                return ("order", order.id)
            except OrderCreationError as error:
                return ("error", error.code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create_order, requests))

    if identical_payloads:
        assert results[0][0] == "order"
        assert results[1][0] == "order"
        assert results[0][1] == results[1][1]
    else:
        assert sorted(result[0] for result in results) == ["error", "order"]
        assert (
            next(result[1] for result in results if result[0] == "error")
            == OrderCreationErrorCode.IDEMPOTENCY_CONFLICT
        )

    with Session(prepared_order_engine) as session:
        assert session.scalar(select(text("count(*)")).select_from(Order)) == 1


@pytest.mark.postgresql
@pytest.mark.parametrize(
    ("request_change", "expected_code"),
    [
        (
            lambda ids: {"requested_pickup_at": local_datetime(6, 30)},
            OrderCreationErrorCode.PICKUP_INVALID,
        ),
        (
            lambda ids: {
                "lines": [
                    ConfiguredOrderLineInput(
                        product_id=ids["product"],
                        variant_id=None,
                        modifier_option_ids=[ids["oat"]],
                        quantity=1,
                    )
                ]
            },
            OrderCreationErrorCode.VARIANT_REQUIRED,
        ),
        (
            lambda ids: {
                "lines": [
                    ConfiguredOrderLineInput(
                        product_id=ids["product"],
                        variant_id=999999,
                        modifier_option_ids=[ids["oat"]],
                        quantity=1,
                    )
                ]
            },
            OrderCreationErrorCode.VARIANT_INVALID,
        ),
        (
            lambda ids: {
                "lines": [
                    ConfiguredOrderLineInput(
                        product_id=ids["product"],
                        variant_id=ids["small"],
                        modifier_option_ids=[999999],
                        quantity=1,
                    )
                ]
            },
            OrderCreationErrorCode.MODIFIER_OPTION_INVALID,
        ),
        (
            lambda ids: {
                "lines": [
                    ConfiguredOrderLineInput(
                        product_id=ids["product"],
                        variant_id=ids["small"],
                        modifier_option_ids=[],
                        quantity=1,
                    )
                ]
            },
            OrderCreationErrorCode.MODIFIER_SELECTION_INVALID,
        ),
        (
            lambda ids: {
                "lines": [
                    ConfiguredOrderLineInput(
                        product_id=ids["product"],
                        variant_id=ids["small"],
                        modifier_option_ids=[ids["whole"], ids["oat"]],
                        quantity=1,
                    )
                ]
            },
            OrderCreationErrorCode.MODIFIER_SELECTION_INVALID,
        ),
    ],
)
def test_rejects_invalid_pickup_variants_and_modifiers_atomically(
    prepared_order_engine: Engine,
    request_change: object,
    expected_code: OrderCreationErrorCode,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        request = make_request(ids, **request_change(ids))

        with pytest.raises(OrderCreationError) as error:
            OrderCreationService(session).create_pending_order(
                request,
                now=local_datetime(8),
            )

        assert error.value.code == expected_code
        assert session.scalar(select(text("count(*)")).select_from(Order)) == 0
        assert session.scalar(select(text("count(*)")).select_from(OrderItem)) == 0


@pytest.mark.postgresql
def test_rejects_unpublished_and_unavailable_products(
    prepared_order_engine: Engine,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        product = session.get(Product, ids["product"])
        assert product is not None
        product.is_published = False
        session.commit()

        with pytest.raises(OrderCreationError) as unpublished:
            OrderCreationService(session).create_pending_order(
                make_request(ids),
                now=local_datetime(8),
            )
        assert (
            unpublished.value.code
            == OrderCreationErrorCode.PRODUCT_NOT_SELLABLE
        )

        product.is_published = True
        product.availability_overrides.append(
            ProductAvailabilityOverride(
                business_date=date(2026, 7, 28),
                is_available=False,
                reason="Sold out today",
            )
        )
        session.commit()

        with pytest.raises(OrderCreationError, match="Sold out today"):
            OrderCreationService(session).create_pending_order(
                make_request(ids),
                now=local_datetime(8),
            )

        assert session.scalar(select(text("count(*)")).select_from(Order)) == 0


@pytest.mark.postgresql
def test_failure_on_later_line_rolls_back_entire_order(
    prepared_order_engine: Engine,
) -> None:
    with Session(prepared_order_engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        request = make_request(
            ids,
            lines=[
                ConfiguredOrderLineInput(
                    product_id=ids["product"],
                    variant_id=ids["small"],
                    modifier_option_ids=[ids["whole"]],
                    quantity=1,
                ),
                ConfiguredOrderLineInput(
                    product_id=999999,
                    variant_id=None,
                    modifier_option_ids=[],
                    quantity=1,
                ),
            ],
        )

        with pytest.raises(OrderCreationError):
            OrderCreationService(session).create_pending_order(
                request,
                now=local_datetime(8),
            )

        assert session.scalar(select(text("count(*)")).select_from(Order)) == 0
        assert session.scalar(select(text("count(*)")).select_from(OrderItem)) == 0
        assert (
            session.scalar(
                select(text("count(*)")).select_from(OrderItemModifier)
            )
            == 0
        )
