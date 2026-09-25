from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


STARTER_REFERENCE_PREFIX = "starter:"
STARTER_MANIFEST_VERSION = 1
CAFE_RESTAURANT_COLLECTION = "cafe-restaurant"


@dataclass(frozen=True)
class StarterMediaAsset:
    key: str
    name: str
    category: str
    tags: tuple[str, ...]
    alt_text: str
    sort_order: int
    collection: str = CAFE_RESTAURANT_COLLECTION
    width: int = 1200
    height: int = 1200
    version: int = 1
    active: bool = True

    @property
    def reference(self) -> str:
        return f"{STARTER_REFERENCE_PREFIX}{self.collection}/{self.key}@{self.version}"

    @property
    def relative_path(self) -> Path:
        return Path(self.collection) / f"{self.key}-v{self.version}.webp"


def _asset(key: str, name: str, category: str, tags: str, order: int) -> StarterMediaAsset:
    return StarterMediaAsset(
        key=key,
        name=name,
        category=category,
        tags=tuple(tags.split()),
        alt_text=f"Generic {name.lower()} product image",
        sort_order=order,
    )


# Versioned V1 manifest. Binary assets are intentionally supplied and reviewed separately.
STARTER_MEDIA_ASSETS = (
    # Coffee (10)
    _asset("brewed-coffee", "Brewed coffee", "coffee", "coffee brewed drip filter black regular decaf dark roast light roast hot drink cafe", 10),
    _asset("espresso", "Espresso", "coffee", "coffee espresso shot doppio ristretto short black hot drink cafe", 20),
    _asset("americano", "Americano", "coffee", "coffee americano long black espresso water hot drink cafe", 30),
    _asset("latte", "Latte", "coffee", "latte vanilla caramel maple hazelnut flavoured coffee espresso milk hot drink cafe", 40),
    _asset("cappuccino", "Cappuccino", "coffee", "cappuccino coffee espresso foam foamed milk oat hot drink cafe", 50),
    _asset("flat-white-cortado", "Flat white or cortado", "coffee", "flat white cortado piccolo coffee espresso milk hot drink cafe", 60),
    _asset("mocha", "Mocha", "coffee", "mocha mochaccino chocolate coffee espresso milk hot drink cafe", 70),
    _asset("iced-latte", "Iced latte", "coffee", "iced latte vanilla caramel maple hazelnut coffee espresso milk cold drink cafe", 80),
    _asset("iced-coffee", "Iced coffee", "coffee", "iced coffee chilled coffee cold drink cafe", 90),
    _asset("cold-brew", "Cold brew", "coffee", "cold brew nitro coffee chilled black cold drink cafe", 100),

    # Tea & specialty drinks (5)
    _asset("hot-tea", "Hot tea", "tea-specialty-drinks", "tea hot herbal black green earl grey peppermint chamomile cup drink cafe", 110),
    _asset("chai-latte", "Chai latte", "tea-specialty-drinks", "chai latte masala spiced tea milk hot drink cafe", 120),
    _asset("matcha-latte", "Matcha latte", "tea-specialty-drinks", "matcha green tea latte milk hot drink cafe", 130),
    _asset("tea-latte-london-fog", "Tea latte or London Fog", "tea-specialty-drinks", "tea latte london fog earl grey bergamot milk hot drink cafe", 140),
    _asset("hot-chocolate", "Hot chocolate", "tea-specialty-drinks", "hot chocolate cocoa milk steamed drink cafe", 150),

    # Cold drinks (5)
    _asset("iced-tea", "Iced tea", "cold-drinks", "iced tea sweet tea peach lemon cold drink cafe", 160),
    _asset("lemonade-fruit-cooler", "Lemonade or fruit cooler", "cold-drinks", "lemonade fruit cooler refresher citrus berry cold drink cafe", 170),
    _asset("smoothie", "Smoothie", "cold-drinks", "smoothie fruit berry mango banana blended cold drink breakfast cafe", 180),
    _asset("milkshake-blended-drink", "Milkshake or blended drink", "cold-drinks", "milkshake frappe frappuccino blended frozen chocolate vanilla cold drink cafe", 190),
    _asset("juice", "Juice", "cold-drinks", "juice orange apple fruit fresh pressed cold drink cafe", 200),

    # Breakfast (11)
    _asset("breakfast-sandwich", "Breakfast sandwich", "breakfast", "breakfast sandwich egg bacon sausage english muffin breakfast bun morning cafe", 220),
    _asset("croissant-breakfast-sandwich", "Croissant breakfast sandwich", "breakfast", "croissant breakfast sandwich egg bacon ham cheese morning cafe", 230),
    _asset("breakfast-wrap", "Breakfast wrap", "breakfast", "breakfast wrap burrito egg bacon sausage morning cafe", 240),
    _asset("eggs-breakfast-plate", "Eggs and breakfast plate", "breakfast", "eggs breakfast plate bacon sausage potatoes toast morning brunch cafe", 250),
    _asset("pancakes", "Pancakes", "breakfast", "pancakes hotcakes flapjacks syrup breakfast brunch morning", 260),
    _asset("waffles", "Waffles", "breakfast", "waffles syrup breakfast brunch morning", 270),
    _asset("french-toast", "French toast", "breakfast", "french toast bread syrup breakfast brunch morning", 280),
    _asset("bagel", "Bagel", "breakfast", "bagel cream cheese breakfast bread morning cafe", 290),
    _asset("toast", "Toast", "breakfast", "toast bread jam avocado breakfast morning cafe", 300),
    _asset("yogurt-granola", "Yogurt and granola", "breakfast", "yogurt granola parfait fruit breakfast bowl morning healthy", 305),
    _asset("oatmeal-porridge", "Oatmeal or porridge", "breakfast", "oatmeal porridge oats breakfast bowl cereal morning healthy", 310),

    # Bakery (11)
    _asset("plain-croissant", "Plain croissant", "bakery", "croissant plain butter flaky pastry bakery breakfast cafe", 320),
    _asset("filled-croissant-danish", "Filled croissant or Danish", "bakery", "filled flavoured croissant danish chocolate almond fruit cheese pastry bakery cafe", 330),
    _asset("muffin", "Muffin", "bakery", "muffin blueberry chocolate bran banana bakery pastry breakfast cafe", 340),
    _asset("scone", "Scone", "bakery", "scone biscuit blueberry cranberry cheese bakery pastry cafe", 350),
    _asset("cookie", "Cookie", "bakery", "cookie chocolate chip oatmeal shortbread sweet bakery cafe", 360),
    _asset("brownie-dessert-square", "Brownie or dessert square", "bakery", "brownie dessert square blondie nanaimo bar chocolate sweet bakery cafe", 370),
    _asset("donut", "Donut", "bakery", "donut doughnut glazed filled ring sweet bakery cafe", 380),
    _asset("cinnamon-roll", "Cinnamon roll", "bakery", "cinnamon roll bun sticky bun swirl sweet bakery cafe", 390),
    _asset("loaf-slice", "Loaf slice", "bakery", "loaf slice banana bread lemon loaf pound cake bakery cafe", 400),
    _asset("tart", "Tart", "bakery", "tart fruit lemon butter pastry dessert sweet bakery cafe", 410),
    _asset("pastry-turnover", "Pastry or turnover", "bakery", "pastry turnover hand pie apple fruit filled flaky bakery cafe", 420),

    # Sandwiches & wraps (4)
    _asset("deli-sandwich", "Deli-style sandwich", "sandwiches-wraps", "sandwich blt club turkey ham deli bacon lettuce tomato lunch cafe", 430),
    _asset("artisan-cafe-sandwich", "Artisan café sandwich", "sandwiches-wraps", "artisan cafe sandwich focaccia baguette ciabatta lunch", 440),
    _asset("panini-grilled-sandwich", "Panini or grilled sandwich", "sandwiches-wraps", "panini grilled sandwich pressed toastie lunch cafe", 450),
    _asset("wrap", "Wrap", "sandwiches-wraps", "wrap chicken caesar veggie tortilla sandwich lunch cafe", 460),

    # Lunch & savoury (6)
    _asset("burger", "Burger", "lunch-savoury", "burger hamburger cheeseburger veggie burger lunch restaurant", 470),
    _asset("hot-dog", "Hot dog", "lunch-savoury", "hot dog sausage frankfurter bun lunch restaurant", 480),
    _asset("quiche", "Quiche", "lunch-savoury", "quiche egg tart savoury pie lunch brunch cafe", 490),
    _asset("pizza-flatbread", "Pizza or flatbread", "lunch-savoury", "pizza flatbread slice savoury lunch restaurant cafe", 500),
    _asset("fries-potato-wedges", "Fries or potato wedges", "lunch-savoury", "fries french fries chips potato wedges side lunch restaurant", 510),
    _asset("savoury-bowl", "Savoury bowl", "lunch-savoury", "bowl rice noodle grain protein vegetables lunch meal restaurant", 520),

    # Soup & salad (7)
    _asset("broth-soup", "Broth soup", "soup-salad", "soup broth chicken noodle vegetable clear bowl lunch cafe", 530),
    _asset("creamy-soup", "Creamy soup", "soup-salad", "soup creamy tomato squash mushroom bisque bowl lunch cafe", 540),
    _asset("chowder", "Chowder", "soup-salad", "chowder creamy corn seafood potato soup bowl lunch", 550),
    _asset("chili", "Chili", "soup-salad", "chili chilli stew beans beef vegetarian bowl lunch", 560),
    _asset("green-salad", "Green salad", "soup-salad", "green garden house side salad lettuce vegetables healthy lunch", 570),
    _asset("composed-salad", "Composed salad", "soup-salad", "caesar cobb greek chicken salad vegetables lunch restaurant", 580),
    _asset("grain-bowl-salad", "Grain or bowl salad", "soup-salad", "grain quinoa couscous rice bowl salad vegetables healthy lunch", 590),

    # Desserts (8)
    _asset("chocolate-cake-slice", "Chocolate cake slice", "desserts", "chocolate cake slice layer dessert sweet cafe", 600),
    _asset("light-fruit-cake-slice", "Light or fruit cake slice", "desserts", "vanilla white lemon fruit cake slice layer dessert sweet cafe", 610),
    _asset("cheesecake", "Cheesecake", "desserts", "cheesecake slice baked dessert sweet cafe", 620),
    _asset("tiramisu", "Tiramisu", "desserts", "tiramisu coffee mascarpone layered dessert sweet cafe", 630),
    _asset("pie-slice", "Pie slice", "desserts", "pie slice apple fruit cream dessert sweet cafe", 640),
    _asset("ice-cream-gelato", "Ice cream or gelato", "desserts", "ice cream gelato scoop frozen dessert sweet cafe", 650),
    _asset("dessert-parfait", "Dessert parfait", "desserts", "parfait layered cream pudding dessert sweet cafe", 660),
    _asset("fruit-cup", "Fruit cup", "desserts", "fruit cup bowl fresh mixed healthy dessert snack cafe", 670),

    # Packaged & retail (3)
    _asset("coffee-beans-bag", "Bag of coffee beans", "packaged-retail", "coffee beans bag packaged retail whole bean ground coffee unbranded cafe", 680),
    _asset("packaged-snack", "Packaged snack", "packaged-retail", "packaged snack chips granola bar crackers retail unbranded cafe", 690),
    _asset("bottled-canned-drink", "Bottled or canned drink", "packaged-retail", "bottled canned beverage water soda juice cold drink retail unbranded cafe", 700),
)

