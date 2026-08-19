from fastapi import APIRouter

from app.api.v1.catalog import router as catalog_router
from app.api.v1.clover import router as clover_router
from app.api.v1.orders import router as orders_router
from app.api.v1.owner_auth import router as owner_auth_router
from app.api.v1.owner_catalog import router as owner_catalog_router
from app.api.v1.owner_scheduling import router as owner_scheduling_router
from app.api.v1.owner_orders import router as owner_orders_router
from app.api.v1.owner_customers import router as owner_customers_router
from app.api.v1.customer_auth import router as customer_auth_router
from app.api.v1.customer_account import router as customer_account_router
from app.api.v1.scheduling import router as scheduling_router
from app.api.v1.runtime_diagnostics import router as runtime_diagnostics_router
from app.api.v1.owner_communications import router as owner_communications_router
from app.api.v1.customer_push import router as customer_push_router
from app.api.v1.staff_access import router as staff_access_router
from app.api.v1.loyalty import router as loyalty_router
from app.api.v1.platform import router as platform_router

router = APIRouter(prefix="/api/v1")
router.include_router(catalog_router)
router.include_router(orders_router)
router.include_router(clover_router)
router.include_router(owner_auth_router)
router.include_router(owner_catalog_router)
router.include_router(owner_scheduling_router)
router.include_router(owner_orders_router)
router.include_router(owner_customers_router)
router.include_router(customer_auth_router)
router.include_router(customer_account_router)
router.include_router(scheduling_router)
router.include_router(runtime_diagnostics_router)
router.include_router(owner_communications_router)
router.include_router(customer_push_router)
router.include_router(staff_access_router)
router.include_router(loyalty_router)
router.include_router(platform_router)
