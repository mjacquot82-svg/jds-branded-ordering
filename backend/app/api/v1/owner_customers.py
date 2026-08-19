from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.orders import get_order_session
from app.api.v1.owner_auth import require_read_permission
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.models import JdsUser
from app.jds_auth.service import AuthPrincipal
from app.orders.models import Order
from app.platform.models import CustomerRelationship
from app.tenancy.context import TenantContext

router = APIRouter(prefix="/owner/customers", tags=["owner-customers"])


@router.get("")
def owner_customers(
    response: Response,
    q: str = Query(default="", max_length=100),
    _: AuthPrincipal = Depends(require_read_permission("orders.read")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
    session: Session = Depends(get_order_session),
) -> dict:
    query = (
        select(CustomerRelationship, JdsUser)
        .join(JdsUser, JdsUser.id == CustomerRelationship.user_id)
        .where(CustomerRelationship.organization_id == tenant.organization_id)
        .order_by(CustomerRelationship.updated_at.desc(), CustomerRelationship.id)
        .limit(100)
    )
    term = q.strip()
    if term:
        escaped_term = term.replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped_term}%"
        query = query.where(
            or_(
                CustomerRelationship.display_name.ilike(pattern, escape="\\"),
                JdsUser.primary_email.ilike(pattern, escape="\\"),
                CustomerRelationship.phone.ilike(pattern, escape="\\"),
            )
        )
    rows = session.execute(query).all()
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "customers": [
            {
                "id": str(relationship.user_id),
                "displayName": relationship.display_name or user.display_name,
                "email": user.primary_email,
                "phone": relationship.phone,
                "orderCount": session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(
                        Order.organization_id == tenant.organization_id,
                        Order.customer_user_id == relationship.user_id,
                    )
                )
                or 0,
                "updatedAt": relationship.updated_at,
            }
            for relationship, user in rows
        ]
    }
