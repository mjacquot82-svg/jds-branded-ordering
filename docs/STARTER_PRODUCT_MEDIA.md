# JDS starter product media

JDS starter media is platform-owned, globally readable content. It is separate from merchant media: uploads remain tenant-owned, private to that merchant's owner tools, and authorized through the existing tenant-scoped media endpoints. Starter selection never copies a binary or creates a `media_assets` row.

## Product references

Private uploads use the nullable `Product.media_asset_id` relation, protected by a composite `(organization_id, media_asset_id)` foreign key. Owner writes accept only JDS media references and verify the active asset belongs to the authenticated tenant; arbitrary external URLs are rejected. New platform references use the unambiguous form `starter:<collection>/<asset-key>@<version>`. Public catalog responses resolve either controlled reference to a JDS endpoint.

## V1 manifest and storage

The versioned manifest is `backend/app/platform/starter_media.py`. It defines stable keys, collection, browsing category, tags, dimensions, active state, ordering, neutral alt text, and asset version. Binary storage is a separate platform/static abstraction rooted at `JDS_STARTER_MEDIA_ROOT`; no binaries are included in this change. This is the clean extension point for the future shared library. Platform entries remain separate from `media_assets`, so tenant owners cannot archive, replace, or delete them.

The initial `Café & Restaurant` collection contains 70 planned visual archetypes. Its browsing-only categories are Coffee; Tea & Specialty Drinks; Cold Drinks; Breakfast; Bakery; Sandwiches & Wraps; Lunch & Savoury; Soup & Salad; Desserts; and Packaged & Retail. These categories never create or alter a merchant's catalog categories. Future verticals receive separate collections so their assets do not enter this picker accidentally.

Archetypes intentionally represent product families rather than every menu name. For example, the Latte asset is tagged for caramel, vanilla, maple, hazelnut, and other flavoured lattes, while visually distinct brewed coffee, espresso, iced latte, iced coffee, and cold brew retain separate assets. Tags and aliases may be expanded without changing stable product references.

Only active assets with a supplied binary are selectable. Planned entries without binaries appear as deliberately unavailable cards, never broken images. Retiring an asset makes it unavailable for new assignments but keeps its versioned content resolvable for products that already reference it. Removing a binary requires a migration/replacement plan for existing references.

## Search and suggestions

The owner picker uses deterministic, local token matching against asset key, display name, and tags. Exact name/key matches rank above tag matches. No merchant data is sent to an AI or external service.

## Generation specification

All final V1 binaries should be generated at a canonical 1200 × 1200 WebP size from reviewed source material intentionally owned or licensed for JDS platform use. Use a consistent high-quality product-photography style: one centered subject, safe breathing room, clean neutral unbranded background, no text, logos, trademarks, recognizable packaging, people, or misleading quantities. Images must remain suitable for responsive product-card cropping. Do not scrape or introduce third-party restaurant/stock imagery without explicit licensing review.

## Money input note

Modifier extra-price input accepts ordinary dollar notation such as `.25`, `0.50`, `1`, and `1.5`, then converts exactly to integer cents. Malformed, negative, over-precision, and PostgreSQL-integer-overflow values are rejected next to the relevant field before persistence.
