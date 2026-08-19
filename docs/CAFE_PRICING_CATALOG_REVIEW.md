# Cafe Pricing catalog staging review

Source: Jessie's reviewed `Cafe Pricing.docx`, supplemented only by her email
clarifications that the prices are selling prices and the listed menu is offered
daily except possibly Candy Cane Hot Chocolate.

## Ready to import

The staged catalog is defined in
`backend/app/catalog/cafe_pricing_seed_data.py` and currently contains:

- 8 customer-facing categories
- 51 products
- 110 explicitly priced product variants
- 2 Café Favorites: Drip Coffee and Latte
- 0 modifier groups, because the source document does not define any modifier
  group or option structure

All staged products are intended to be published and default-available. Product
choices explicitly labelled as variants in the document are preserved as priced
variants. No production import has been run.

After approval, the deliberate import entry point is:

```shell
python -m app.catalog.import_cafe_pricing
```

It uses the existing transactional, idempotent catalog upsert and requires the
target `DATABASE_URL`. The ordinary seed command remains unchanged.

## Needs Jessie's Review

Only the following source rows remain unresolved:

| Source row | Price | Question to resolve |
|---|---:|---|
| $1 Coffee Day | $1.00 | Is this a customer-orderable product/promotion, and when is it available? |
| Candy Cane Hot Chocolate | 12oz $3.50; 16oz $4.05; 20oz $4.25 | Jessie identified it as possibly seasonal. Confirm whether it should be unpublished, unavailable, or seasonally scheduled. |
| COFFEE FLIGHT | $16.00 | Confirm customer availability and whether its selections need modifiers. |
| Drip Coffee - Refill | $1.00 | Confirm whether online preorder customers may order a refill and whether it belongs as a Drip Coffee variant or a separate product. |
| EVENING FLIGHT | $12.00 | Confirm whether this event-specific item should be published and when it is available. |
| EVENING LATTE | $5.00 | Confirm whether this event-specific item should be published and when it is available. |
| Free 7th Coffee | $0.00 | This appears to be a loyalty redemption rather than a generally orderable product. Confirm that it should remain excluded from the public catalog. |
| MILK ALTERNATIVE - Coffee Flight | $2.00 | Confirm whether this is a Coffee Flight modifier, and provide the allowed milk options if customers must choose one. |
| Nurses Week Coffee | $0.00 | Confirm whether this expired/event promotion should remain excluded from the public catalog. |
| Protein Powder | $2.50 | Confirm which smoothie products receive this modifier and whether there are selectable powder options. |
| WD40 | $5.35 | The source name is not sufficient to identify the product or its customer-facing category. |

## Classification notes

- `Regular`, `Decaf`, temperature, size, flavour, and packaged-drink choices
  carrying complete prices were modeled as variants, not modifiers.
- The historical approved Guest House catalog explicitly featured Drip Coffee
  and Latte. No other source-backed favorites were carried forward.
- Products not marked featured use the normal safe default (`false`); that does
  not prevent them from appearing in Browse.
- No undocumented milk, syrup, flavour-shot, or food customization choices were
  added.
