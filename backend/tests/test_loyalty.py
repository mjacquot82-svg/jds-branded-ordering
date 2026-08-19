from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.jds_auth.foundation import ROLE_PERMISSIONS
from app.jds_auth.models import JdsApplication, JdsUser, Membership, Organization, Role
from app.loyalty.models import CustomerLoyaltyEvent, LoyaltyProgram, LoyaltyProgramProduct
from app.loyalty.service import LoyaltyService
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.fulfillment import FulfillmentError, OwnerOrderService
from app.api.v1.loyalty import ProgramInput
from app.orders.models import Order, OrderItem
from app.platform.models import CustomerRelationship
from tests.test_migrations import make_alembic_config
from tests.test_order_service import LADELS_TENANT, seed_order_dependencies


def test_loyalty_permissions_are_owner_only_and_threshold_means_six_paid_orders():
    assert {"loyalty.manage", "loyalty.adjust"}.issubset(ROLE_PERMISSIONS["owner"])
    assert "loyalty.manage" not in ROLE_PERMISSIONS["manager"]
    assert "loyalty.adjust" not in ROLE_PERMISSIONS["staff"]
    assert LoyaltyProgram(stamps_required=6).stamps_required == 6
    with pytest.raises(ValueError):
        ProgramInput(name="   ", description="Valid", enabled=False, stamps_required=6, reward_description="Free drink", earning_product_ids=[], reward_product_ids=[])


def make_order(session, customer_id, product_id, key, *, payment=OrderStatus.PAID, fulfillment=FulfillmentStatus.NEW, quantity=1):
    now=datetime.now(timezone.utc)
    organization_id=session.scalar(select(Product.organization_id).where(Product.id==product_id))
    order=Order(organization_id=organization_id,customer_user_id=customer_id,idempotency_key=key,request_fingerprint=(key[0]*64),public_access_token=f"token-{key}",status=payment,fulfillment_status=fulfillment,guest_name="Loyal Customer",guest_email=f"{key}@example.com",guest_phone="+15195550100",requested_pickup_at=now+timedelta(minutes=20),business_timezone="America/Toronto",currency="CAD",subtotal_cents=500*quantity,tax_cents=65*quantity,tax_name="HST",tax_rate_millionths=1_300_000,total_cents=565*quantity,version=1,expires_at=now+timedelta(hours=1),created_at=now,updated_at=now,items=[OrderItem(source_product_id=product_id,product_slug="drink",product_name="Drink snapshot",base_unit_price_cents=500,unit_price_cents=500,quantity=quantity,line_subtotal_cents=500*quantity,sort_order=0)])
    session.add(order);session.flush();return order


@pytest.fixture
def loyalty_db(postgresql_url):
    command.upgrade(make_alembic_config(postgresql_url),"head")
    from sqlalchemy import create_engine
    engine=create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE customer_loyalty_events, loyalty_program_products, loyalty_programs, order_item_modifiers, order_items, orders, product_availability_overrides, product_availability, business_closures, business_hours, business_settings, product_modifier_groups, modifier_options, product_variants, products, modifier_groups, categories, jds_users, organizations RESTART IDENTITY CASCADE"))
    with Session(engine) as session:
        seed_order_dependencies(session);first_product=session.scalar(select(Product).order_by(Product.id));second_product=Product(organization_id=first_product.organization_id,category_id=first_product.category_id,slug="sandwich",name="Sandwich",description="Nonqualifying food",base_price_cents=900,is_published=True,is_featured=False,sort_order=1);session.add(second_product);org=session.get(Organization,first_product.organization_id);application=JdsApplication(key=f"loyalty-{uuid4()}",name="Loyalty App");customer=JdsUser(primary_email=f"customer-{uuid4()}@example.com",display_name="Customer",status="active",credential_state="active");actor=JdsUser(primary_email=f"owner-{uuid4()}@example.com",display_name="Owner",status="active",credential_state="active");session.add_all([application,customer,actor]);session.flush();role=Role(application_id=application.id,key="customer",name="Customer");session.add(role);session.flush();session.add_all([Membership(organization_id=org.id,application_id=application.id,user_id=customer.id,role_id=role.id,status="active",joined_at=datetime.now(timezone.utc)),CustomerRelationship(organization_id=org.id,user_id=customer.id,display_name=customer.display_name)]);products=[first_product,second_product];program=LoyaltyProgram(organization_id=org.id,slug="coffee-tea",name="Coffee & Tea Loyalty",description="Buy 6, get your 7th free.",enabled=True,stamps_required=6,reward_description="Free drink",earning_rule="one_per_completed_qualifying_order",reward_type="free_qualifying_product");second=LoyaltyProgram(organization_id=org.id,slug="future",name="Future Program",description="Structural test",enabled=True,stamps_required=3,reward_description="Future reward",earning_rule="one_per_completed_qualifying_order",reward_type="free_qualifying_product");session.add_all([program,second]);session.flush();session.add_all([LoyaltyProgramProduct(organization_id=org.id,loyalty_program_id=program.id,product_id=products[0].id,earning_eligible=True,reward_eligible=True),LoyaltyProgramProduct(organization_id=org.id,loyalty_program_id=second.id,product_id=products[1].id,earning_eligible=True,reward_eligible=True)]);session.commit();ids=(org.id,customer.id,actor.id,products[0].id,products[1].id,program.id,second.id)
    yield engine,ids
    engine.dispose()


