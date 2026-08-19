from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.catalog.models import Category, Product
from app.jds_auth.models import JdsUser, Membership, Role
from app.loyalty.models import CustomerLoyaltyEvent, LoyaltyProgram, LoyaltyProgramProduct
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.models import Order, OrderItem

DEFAULT_SLUG = "coffee-tea"
DEFAULTS = {
    "slug": DEFAULT_SLUG,
    "name": "Coffee & Tea Loyalty",
    "description": "Buy 6 qualifying drinks and get your 7th free.",
    "enabled": False,
    "stamps_required": 6,
    "reward_description": "Your next qualifying drink is free, any size.",
    "earning_rule": "one_per_completed_qualifying_order",
    "reward_type": "free_qualifying_product",
}


@dataclass(frozen=True)
class LoyaltyBalance:
    stamps: int
    rewards_available: int
    lifetime_stamps: int


class LoyaltyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def programs(self, organization_id: UUID, *, enabled_only: bool = False) -> list[LoyaltyProgram]:
        query = select(LoyaltyProgram).where(LoyaltyProgram.organization_id == organization_id)
        if enabled_only:
            query = query.where(LoyaltyProgram.enabled.is_(True))
        return list(self.session.scalars(query.order_by(LoyaltyProgram.created_at, LoyaltyProgram.id)))

    def program(self, organization_id: UUID, program_id: UUID) -> LoyaltyProgram | None:
        return self.session.scalar(select(LoyaltyProgram).where(LoyaltyProgram.id == program_id, LoyaltyProgram.organization_id == organization_id))

    def save_program(self, organization_id: UUID, *, program_id: UUID | None, values: dict, earning_product_ids: set[int], reward_product_ids: set[int]) -> LoyaltyProgram:
        program = self.program(organization_id, program_id) if program_id else None
        if program is None:
            if program_id is not None:
                raise ValueError("program_not_found")
            program = LoyaltyProgram(organization_id=organization_id, slug=DEFAULT_SLUG)
            self.session.add(program)
        else:
            self.session.refresh(program, with_for_update=True)
            if program.stamps_required != values["stamps_required"]:
                has_history = self.session.scalar(select(CustomerLoyaltyEvent.id).where(CustomerLoyaltyEvent.loyalty_program_id == program.id).limit(1))
                if has_history:
                    raise ValueError("threshold_has_history")
        for key in ("name", "description", "enabled", "stamps_required", "reward_description"):
            setattr(program, key, values[key])
        program.earning_rule = DEFAULTS["earning_rule"]
        program.reward_type = DEFAULTS["reward_type"]
        self.session.flush()
        all_ids = earning_product_ids | reward_product_ids
        existing_products = set(self.session.scalars(select(Product.id).where(Product.organization_id == organization_id, Product.id.in_(all_ids)))) if all_ids else set()
        if existing_products != all_ids:
            raise ValueError("product_not_found")
        existing = {item.product_id: item for item in self.session.scalars(select(LoyaltyProgramProduct).where(LoyaltyProgramProduct.loyalty_program_id == program.id))}
        for product_id, item in existing.items():
            if product_id not in all_ids:
                self.session.delete(item)
            else:
                item.earning_eligible = product_id in earning_product_ids
                item.reward_eligible = product_id in reward_product_ids
        for product_id in all_ids - existing.keys():
            self.session.add(LoyaltyProgramProduct(organization_id=organization_id, loyalty_program_id=program.id, product_id=product_id, earning_eligible=product_id in earning_product_ids, reward_eligible=product_id in reward_product_ids))
        self.session.commit()
        return program

    def award_completed_order(self, order_id: int, *, organization_id: UUID) -> int:
        order = self.session.scalar(select(Order).where(Order.id == order_id, Order.organization_id == organization_id).with_for_update())
        if order is None or order.status != OrderStatus.PAID or order.fulfillment_status != FulfillmentStatus.COMPLETED or order.customer_user_id is None:
            return 0
        product_ids = set(self.session.scalars(select(OrderItem.source_product_id).where(OrderItem.order_id == order.id, OrderItem.source_product_id.is_not(None))))
        if not product_ids:
            return 0
        eligible_product = exists(select(LoyaltyProgramProduct.id).where(LoyaltyProgramProduct.loyalty_program_id == LoyaltyProgram.id, LoyaltyProgramProduct.earning_eligible.is_(True), LoyaltyProgramProduct.product_id.in_(product_ids)))
        programs = list(self.session.scalars(select(LoyaltyProgram).where(LoyaltyProgram.organization_id == organization_id, LoyaltyProgram.enabled.is_(True), eligible_product).with_for_update()))
        awarded = 0
        for program in programs:
            existing_event_id = self.session.scalar(select(CustomerLoyaltyEvent.id).where(CustomerLoyaltyEvent.loyalty_program_id == program.id, CustomerLoyaltyEvent.related_order_id == order.id, CustomerLoyaltyEvent.event_type == "stamp_earned"))
            if existing_event_id:
                continue
            self.session.add(CustomerLoyaltyEvent(organization_id=organization_id, customer_user_id=order.customer_user_id, loyalty_program_id=program.id, event_type="stamp_earned", quantity=1, related_order_id=order.id, program_name_snapshot=program.name))
            self.session.flush()
            self._issue_due_rewards(order.customer_user_id, program)
            awarded += 1
        return awarded

    def balance(self, customer_user_id: UUID, program: LoyaltyProgram) -> LoyaltyBalance:
        rows = self.session.execute(select(CustomerLoyaltyEvent.event_type, func.coalesce(func.sum(CustomerLoyaltyEvent.quantity), 0)).where(CustomerLoyaltyEvent.customer_user_id == customer_user_id, CustomerLoyaltyEvent.loyalty_program_id == program.id).group_by(CustomerLoyaltyEvent.event_type)).all()
        totals = dict(rows)
        lifetime = max(0, totals.get("stamp_earned", 0) + totals.get("manual_adjustment", 0) + totals.get("reversal", 0))
        consumed = self.session.scalar(select(func.coalesce(func.sum(CustomerLoyaltyEvent.quantity * CustomerLoyaltyEvent.threshold_snapshot), 0)).where(CustomerLoyaltyEvent.customer_user_id == customer_user_id, CustomerLoyaltyEvent.loyalty_program_id == program.id, CustomerLoyaltyEvent.event_type == "reward_earned")) or 0
        available = max(0, totals.get("reward_earned", 0) - totals.get("reward_redeemed", 0))
        return LoyaltyBalance(stamps=max(0, lifetime - consumed), rewards_available=available, lifetime_stamps=lifetime)

    def adjust(self, customer_user_id: UUID, program: LoyaltyProgram, *, quantity: int, actor_user_id: UUID, reason: str) -> CustomerLoyaltyEvent:
        if quantity == 0 or not reason.strip():
            raise ValueError("adjustment_invalid")
        self.session.refresh(program, with_for_update=True)
        current = self.balance(customer_user_id, program)
        if quantity < 0 and -quantity > current.stamps:
            raise ValueError("adjustment_exceeds_balance")
        event = CustomerLoyaltyEvent(organization_id=program.organization_id, customer_user_id=customer_user_id, loyalty_program_id=program.id, event_type="manual_adjustment", quantity=quantity, actor_user_id=actor_user_id, reason=reason.strip(), program_name_snapshot=program.name)
        self.session.add(event)
        self.session.flush()
        self._issue_due_rewards(customer_user_id, program)
        self.session.commit()
        return event

    def _issue_due_rewards(self, customer_user_id: UUID, program: LoyaltyProgram) -> None:
        balance = self.balance(customer_user_id, program)
        due = balance.stamps // program.stamps_required
        if due:
            self.session.add(CustomerLoyaltyEvent(organization_id=program.organization_id, customer_user_id=customer_user_id, loyalty_program_id=program.id, event_type="reward_earned", quantity=due, threshold_snapshot=program.stamps_required, program_name_snapshot=program.name))
            self.session.flush()

    def customer_summary(self, customer_user_id: UUID, organization_id: UUID, *, include_inactive: bool = False) -> list[dict]:
        programs = self.programs(organization_id, enabled_only=not include_inactive)
        result = []
        for program in programs:
            balance = self.balance(customer_user_id, program)
            activity = list(self.session.scalars(select(CustomerLoyaltyEvent).where(CustomerLoyaltyEvent.customer_user_id == customer_user_id, CustomerLoyaltyEvent.loyalty_program_id == program.id).order_by(CustomerLoyaltyEvent.created_at.desc()).limit(10)))
            result.append({"program": program, "balance": balance, "activity": activity})
        return result

    def catalog(self, organization_id: UUID) -> list[dict]:
        rows = self.session.execute(select(Product, Category.name).join(Category, Category.id == Product.category_id).where(Product.organization_id == organization_id, Category.organization_id == organization_id, Product.archived_at.is_(None)).order_by(Category.sort_order, Product.sort_order, Product.name)).all()
        return [{"id": p.id, "name": p.name, "category": category, "published": p.is_published} for p, category in rows]

    def customers(self, organization_id: UUID, query: str) -> list[JdsUser]:
        pattern = f"%{query.strip()}%"
        return list(self.session.scalars(select(JdsUser).join(Membership, Membership.user_id == JdsUser.id).join(Role, Role.id == Membership.role_id).where(Membership.organization_id == organization_id, Membership.status == "active", Role.key.in_(("customer", "owner")), (JdsUser.display_name.ilike(pattern) | JdsUser.primary_email.ilike(pattern))).order_by(JdsUser.display_name).limit(25)))

    def customer(self, organization_id: UUID, customer_user_id: UUID) -> JdsUser | None:
        return self.session.scalar(select(JdsUser).join(Membership, Membership.user_id == JdsUser.id).join(Role, Role.id == Membership.role_id).where(JdsUser.id == customer_user_id, Membership.organization_id == organization_id, Membership.status == "active", Role.key.in_(("customer", "owner"))))
