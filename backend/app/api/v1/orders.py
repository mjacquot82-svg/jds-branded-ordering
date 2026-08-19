from collections.abc import Awaitable, Callable, Generator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.api.v1.order_schemas import (
    CreateOrderRequest,
    OrderErrorResponse,
    PendingOrderResponse,
)
from app.availability.service import AvailabilityConfigurationError
from app.orders.models import Order, OrderItem
from app.orders.service import (
    OrderCreationError,
    OrderCreationErrorCode,
    OrderCreationService,
)
from app.api.v1.customer_auth import current_ordering_customer
from app.jds_auth.service import AuthPrincipal

class OrderApiRoute(APIRoute):
    def get_route_handler(
        self,
    ) -> Callable[[Request], Awaitable[Response]]:
        original_handler = super().get_route_handler()

        async def validation_error_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={
                        "detail": {
                            "code": "request_validation_error",
                            "message": "Order request validation failed.",
                        }
                    },
                )

        return validation_error_handler


router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    route_class=OrderApiRoute,
)

DOMAIN_ERROR_STATUS = {
    OrderCreationErrorCode.IDEMPOTENCY_CONFLICT: status.HTTP_409_CONFLICT,
    OrderCreationErrorCode.PICKUP_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    OrderCreationErrorCode.PRODUCT_NOT_SELLABLE: status.HTTP_422_UNPROCESSABLE_CONTENT,
    OrderCreationErrorCode.VARIANT_REQUIRED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    OrderCreationErrorCode.VARIANT_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    OrderCreationErrorCode.MODIFIER_OPTION_INVALID: (
        status.HTTP_422_UNPROCESSABLE_CONTENT
    ),
    OrderCreationErrorCode.MODIFIER_SELECTION_INVALID: (
        status.HTTP_422_UNPROCESSABLE_CONTENT
    ),
}

ERROR_RESPONSES = {
    409: {
        "model": OrderErrorResponse,
        "description": "The idempotency key was used for a different order.",
    },
    422: {
        "model": OrderErrorResponse,
        "description": "Request validation or an order business rule failed.",
    },
    503: {
        "model": OrderErrorResponse,
        "description": "Order persistence or configuration is unavailable.",
    },
}


def get_order_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.db_session_factory
    if session_factory is None:
        raise_order_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "order_service_unavailable",
            "Order service is unavailable.",
        )

    with session_factory() as session:
        yield session


def get_current_time() -> datetime:
    return datetime.now(timezone.utc)


def raise_order_http_error(
    status_code: int,
    code: str,
    message: str,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@router.post(
    "",
    response_model=PendingOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pending guest order",
    description=(
        "Validates a guest order against the current catalog, availability, "
        "and pickup rules, then creates an authoritatively priced pending order."
    ),
    responses=ERROR_RESPONSES,
)
def create_pending_order(
    request: CreateOrderRequest,
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
    customer: AuthPrincipal = Depends(current_ordering_customer),
) -> PendingOrderResponse:
    try:
        domain_request = request.to_domain()
        order = OrderCreationService(session).create_pending_order(
            domain_request,
            now=now,
            customer_user_id=customer.user_id,
        )
        return PendingOrderResponse.from_model(order)
    except OrderCreationError as error:
        raise_order_http_error(
            DOMAIN_ERROR_STATUS[error.code],
            error.code.value,
            str(error),
        )
    except AvailabilityConfigurationError:
        raise_order_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "order_service_unavailable",
            "Order service is unavailable.",
        )
    except SQLAlchemyError:
        raise_order_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "order_service_unavailable",
            "Order service is unavailable.",
        )


@router.get(
    "/{public_token}",
    response_model=PendingOrderResponse,
    summary="Retrieve an order",
    description="Returns the current order snapshot by its public token.",
    responses={
        404: {
            "model": OrderErrorResponse,
            "description": "No pending order exists for the public token.",
        },
        503: ERROR_RESPONSES[503],
    },
)
def get_pending_order(
    public_token: Annotated[
        str,
        Path(
            min_length=1,
            max_length=200,
            description="Opaque public order-access token.",
        ),
    ],
    customer: AuthPrincipal = Depends(current_ordering_customer),
    session: Session = Depends(get_order_session),
) -> PendingOrderResponse:
    try:
        order = session.scalar(
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
            )
            .where(
                Order.public_access_token == public_token,
                Order.customer_user_id == customer.user_id,
            )
        )
        if order is None:
            raise_order_http_error(
                status.HTTP_404_NOT_FOUND,
                "order_not_found",
                "Pending order was not found.",
            )
        return PendingOrderResponse.from_model(order)
    except SQLAlchemyError:
        raise_order_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "order_service_unavailable",
            "Order service is unavailable.",
        )
