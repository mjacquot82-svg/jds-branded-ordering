from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoyaltyProgram(Base):
    __tablename__ = "loyalty_programs"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_loyalty_programs_organization_slug"),
        CheckConstraint("stamps_required > 0", name="stamps_required_positive"),
        CheckConstraint("earning_rule = 'one_per_completed_qualifying_order'", name="earning_rule_valid"),
        CheckConstraint("reward_type = 'free_qualifying_product'", name="reward_type_valid"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    stamps_required: Mapped[int] = mapped_column(Integer, default=6, server_default="6")
    reward_description: Mapped[str] = mapped_column(String(200))
    earning_rule: Mapped[str] = mapped_column(String(60), default="one_per_completed_qualifying_order", server_default="one_per_completed_qualifying_order")
    reward_type: Mapped[str] = mapped_column(String(60), default="free_qualifying_product", server_default="free_qualifying_product")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LoyaltyProgramProduct(Base):
    __tablename__ = "loyalty_program_products"
    __table_args__ = (
        UniqueConstraint("loyalty_program_id", "product_id", name="uq_loyalty_program_products_program_product"),
        CheckConstraint("earning_eligible OR reward_eligible", name="some_eligibility_required"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    loyalty_program_id: Mapped[UUID] = mapped_column(ForeignKey("loyalty_programs.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    earning_eligible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    reward_eligible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerLoyaltyEvent(Base):
    __tablename__ = "customer_loyalty_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('stamp_earned','reward_earned','reward_redeemed','manual_adjustment','reversal')", name="event_type_valid"),
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        CheckConstraint("threshold_snapshot IS NULL OR threshold_snapshot > 0", name="threshold_snapshot_positive"),
        CheckConstraint("event_type NOT IN ('manual_adjustment','reversal') OR (actor_user_id IS NOT NULL AND reason IS NOT NULL AND btrim(reason) <> '')", name="manual_audit_required"),
        CheckConstraint("event_type <> 'stamp_earned' OR (quantity = 1 AND related_order_id IS NOT NULL)", name="stamp_earned_shape_valid"),
        CheckConstraint("event_type <> 'reward_earned' OR (quantity > 0 AND threshold_snapshot IS NOT NULL)", name="reward_earned_shape_valid"),
        CheckConstraint("event_type <> 'reward_redeemed' OR quantity > 0", name="reward_redeemed_quantity_positive"),
        CheckConstraint("event_type = 'reward_earned' OR threshold_snapshot IS NULL", name="threshold_snapshot_event_valid"),
        Index("uq_loyalty_order_stamp", "loyalty_program_id", "related_order_id", unique=True, postgresql_where=text("event_type = 'stamp_earned' AND related_order_id IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    customer_user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="RESTRICT"), index=True)
    loyalty_program_id: Mapped[UUID] = mapped_column(ForeignKey("loyalty_programs.id", ondelete="RESTRICT"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    related_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    threshold_snapshot: Mapped[int | None] = mapped_column(Integer)
    program_name_snapshot: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
