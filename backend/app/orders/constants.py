from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"


class FulfillmentStatus(str, Enum):
    NEW = "new"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


DEFAULT_CURRENCY = "CAD"
DEFAULT_PENDING_EXPIRY_MINUTES = 30
MAX_LINE_QUANTITY = 50
MAX_ORDER_LINES = 100
MAX_ORDER_NOTES_LENGTH = 2000
