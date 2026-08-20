"""Repair legacy customer values in the Ladel's tenant relationship.

Revision ID: 20260820_29
Revises: 20260819_28

Migration 27 may have created a relationship before migration 28 encountered the
legacy profile.  Migration 28 deliberately did not overwrite conflicts, so this
forward repair fills only values that are still empty.  Existing relationship
values are authoritative and are never replaced.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260820_29"
down_revision: str | None = "20260819_28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A legacy profile has no tenant key.  It is safe to map it only when the
    # canonical legacy slug resolves to exactly one organization.  This guard
    # also catches damaged schemas where the slug uniqueness invariant was lost.
    op.execute("""
        DO $$
        DECLARE ladels_count integer;
        BEGIN
          SELECT count(*) INTO ladels_count
            FROM organizations
           WHERE slug = 'the-guest-house';
          IF ladels_count <> 1 THEN
            RAISE EXCEPTION
              'cannot safely map legacy customer profiles: expected exactly one Ladel''s organization, found %',
              ladels_count;
          END IF;
        END $$
    """)

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
        ON CONFLICT (organization_id, user_id) DO UPDATE
          SET display_name = CASE
                WHEN NULLIF(btrim(organization_customers.display_name), '') IS NULL
                  THEN EXCLUDED.display_name
                ELSE organization_customers.display_name
              END,
              phone = CASE
                WHEN NULLIF(btrim(organization_customers.phone), '') IS NULL
                  THEN EXCLUDED.phone
                ELSE organization_customers.phone
              END,
              preferred_pickup_minutes = COALESCE(
                organization_customers.preferred_pickup_minutes,
                EXCLUDED.preferred_pickup_minutes
              ),
              preferred_pickup_notes = CASE
                WHEN NULLIF(btrim(organization_customers.preferred_pickup_notes), '') IS NULL
                  THEN EXCLUDED.preferred_pickup_notes
                ELSE organization_customers.preferred_pickup_notes
              END,
              updated_at = CASE
                WHEN NULLIF(btrim(organization_customers.display_name), '') IS NULL
                  OR NULLIF(btrim(organization_customers.phone), '') IS NULL
                  OR organization_customers.preferred_pickup_minutes IS NULL
                  OR NULLIF(btrim(organization_customers.preferred_pickup_notes), '') IS NULL
                  THEN now()
                ELSE organization_customers.updated_at
              END
    """)

    # Validate values, not just relationship existence.  A non-empty/newer
    # relationship value satisfies preservation; otherwise every meaningful
    # legacy value must now be present in its tenant relationship field.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1
              FROM customer_profiles profiles
              JOIN jds_users users
                ON users.id = profiles.user_id
              JOIN organizations
                ON organizations.slug = 'the-guest-house'
         LEFT JOIN organization_customers relationships
                ON relationships.organization_id = organizations.id
               AND relationships.user_id = profiles.user_id
             WHERE relationships.id IS NULL
                OR (
                     NULLIF(btrim(users.display_name), '') IS NOT NULL
                     AND NULLIF(btrim(relationships.display_name), '') IS NULL
                   )
                OR (
                     NULLIF(btrim(profiles.phone), '') IS NOT NULL
                     AND NULLIF(btrim(relationships.phone), '') IS NULL
                   )
                OR (
                     profiles.preferred_pickup_minutes IS NOT NULL
                     AND relationships.preferred_pickup_minutes IS NULL
                   )
                OR (
                     NULLIF(btrim(profiles.preferred_pickup_notes), '') IS NOT NULL
                     AND NULLIF(btrim(relationships.preferred_pickup_notes), '') IS NULL
                   )
          ) THEN
            RAISE EXCEPTION
              'legacy customer profile field preservation is incomplete';
          END IF;
        END $$
    """)


def downgrade() -> None:
    # The merge is intentionally non-destructive and cannot distinguish values
    # filled by this repair from later tenant-owned updates.  Retain all rows.
    pass
