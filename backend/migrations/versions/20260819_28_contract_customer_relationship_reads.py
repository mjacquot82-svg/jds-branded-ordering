"""Contract runtime customer profiles onto tenant relationships.

Revision ID: 20260819_28
Revises: 20260819_27

The legacy table is intentionally retained as rollback evidence. Runtime code no
longer reads or writes it after this migration; organization_customers is the
single merchant-profile source of truth.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260819_28"
down_revision: str | None = "20260819_27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO organization_customers
            (id, organization_id, user_id, display_name, phone,
             preferred_pickup_minutes, preferred_pickup_notes)
        SELECT gen_random_uuid(), organizations.id, profiles.user_id,
               users.display_name, profiles.phone,
               profiles.preferred_pickup_minutes,
               profiles.preferred_pickup_notes
          FROM customer_profiles profiles
          JOIN jds_users users ON users.id = profiles.user_id
          JOIN organizations ON organizations.slug = 'the-guest-house'
        ON CONFLICT (organization_id, user_id) DO NOTHING
    """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1
              FROM customer_profiles profiles
              JOIN organizations ON organizations.slug = 'the-guest-house'
         LEFT JOIN organization_customers relationships
                ON relationships.organization_id = organizations.id
               AND relationships.user_id = profiles.user_id
             WHERE relationships.id IS NULL
          ) THEN
            RAISE EXCEPTION 'legacy customer profile backfill is incomplete';
          END IF;
        END $$
    """)


def downgrade() -> None:
    # Rows are retained: restoring older code must not lose legacy compatibility.
    pass