STARTER_MEDIA_BY_REFERENCE = {asset.reference: asset for asset in STARTER_MEDIA_ASSETS}


def starter_media_root() -> Path:
    configured = os.getenv("JDS_STARTER_MEDIA_ROOT")
    return Path(configured).resolve() if configured else (Path(__file__).parent / "starter-media").resolve()


def starter_asset(reference: str) -> StarterMediaAsset | None:
    return STARTER_MEDIA_BY_REFERENCE.get(reference)


def starter_asset_path(asset: StarterMediaAsset) -> Path:
    root = starter_media_root()
    candidate = (root / asset.relative_path).resolve()
    if root not in candidate.parents:
        raise ValueError("Invalid starter media path.")
    return candidate


def starter_asset_available(asset: StarterMediaAsset) -> bool:
    return asset.active and starter_asset_path(asset).is_file()


def starter_public_url(reference: str) -> str:
    asset = starter_asset(reference)
    return f"/api/v1/storefront/starter-media/{asset.collection}/{asset.key}?version={asset.version}" if asset else reference


def starter_reference(collection: str, key: str, version: int) -> str:
    return f"{STARTER_REFERENCE_PREFIX}{collection}/{key}@{version}"


def product_image_source(media_asset_id: object, image_reference: str | None) -> str:
    """Distinguish merchant upload, platform starter, legacy seed token, or no image."""
    if media_asset_id:
        return "upload"
    reference = (image_reference or "").strip()
    if not reference:
        return "none"
    return "starter" if reference.startswith(STARTER_REFERENCE_PREFIX) else "legacy"
