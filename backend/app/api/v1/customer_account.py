from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.customer_auth import current_customer, customer_csrf
from app.api.v1.orders import get_order_session
from app.api.v1.order_schemas import PendingOrderResponse
from app.customers.account_schemas import CustomerOrderSummary, CustomerOrderSummaryItem, CustomerOrderSummaryModifier, CustomerProfileResponse, CustomerProfileUpdate, CustomerQuickOrderResponse
from app.customers.repository import CustomerRepository
from app.customers.service import CustomerAccountService
from app.jds_auth.service import AuthPrincipal
from app.orders.constants import FulfillmentStatus
from app.orders.models import Order


class CustomerOrderDetail(PendingOrderResponse):
    fulfillment_status: FulfillmentStatus
    tax_name: str

    @classmethod
    def from_model(cls, order: Order) -> "CustomerOrderDetail":
        snapshot = PendingOrderResponse.from_model(order)
        return cls(
            **snapshot.model_dump(),
            fulfillment_status=order.fulfillment_status,
            tax_name=order.tax_name,
        )

router = APIRouter(prefix="/customer", tags=["customer-account"])


@router.get("/profile", response_model=CustomerProfileResponse)
def get_profile(response: Response, principal: AuthPrincipal = Depends(current_customer), session: Session = Depends(get_order_session)) -> CustomerProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return CustomerAccountService(session).profile(principal.user_id)
    except (SQLAlchemyError, LookupError) as error:
        raise HTTPException(status_code=503, detail="Customer profile is unavailable.") from error


@router.put("/profile", response_model=CustomerProfileResponse)
def update_profile(payload: CustomerProfileUpdate, response: Response, principal: AuthPrincipal = Depends(customer_csrf), session: Session = Depends(get_order_session)) -> CustomerProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return CustomerAccountService(session).update_profile(principal.user_id, payload)
    except (SQLAlchemyError, LookupError) as error:
        raise HTTPException(status_code=503, detail="Customer profile is unavailable.") from error


@router.get("/orders", response_model=list[CustomerOrderSummary])
def list_orders(principal: AuthPrincipal = Depends(current_customer), session: Session = Depends(get_order_session)) -> list[CustomerOrderSummary]:
    try:
        return [CustomerOrderSummary(
            id=order.id, status=order.status, requested_pickup_at=order.requested_pickup_at.isoformat(),
            total_cents=order.total_cents, created_at=order.created_at.isoformat(),
            item_count=sum(item.quantity for item in order.items),
            fulfillment_status=order.fulfillment_status,
            business_timezone=order.business_timezone,
            first_item=CustomerOrderSummaryItem(
                product_name=order.items[0].product_name,
                variant_name=order.items[0].variant_name,
                quantity=order.items[0].quantity,
                modifiers=[CustomerOrderSummaryModifier(
                    group_name=modifier.modifier_group_name,
                    option_name=modifier.modifier_option_name,
                    quantity=modifier.quantity,
                ) for modifier in order.items[0].modifiers],
            ),
        ) for order in CustomerRepository(session).orders(principal.user_id)]
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Order history is unavailable.") from error


@router.get("/quick-order", response_model=CustomerQuickOrderResponse)
def quick_order(response: Response, principal: AuthPrincipal = Depends(current_customer), session: Session = Depends(get_order_session)) -> CustomerQuickOrderResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        repository = CustomerRepository(session)
        product_ids = repository.quick_order_product_ids(principal.user_id)
        return CustomerQuickOrderResponse(product_ids=[str(product_id) for product_id in product_ids], configurations=repository.quick_order_configurations(principal.user_id))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Quick Order personalization is unavailable.") from error


@router.get("/orders/{order_id}", response_model=CustomerOrderDetail)
def get_order(order_id: int, principal: AuthPrincipal = Depends(current_customer), session: Session = Depends(get_order_session)) -> CustomerOrderDetail:
    try:
        order = CustomerRepository(session).order(principal.user_id, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        return CustomerOrderDetail.from_model(order)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Order history is unavailable.") from error
