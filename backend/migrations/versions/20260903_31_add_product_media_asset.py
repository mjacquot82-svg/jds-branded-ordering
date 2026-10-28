"""Reference tenant media assets from products.

Revision ID: 20260903_31
Revises: 20260821_30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_31"
down_revision: str | None = "20260821_30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("purpose", sa.String(20), nullable=False, server_default="design"))
    op.add_column("media_assets", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("height", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_media_assets_purpose", "media_assets", "purpose IN ('design','product')")
    op.add_column("products", sa.Column("media_asset_id", sa.Uuid(), nullable=True))
    op.execute("""
        UPDATE products p
        SET media_asset_id = m.id, image_reference = NULL
        FROM media_assets m
        WHERE p.organization_id = m.organization_id
          AND p.image_reference = '/api/v1/storefront/media/' || m.id::text
          AND m.status = 'active'
    """)
    op.create_foreign_key(
        "fk_products_organization_media_asset", "products", "media_assets",
        ["organization_id", "media_asset_id"], ["organization_id", "id"], ondelete="RESTRICT",
    )
    op.create_index("ix_products_media_asset_id", "products", ["media_asset_id"])


def downgrade() -> None:
    op.execute("""
        UPDATE products
        SET image_reference = '/api/v1/storefront/media/' || media_asset_id::text
        WHERE media_asset_id IS NOT NULL
    """)
    op.drop_index("ix_products_media_asset_id", table_name="products")
    op.drop_constraint("fk_products_organization_media_asset", "products", type_="foreignkey")
    op.drop_column("products", "media_asset_id")
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.drop_column("media_assets", "height")
    op.drop_column("media_assets", "width")
    op.drop_column("media_assets", "purpose")