@pytest.mark.postgresql
def test_completed_paid_order_awards_once_per_program_and_reopen_is_idempotent(loyalty_db):
    engine,(organization_id,customer,_,eligible,other,program_id,_)=loyalty_db
    with Session(engine) as session:
        session.add(LoyaltyProgramProduct(organization_id=organization_id,loyalty_program_id=program_id,product_id=other,earning_eligible=True,reward_eligible=True));order=make_order(session,customer,eligible,"eligible",quantity=5);order.items.append(OrderItem(source_product_id=other,product_slug="second-drink",product_name="Second qualifying drink",base_unit_price_cents=500,unit_price_cents=500,quantity=2,line_subtotal_cents=1000,sort_order=1));session.commit();service=OwnerOrderService(session,LADELS_TENANT);service.transition(order.id,target=FulfillmentStatus.COMPLETED,expected_version=1,now=datetime.now(timezone.utc));service.transition(order.id,target=FulfillmentStatus.NEW,expected_version=2,now=datetime.now(timezone.utc));service.transition(order.id,target=FulfillmentStatus.COMPLETED,expected_version=3,now=datetime.now(timezone.utc));
        assert session.scalar(select(func.count()).select_from(CustomerLoyaltyEvent).where(CustomerLoyaltyEvent.loyalty_program_id==program_id,CustomerLoyaltyEvent.event_type=="stamp_earned"))==1


@pytest.mark.postgresql
def test_nonqualifying_unpaid_failed_cancelled_and_disabled_do_not_earn(loyalty_db):
    engine,(_,customer,_,eligible,other,program_id,second_id)=loyalty_db
    with Session(engine) as session:
        session.get(LoyaltyProgram,second_id).enabled=False;nonqualifying=make_order(session,customer,other,"nonqualifying",fulfillment=FulfillmentStatus.COMPLETED);unpaid=make_order(session,customer,eligible,"unpaid",payment=OrderStatus.PAYMENT_PENDING,fulfillment=FulfillmentStatus.COMPLETED);failed=make_order(session,customer,eligible,"failed",payment=OrderStatus.PAYMENT_FAILED,fulfillment=FulfillmentStatus.COMPLETED);cancelled=make_order(session,customer,eligible,"cancelled",fulfillment=FulfillmentStatus.CANCELLED);session.commit();loyalty=LoyaltyService(session)
        for order in (nonqualifying,unpaid,failed,cancelled): assert loyalty.award_completed_order(order.id,organization_id=LADELS_TENANT.organization_id)==0
        session.get(LoyaltyProgram,program_id).enabled=False;disabled=make_order(session,customer,eligible,"disabled",fulfillment=FulfillmentStatus.COMPLETED);session.flush();assert loyalty.award_completed_order(disabled.id,organization_id=LADELS_TENANT.organization_id)==0
        session.get(LoyaltyProgram,program_id).enabled=True;reenabled=make_order(session,customer,eligible,"reenabled",fulfillment=FulfillmentStatus.COMPLETED);session.flush();assert loyalty.award_completed_order(reenabled.id,organization_id=LADELS_TENANT.organization_id)==1


@pytest.mark.postgresql
def test_six_orders_issue_reward_without_off_by_one_and_programs_are_independent(loyalty_db):
    engine,(_,customer,_,eligible,other,program_id,second_id)=loyalty_db
    with Session(engine) as session:
        loyalty=LoyaltyService(session)
        for index in range(6):
            order=make_order(session,customer,eligible,f"earned-{index}",fulfillment=FulfillmentStatus.COMPLETED);session.flush();assert loyalty.award_completed_order(order.id,organization_id=LADELS_TENANT.organization_id)==1
        session.flush();balance=loyalty.balance(customer,session.get(LoyaltyProgram,program_id));assert balance.stamps==0;assert balance.rewards_available==1
        for index in range(6,12):
            order=make_order(session,customer,eligible,f"earned-{index}",fulfillment=FulfillmentStatus.COMPLETED);session.flush();assert loyalty.award_completed_order(order.id,organization_id=LADELS_TENANT.organization_id)==1
        balance=loyalty.balance(customer,session.get(LoyaltyProgram,program_id));assert balance.stamps==0;assert balance.rewards_available==2
        loyalty.adjust(customer,session.get(LoyaltyProgram,program_id),quantity=1,actor_user_id=session.scalar(select(JdsUser.id).where(JdsUser.id!=customer)),reason="Test correction")
        loyalty.adjust(customer,session.get(LoyaltyProgram,program_id),quantity=-1,actor_user_id=session.scalar(select(JdsUser.id).where(JdsUser.id!=customer)),reason="Undo test correction")
        balance=loyalty.balance(customer,session.get(LoyaltyProgram,program_id));assert balance.stamps==0;assert balance.rewards_available==2
        with pytest.raises(ValueError,match="adjustment_exceeds_balance"): loyalty.adjust(customer,session.get(LoyaltyProgram,program_id),quantity=-1,actor_user_id=session.scalar(select(JdsUser.id).where(JdsUser.id!=customer)),reason="Impossible removal")
        assert loyalty.balance(customer,session.get(LoyaltyProgram,second_id)).rewards_available==0


