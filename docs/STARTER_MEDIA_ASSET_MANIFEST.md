# Starter media asset manifest — Café & Restaurant collection (M3)

Manifest: `backend/app/platform/starter_media.py` (manifest version 1). Art style: `illustrated-placeholder`. Provenance: Original JDS illustration generated in-repo (no third-party or stock imagery).

- **26 shipped** illustrated placeholders (1200 × 1200 WebP, ~463 KB total), packaged via `pyproject.toml` package-data `app.platform = ["starter-media/*/*.webp"]`.
- **44 planned archetypes without art.** They are hidden from the owner picker (`available: false`) and never render as broken images.

These are **clearly-marked illustrated placeholders**, not photographs. The picker labels them “Illustrated placeholder — replace it with your own photo anytime.” For production, replace or supplement them with reviewed, JDS-owned or properly licensed photography (see `docs/STARTER_PRODUCT_MEDIA.md`, *Generation specification*). No scraped, hotlinked, or third-party stock imagery is included.

## Regenerating

```
cd backend && . .venv/bin/activate
python scripts/generate_starter_media.py   # draws with scripts/starter_art.py (Pillow), writes <key>-v1.webp
```

The output is deterministic. Bump the asset `version` in the manifest when artwork changes so cached URLs (`?version=N`) refresh; products keep referencing `starter:<collection>/<key>@<version>`.

## Shipped (selectable)

| Key | Name | Browse category | File | Size |
|---|---|---|---|---|
| `plain-croissant` | Plain croissant | bakery | `plain-croissant-v1.webp` | 17 KB |
| `filled-croissant-danish` | Filled croissant or Danish | bakery | `filled-croissant-danish-v1.webp` | 25 KB |
| `muffin` | Muffin | bakery | `muffin-v1.webp` | 18 KB |
| `scone` | Scone | bakery | `scone-v1.webp` | 16 KB |
| `cookie` | Cookie | bakery | `cookie-v1.webp` | 22 KB |
| `brownie-dessert-square` | Brownie or dessert square | bakery | `brownie-dessert-square-v1.webp` | 16 KB |
| `donut` | Donut | bakery | `donut-v1.webp` | 20 KB |
| `loaf-slice` | Loaf slice | bakery | `loaf-slice-v1.webp` | 18 KB |
| `breakfast-sandwich` | Breakfast sandwich | breakfast | `breakfast-sandwich-v1.webp` | 18 KB |
| `toast` | Toast | breakfast | `toast-v1.webp` | 20 KB |
| `yogurt-granola` | Yogurt and granola | breakfast | `yogurt-granola-v1.webp` | 22 KB |
| `brewed-coffee` | Brewed coffee | coffee | `brewed-coffee-v1.webp` | 12 KB |
| `espresso` | Espresso | coffee | `espresso-v1.webp` | 10 KB |
| `latte` | Latte | coffee | `latte-v1.webp` | 14 KB |
| `cappuccino` | Cappuccino | coffee | `cappuccino-v1.webp` | 15 KB |
| `iced-latte` | Iced latte | coffee | `iced-latte-v1.webp` | 15 KB |
| `iced-coffee` | Iced coffee | coffee | `iced-coffee-v1.webp` | 17 KB |
| `iced-tea` | Iced tea | cold-drinks | `iced-tea-v1.webp` | 18 KB |
| `lemonade-fruit-cooler` | Lemonade or fruit cooler | cold-drinks | `lemonade-fruit-cooler-v1.webp` | 20 KB |
| `smoothie` | Smoothie | cold-drinks | `smoothie-v1.webp` | 17 KB |
| `deli-sandwich` | Deli-style sandwich | sandwiches-wraps | `deli-sandwich-v1.webp` | 16 KB |
| `wrap` | Wrap | sandwiches-wraps | `wrap-v1.webp` | 19 KB |
| `creamy-soup` | Creamy soup | soup-salad | `creamy-soup-v1.webp` | 16 KB |
| `green-salad` | Green salad | soup-salad | `green-salad-v1.webp` | 19 KB |
| `hot-tea` | Hot tea | tea-specialty-drinks | `hot-tea-v1.webp` | 14 KB |
| `hot-chocolate` | Hot chocolate | tea-specialty-drinks | `hot-chocolate-v1.webp` | 20 KB |

## Planned, art still needed (hidden)

| Key | Name | Browse category |
|---|---|---|
| `cinnamon-roll` | Cinnamon roll | bakery |
| `tart` | Tart | bakery |
| `pastry-turnover` | Pastry or turnover | bakery |
| `croissant-breakfast-sandwich` | Croissant breakfast sandwich | breakfast |
| `breakfast-wrap` | Breakfast wrap | breakfast |
| `eggs-breakfast-plate` | Eggs and breakfast plate | breakfast |
| `pancakes` | Pancakes | breakfast |
| `waffles` | Waffles | breakfast |
| `french-toast` | French toast | breakfast |
| `bagel` | Bagel | breakfast |
| `oatmeal-porridge` | Oatmeal or porridge | breakfast |
| `americano` | Americano | coffee |
| `flat-white-cortado` | Flat white or cortado | coffee |
| `mocha` | Mocha | coffee |
| `cold-brew` | Cold brew | coffee |
| `milkshake-blended-drink` | Milkshake or blended drink | cold-drinks |
| `juice` | Juice | cold-drinks |
| `chocolate-cake-slice` | Chocolate cake slice | desserts |
| `light-fruit-cake-slice` | Light or fruit cake slice | desserts |
| `cheesecake` | Cheesecake | desserts |
| `tiramisu` | Tiramisu | desserts |
| `pie-slice` | Pie slice | desserts |
| `ice-cream-gelato` | Ice cream or gelato | desserts |
| `dessert-parfait` | Dessert parfait | desserts |
| `fruit-cup` | Fruit cup | desserts |
| `burger` | Burger | lunch-savoury |
| `hot-dog` | Hot dog | lunch-savoury |
| `quiche` | Quiche | lunch-savoury |
| `pizza-flatbread` | Pizza or flatbread | lunch-savoury |
| `fries-potato-wedges` | Fries or potato wedges | lunch-savoury |
| `savoury-bowl` | Savoury bowl | lunch-savoury |
| `coffee-beans-bag` | Bag of coffee beans | packaged-retail |
| `packaged-snack` | Packaged snack | packaged-retail |
| `bottled-canned-drink` | Bottled or canned drink | packaged-retail |
| `artisan-cafe-sandwich` | Artisan café sandwich | sandwiches-wraps |
| `panini-grilled-sandwich` | Panini or grilled sandwich | sandwiches-wraps |
| `broth-soup` | Broth soup | soup-salad |
| `chowder` | Chowder | soup-salad |
| `chili` | Chili | soup-salad |
| `composed-salad` | Composed salad | soup-salad |
| `grain-bowl-salad` | Grain or bowl salad | soup-salad |
| `chai-latte` | Chai latte | tea-specialty-drinks |
| `matcha-latte` | Matcha latte | tea-specialty-drinks |
| `tea-latte-london-fog` | Tea latte or London Fog | tea-specialty-drinks |

## Harbor & Hearth starter mapping

| Starter product | Starter image |
|---|---|
| `house-drip` | `brewed-coffee` |
| `cafe-latte` | `latte` |
| `cappuccino` | `cappuccino` |
| `iced-latte` | `iced-latte` |
| `butter-croissant` | `plain-croissant` |
| `blueberry-muffin` | `muffin` |
| `chocolate-cookie` | `cookie` |
| `avocado-toast` | `toast` |
| `yogurt-parfait` | `yogurt-granola` |
