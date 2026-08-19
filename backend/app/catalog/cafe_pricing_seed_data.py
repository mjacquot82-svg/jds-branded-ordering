"""Staged production catalog transcribed from Jessie's Cafe Pricing.docx.

This module is intentionally not wired into the seed command yet.  It can be
passed explicitly to ``seed_catalog`` after the review list in
``docs/CAFE_PRICING_CATALOG_REVIEW.md`` is resolved.
"""

from app.catalog.seed_data import (
    CatalogSeed,
    CategorySeed,
    ProductSeed,
    VariantSeed,
)


def variants(*entries: tuple[str, str, int]) -> tuple[VariantSeed, ...]:
    return tuple(VariantSeed(key=key, name=name, price_cents=price) for key, name, price in entries)


def product(
    slug: str,
    category: str,
    name: str,
    price: int,
    *,
    options: tuple[VariantSeed, ...] = (),
    featured: bool = False,
    image: str = "coffee",
) -> ProductSeed:
    return ProductSeed(
        slug=slug,
        category_slug=category,
        name=name,
        description="",
        base_price_cents=price,
        image_reference=image,
        is_featured=featured,
        variants=options,
    )


CAFE_PRICING_CATALOG = CatalogSeed(
    categories=(
        CategorySeed("coffee", "Coffee", "Brewed coffee and house coffee offerings."),
        CategorySeed("espresso", "Espresso", "Espresso and milk-based café drinks."),
        CategorySeed("tea-hot-drinks", "Tea & Hot Drinks", "Tea and other non-coffee hot drinks."),
        CategorySeed("cold-drinks", "Cold Drinks", "Cold refreshers, sparkling drinks, and water."),
        CategorySeed("smoothies", "Smoothies", "Blended fruit and protein drinks."),
        CategorySeed("meals", "Meals", "Bowls and wraps."),
        CategorySeed("snacks-bakery", "Snacks & Bakery", "Prepared snacks, breakfast items, and baked goods."),
        CategorySeed("retail", "Retail", "Packaged coffee, café goods, and merchandise."),
    ),
    products=(
        product("drip-coffee", "coffee", "Drip Coffee", 205, featured=True, options=variants(
            ("12oz", "12oz", 205), ("16oz", "16oz", 240), ("20oz", "20oz", 275)
        )),
        product("decaf-coffee", "coffee", "Decaf Coffee", 205, options=variants(
            ("12oz", "12oz", 205), ("16oz", "16oz", 240), ("20oz", "20oz", 257)
        )),
        product("iced-coffee", "coffee", "Iced Coffee", 245, options=variants(
            ("12oz", "12oz", 245), ("16oz", "16oz", 295), ("20oz", "20oz", 305)
        )),
        product("americano", "espresso", "Americano", 365, options=variants(
            ("12oz-hot", "12oz Hot", 365), ("12oz-iced", "12oz Iced", 395),
            ("16oz-hot", "16oz Hot", 385), ("16oz-iced", "16oz Iced", 415),
            ("20oz-hot", "20oz Hot", 405), ("20oz-iced", "20oz Iced", 435)
        )),
        product("brown-sugar-latte", "espresso", "Brown Sugar Latte (Cinnamon)", 675),
        product("cafe-mocha", "espresso", "Café Mocha", 510, options=variants(
            ("12oz-regular", "12oz Regular", 510), ("12oz-white", "12oz White", 510),
            ("16oz-regular", "16oz Regular", 565), ("16oz-white", "16oz White", 565),
            ("20oz-regular", "20oz Regular", 635), ("20oz-white", "20oz White", 635)
        )),
        product("cappuccino", "espresso", "Cappuccino", 445, options=variants(
            ("12oz", "12oz", 445), ("16oz", "16oz", 495), ("20oz", "20oz", 565)
        )),
        product("caramel-macchiato", "espresso", "Caramel Macchiato", 625, options=variants(
            ("12oz-hot", "12oz Hot", 625), ("16oz-hot", "16oz Hot", 695),
            ("20oz-hot", "20oz Hot", 765), ("12oz-iced", "12oz Iced", 655),
            ("16oz-iced", "16oz Iced", 725), ("20oz-iced", "20oz Iced", 795)
        )),
        product("espresso", "espresso", "Espresso", 350, options=variants(
            ("regular", "Regular", 350), ("decaf", "Decaf", 350)
        )),
        product("flat-white", "espresso", "Flat White", 456),
        product("frappe", "espresso", "Frappe", 700),
        product("iced-latte", "espresso", "Iced Latte", 475, options=variants(
            ("12oz", "12oz", 475), ("16oz", "16oz", 525), ("20oz", "20oz", 595)
        )),
        product("iced-mocha", "espresso", "Iced Mocha", 540, options=variants(
            ("12oz-regular", "12oz Regular", 540), ("12oz-white", "12oz White", 540),
            ("16oz-regular", "16oz Regular", 590), ("16oz-white", "16oz White", 590),
            ("20oz-regular", "20oz Regular", 660), ("20oz-white", "20oz White", 660)
        )),
        product("latte", "espresso", "Latte", 445, featured=True, options=variants(
            ("12oz", "12oz", 445), ("16oz", "16oz", 495), ("20oz", "20oz", 565)
        )),
        product("apple-cider", "tea-hot-drinks", "Apple Cider", 310, options=variants(
            ("12oz-hot", "12oz Hot", 310), ("16oz-hot", "16oz Hot", 350),
            ("20oz-hot", "20oz Hot", 390), ("12oz-iced", "12oz Iced", 310),
            ("16oz-iced", "16oz Iced", 350), ("20oz-iced", "20oz Iced", 390)
        )),
        product("chai-latte", "tea-hot-drinks", "Chai Latte", 455, options=variants(
            ("12oz-regular", "12oz Regular", 455), ("12oz-spicy", "12oz Spicy", 455),
            ("12oz-dirty", "12oz Dirty", 685), ("16oz-regular", "16oz Regular", 505),
            ("16oz-spicy", "16oz Spicy", 505), ("16oz-dirty", "16oz Dirty", 735),
            ("20oz-regular", "20oz Regular", 585), ("20oz-spicy", "20oz Spicy", 585),
            ("20oz-dirty", "20oz Dirty", 785)
        )),
        product("hot-chocolate", "tea-hot-drinks", "Hot Chocolate", 335, options=variants(
            ("12oz-regular", "12oz Regular", 335), ("12oz-white", "12oz White", 335),
            ("16oz-regular", "16oz Regular", 385), ("16oz-white", "16oz White", 385),
            ("20oz-regular", "20oz Regular", 455), ("20oz-white", "20oz White", 455)
        )),
        product("iced-chai-latte", "tea-hot-drinks", "Iced Chai Latte", 535, options=variants(
            ("16oz", "16oz", 535), ("20oz", "20oz", 605)
        )),
        product("iced-dirty-chai", "tea-hot-drinks", "Iced Dirty Chai", 705, options=variants(
            ("12oz", "12oz", 705), ("16oz", "16oz", 765), ("20oz", "20oz", 805)
        )),
        product("iced-london-fog", "tea-hot-drinks", "Iced London Fog", 495, options=variants(
            ("12oz", "12oz", 495), ("16oz", "16oz", 535), ("20oz", "20oz", 625)
        )),
        product("iced-matcha", "tea-hot-drinks", "Iced Matcha", 540, options=variants(
            ("12oz", "12oz", 540), ("16oz", "16oz", 590), ("20oz", "20oz", 660)
        )),
        product("london-fog", "tea-hot-drinks", "London Fog", 465, options=variants(
            ("12oz", "12oz", 465), ("16oz", "16oz", 505), ("20oz", "20oz", 595)
        )),
        product("matcha", "tea-hot-drinks", "Matcha", 510, options=variants(
            ("12oz", "12oz", 510), ("16oz", "16oz", 565), ("20oz", "20oz", 635)
        )),
        product("steamer", "tea-hot-drinks", "Steamer", 250, options=variants(
            ("12oz", "12oz", 250), ("16oz", "16oz", 350), ("20oz", "20oz", 450)
        )),
        product("tea", "tea-hot-drinks", "Tea", 220, options=variants(
            ("12oz", "12oz", 220), ("16oz", "16oz", 220), ("20oz", "20oz", 220)
        )),
        product("bottled-water", "cold-drinks", "Bottled Water", 125, image="water"),
        product("city-seltzer", "cold-drinks", "City Seltzer", 300, image="water", options=variants(
            ("berry-whip", "Berry Whip", 300), ("citrus", "Citrus", 300),
            ("cool-melon", "Cool Melon", 300), ("orange-cream", "Orange Cream", 300)
        )),
        product("crazy-ds", "cold-drinks", "Crazy D's", 485, image="water", options=variants(
            ("cherry-cola", "Cherry Cola", 485), ("thrilla-vanilla", "Thrilla Vanilla", 485)
        )),
        product("hibiscus-refresher", "cold-drinks", "Hibiscus Refresher", 505, image="water", options=variants(
            ("12oz", "12oz", 505), ("16oz", "16oz", 595), ("20oz", "20oz", 665)
        )),
        product("iced-tea", "cold-drinks", "Iced Tea", 375, image="water", options=variants(
            ("12oz-hibiscus-refresher", "12oz Hibiscus Refresher", 375),
            ("16oz-hibiscus-refresher", "16oz Hibiscus Refresher", 400),
            ("20oz-hibiscus-refresher", "20oz Hibiscus Refresher", 450),
            ("12oz-lemonade", "12oz Lemonade", 375), ("16oz-lemonade", "16oz Lemonade", 400),
            ("20oz-lemonade", "20oz Lemonade", 450), ("12oz-peach-tea", "12oz Peach Tea", 375),
            ("16oz-peach-tea", "16oz Peach Tea", 400), ("20oz-peach-tea", "20oz Peach Tea", 450)
        )),
        product("maple-3", "cold-drinks", "Maple 3", 395, image="water", options=variants(
            ("sparkling", "Sparkling", 395), ("sparkling-lime", "Sparkling Lime", 395),
            ("sparkling-peach", "Sparkling Peach", 395), ("water", "Water", 395)
        )),
        product("cocoa-blueberry-smoothie", "smoothies", "Cocoa + Blueberry Smoothie", 995, image="water"),
        product("glow-smoothie", "smoothies", "Glow Smoothie", 995, image="water"),
        product("green-sunshine-smoothie", "smoothies", "Green Sunshine Smoothie", 995, image="water"),
        product("strawberry-banana-smoothie", "smoothies", "Strawberry Banana Smoothie", 995, image="water"),
        product("buffalo-chickpea-bowl", "meals", "Buffalo Chickpea Bowl", 1295, image="pastry"),
        product("chilli-cucumber-bowl", "meals", "Chilli Cucumber Bowl", 1195, image="pastry"),
        product("spring-veggie-wrap", "meals", "Spring Veggie Wrap", 1150, image="pastry"),
        product("thai-crunch-wrap", "meals", "Thai Crunch Wrap", 1150, image="pastry"),
        product("chia-chocolate-pudding", "snacks-bakery", "Chia Chocolate Pudding", 695, image="pastry"),
        product("harvest-honey-bar", "snacks-bakery", "Harvest Honey Bar (Trail Mix)", 495, image="pastry"),
        product("maple-carrot-bar", "snacks-bakery", "Maple Carrot Bar (Carrot Oatmeal)", 495, image="pastry"),
        product("muffin", "snacks-bakery", "Muffin", 250, image="pastry"),
        product("nourish-bar", "snacks-bakery", "Nourish Bar (Pistachio Date)", 495, image="pastry"),
        product("overnight-oats", "snacks-bakery", "Overnight Oats", 550, image="pastry"),
        product("peanut-butter-protein-balls", "snacks-bakery", "Peanut Butter Protein Balls", 395, image="pastry"),
        product("peanut-butter-protein-cups", "snacks-bakery", "Peanut Butter Protein Cups", 550, image="pastry"),
        product("1883-syrup-1l", "retail", "1883 Syrup 1L", 1895, image="water"),
        product("tgh-hat", "retail", "TGH Hat", 3900, image="pastry"),
        product("tgh-mug", "retail", "TGH Mug", 1695, image="coffee"),
        product("zafiato-beans-340g", "retail", "Zafiato Beans 340g", 1895),
    ),
    # Cafe Pricing.docx contains product variants but no approved modifier groups.
    modifier_groups=(),
)
