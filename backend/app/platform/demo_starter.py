"""Generic fictional café starter for self-service demos (NOT Guest House / Ladel's)."""
from __future__ import annotations

from copy import deepcopy
from datetime import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.availability.models import BusinessHour, BusinessSettings
from app.catalog.models import Category, Product
from app.platform.design import DEFAULT_CONFIG
from app.platform.models import BusinessProfile, DesignWorkspace
from app.platform.starter_media import CAFE_RESTAURANT_COLLECTION, starter_reference

# Polished fictional café — deliberately not a real shop brand.
STARTER_CAFE_NAME = "Harbor & Hearth Café"
STARTER_TAGLINE = "Specialty coffee, fresh pastries, warm welcome"
STARTER_DESIGN = {
    **deepcopy(DEFAULT_CONFIG),
    "template": "cozy",
    "displayName": STARTER_CAFE_NAME,
    "tagline": STARTER_TAGLINE,
    "colors": {
        "primary": "#4a5d4e",
        "accent": "#c4784a",
        "background": "#f6f1ea",
        "surface": "#ffffff",
        "text": "#2a2f28",
    },
    "typography": "classic",
    "buttonStyle": "rounded",
    "branding": {"showLogo": True, "showHero": True, "headerMode": "tagline"},
    "heroContent": "tagline-cta",
    "hero": {"mode": "color", "mediaId": None},
    "announcement": {"enabled": True, "text": "Demo menu — customize me for your shop"},
    "pwa": {"shortName": "Harbor", "themeColor": "#4a5d4e", "backgroundColor": "#f6f1ea"},
}

STARTER_CATEGORIES = (
    ("coffee", "Coffee", 10),
    ("bakery", "Bakery", 20),
    ("breakfast", "Breakfast", 30),
)

STARTER_PRODUCTS = (
    # category_slug, slug, name, description, price_cents, sort
    ("coffee", "house-drip", "House Drip", "Smooth medium roast, always fresh.", 350, 10),
    ("coffee", "cafe-latte", "Café Latte", "Espresso with steamed milk.", 495, 20),
    ("coffee", "cappuccino", "Cappuccino", "Equal parts espresso, milk, and foam.", 475, 30),
    ("coffee", "iced-latte", "Iced Latte", "Espresso over ice with cold milk.", 525, 40),
    ("bakery", "butter-croissant", "Butter Croissant", "Flaky, golden, baked daily.", 375, 10),
    ("bakery", "blueberry-muffin", "Blueberry Muffin", "Bursting with berries.", 350, 20),
    ("bakery", "chocolate-cookie", "Chocolate Chunk Cookie", "Warm and gooey center.", 295, 30),
    ("breakfast", "avocado-toast", "Avocado Toast", "Sourdough, smashed avocado, chili flake.", 895, 10),
    ("breakfast", "yogurt-parfait", "Yogurt Parfait", "Greek yogurt, granola, seasonal fruit.", 650, 20),
)

# Platform starter illustrations (shared, read-only; never tenant media rows, so they
# never count toward prospect storage/file quotas). Merchants can replace any of them.
STARTER_PRODUCT_IMAGES = {
    "house-drip": "brewed-coffee",
    "cafe-latte": "latte",
    "cappuccino": "cappuccino",
    "iced-latte": "iced-latte",
    "butter-croissant": "plain-croissant",
    "blueberry-muffin": "muffin",
    "chocolate-cookie": "cookie",
    "avocado-toast": "toast",
    "yogurt-parfait": "yogurt-granola",
}


def starter_product_image_reference(product_slug: str) -> str | None:
    key = STARTER_PRODUCT_IMAGES.get(product_slug)
    return starter_reference(CAFE_RESTAURANT_COLLECTION, key, 1) if key else None


def apply_demo_starter(session: Session, organization_id: UUID, *, business_name: str | None = None) -> None:
    """Seed design + limited catalog using the REAL catalog/design architecture."""
    name = (business_name or STARTER_CAFE_NAME).strip() or STARTER_CAFE_NAME
    design = deepcopy(STARTER_DESIGN)
    design["displayName"] = name
    short = "".join(ch for ch in name.split()[0] if ch.isalnum())[:12] or "Cafe"
    design["pwa"] = {**design["pwa"], "shortName": short[:30]}

    workspace = session.get(DesignWorkspace, organization_id)
    if workspace is None:
        session.add(DesignWorkspace(organization_id=organization_id, draft_config=design))
    else:
        workspace.draft_config = design
        workspace.revision = max(1, int(workspace.revision or 1))

    profile = session.get(BusinessProfile, organization_id)
    if profile is None:
        session.add(
            BusinessProfile(
                organization_id=organization_id,
                display_name=name,
                timezone="America/Toronto",
                currency="CAD",
                fulfillment_wording="Pickup",
                pickup_instructions="Show your order confirmation at the counter.",
            )
        )
    else:
        profile.display_name = name

    settings = session.scalar(select(BusinessSettings).where(BusinessSettings.organization_id == organization_id))
    if settings is None:
        settings = BusinessSettings(
            organization_id=organization_id,
            timezone="America/Toronto",
            ordering_enabled=False,  # commerce locked for prospects
        )
        session.add(settings)
        session.flush()
        session.add_all(
            BusinessHour(
                organization_id=organization_id,
                business_settings_id=settings.id,
                weekday=weekday,
                is_closed=weekday >= 6,
                opens_at=None if weekday >= 6 else time(7, 30),
                closes_at=None if weekday >= 6 else time(17, 0),
            )
            for weekday in range(7)
        )

    existing = session.scalar(select(Category.id).where(Category.organization_id == organization_id).limit(1))
    if existing is not None:
        return

    categories: dict[str, Category] = {}
    for slug, label, sort_order in STARTER_CATEGORIES:
        category = Category(
            organization_id=organization_id,
            slug=slug,
            name=label,
            sort_order=sort_order,
            is_published=True,
        )
        session.add(category)
        session.flush()
        categories[slug] = category

    for category_slug, slug, product_name, description, price_cents, sort_order in STARTER_PRODUCTS:
        session.add(
            Product(
                organization_id=organization_id,
                category_id=categories[category_slug].id,
                slug=slug,
                name=product_name,
                description=description,
                base_price_cents=price_cents,
                sort_order=sort_order,
                is_published=True,
                image_reference=starter_product_image_reference(slug),
            )
        )