@pytest.mark.postgresql
def test_eligibility_changes_only_future_orders_and_manual_adjustment_is_audited(loyalty_db):
    engine,(organization_id,customer,actor,eligible,other,program_id,_)=loyalty_db
    with Session(engine) as session:
        loyalty=LoyaltyService(session);first=make_order(session,customer,eligible,"before-change",fulfillment=FulfillmentStatus.COMPLETED);session.flush();loyalty.award_completed_order(first.id,organization_id=LADELS_TENANT.organization_id);link=session.scalar(select(LoyaltyProgramProduct).where(LoyaltyProgramProduct.loyalty_program_id==program_id,LoyaltyProgramProduct.product_id==eligible));session.delete(link);session.add(LoyaltyProgramProduct(organization_id=organization_id,loyalty_program_id=program_id,product_id=other,earning_eligible=True,reward_eligible=True));session.flush();second=make_order(session,customer,eligible,"after-change",fulfillment=FulfillmentStatus.COMPLETED);session.flush();assert loyalty.award_completed_order(second.id,organization_id=LADELS_TENANT.organization_id)==0
        event=loyalty.adjust(customer,session.get(LoyaltyProgram,program_id),quantity=2,actor_user_id=actor,reason="Transferred physical card");assert event.actor_user_id==actor;assert event.reason=="Transferred physical card";assert loyalty.balance(customer,session.get(LoyaltyProgram,program_id)).stamps==3
        assert session.scalar(select(func.count()).select_from(CustomerLoyaltyEvent).where(CustomerLoyaltyEvent.related_order_id==first.id))==1
        with pytest.raises(ValueError, match="threshold_has_history"):
            loyalty.save_program(session.get(LoyaltyProgram,program_id).organization_id,program_id=program_id,values={"name":"Coffee & Tea Loyalty","description":"Buy 6, get your 7th free.","enabled":True,"stamps_required":7,"reward_description":"Free drink"},earning_product_ids={other},reward_product_ids={other})


@pytest.mark.postgresql
def test_order_tenant_controls_loyalty_when_customer_has_multiple_memberships(loyalty_db):
    engine,(_,customer,_,eligible,_,program_id,_)=loyalty_db
    with Session(engine) as session:
        membership=session.scalar(select(Membership).where(Membership.user_id==customer))
        other_org=Organization(slug=f"other-{uuid4()}",name="Other Cafe")
        session.add(other_org);session.flush()
        session.add(Membership(organization_id=other_org.id,application_id=membership.application_id,user_id=customer,role_id=membership.role_id,status="active",joined_at=datetime.now(timezone.utc)))
        order=make_order(session,customer,eligible,"ambiguous-org",fulfillment=FulfillmentStatus.COMPLETED);session.flush()
        assert LoyaltyService(session).award_completed_order(order.id,organization_id=LADELS_TENANT.organization_id)==1
        assert session.scalar(select(func.count()).select_from(CustomerLoyaltyEvent).where(CustomerLoyaltyEvent.loyalty_program_id==program_id))==1


@pytest.mark.postgresql
def test_concurrent_completion_requests_cannot_duplicate_stamp(loyalty_db):
    engine,(_,customer,_,eligible,_,program_id,_)=loyalty_db
    with Session(engine) as session:
        order=make_order(session,customer,eligible,"concurrent");session.commit();order_id=order.id
    barrier=Barrier(2)
    def complete():
        with Session(engine) as session:
            barrier.wait()
            try: OwnerOrderService(session,LADELS_TENANT).transition(order_id,target=FulfillmentStatus.COMPLETED,expected_version=1,now=datetime.now(timezone.utc))
            except FulfillmentError: pass
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _:complete(),range(2)))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CustomerLoyaltyEvent).where(CustomerLoyaltyEvent.loyalty_program_id==program_id,CustomerLoyaltyEvent.related_order_id==order_id,CustomerLoyaltyEvent.event_type=="stamp_earned"))==1
