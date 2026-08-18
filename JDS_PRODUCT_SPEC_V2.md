# JDS Branded Ordering Platform — Product Specification

**Status:** Living product blueprint  
**Reference implementation:** Ladel's / The Guest House  
**V1 focus:** A self-service, branded mobile ordering experience—not a general website builder.

## Vision

Build a multi-tenant SaaS platform for cafés, bakeries, dessert shops, delis, food trucks, quick-service restaurants, and similar businesses. A merchant chooses a professional layout, customizes it to match their brand, connects Clover, previews the finished customer experience, and publishes it without hiring a developer.

> **Build an ordering experience that looks like your business.**

Reuse the proven Ladel's commerce functionality while replacing merchant-specific visual and operational assumptions with safe tenant-controlled configuration.

## Product Principles

- Self-service first; routine launch and customization should not require JDS.
- No coding required.
- Customization is the selling feature; ordering is foundational.
- Templates first, then personalization.
- Persistent live phone preview is central.
- Mobile-first browser/PWA experience.
- V1 is not a full website builder.
- Draft first; preview before publish.
- Design changes are safe and reversible.
- Commerce reliability outranks design freedom.
- One shared platform serves many tenants.
- Avoid extra merchant hardware whenever practical.
- Clover is an integration, not the product identity.
- Merchant branding dominates the customer experience.
- Build for hundreds or thousands of tenants.

## Repository Strategy

Protect the production Ladel's repository. Create a **new SaaS repository cloned from the proven Ladel's codebase**. The SaaS repo can evolve without delaying or destabilizing Ladel's.

Reuse proven ordering, customer, staff, notification, Clover, payment, and security flows. Treat Ladel's as the reference implementation and, where practical, Tenant #1.

## Market and Positioning

Do not brand the product only for coffee shops. Initial targets include cafés, bakeries, ice-cream/dessert shops, juice/smoothie shops, delis, sandwich shops, food trucks, and small quick-service businesses.

Preferred positioning:

> **Build your own branded ordering app — no developer required.**

Supporting ideas: Start with a template. Make it yours. Design it, preview it, publish it. Connect the Clover account you already use. Flat monthly software pricing and unlimited software orders, subject to final commercial terms.

## Multi-Tenant Foundation

Each merchant is a distinct tenant with its own business profile, design, draft/published configuration, menu, orders, customers, staff, Clover connection, payment/webhook evidence, notifications, media, analytics, billing, audit history, and fulfillment preferences.

**Tenant isolation is non-negotiable.** Tenant A must never see or modify Tenant B data through APIs, database queries, webhooks, jobs, notifications, reports, or administration. Explicit automated isolation tests are required.

## Merchant Onboarding

Preferred V1 journey:

1. Create account and basic business profile.
2. Enter Design Studio immediately.
3. Browse and preview templates.
4. Choose a template.
5. Upload logo and imagery.
6. Choose colors, fonts, buttons, and presentation.
7. Arrange supported sections.
8. Configure menu and availability.
9. Configure fulfillment/order-notification preferences.
10. Preview the finished customer experience.
11. Connect Clover before live commerce.
12. Complete readiness checks.
13. Publish.
14. Receive customer URL, QR code, and launch assets.

Minimize barriers to experiencing the builder. Clover and billing may be required closer to publication.

## JDS Design Studio

Design Studio is the centerpiece.

**Desktop layout:** editing controls on the left and a persistent live phone mockup on the right. Changes update the preview immediately.

First-time use should be guided and creative rather than technical. Returning navigation may include Templates, Brand, Homepage, Menu Presentation, Sections, Announcements, Business Information, Fulfillment, Preview, and Publish.

Design work is stored as a draft and can be resumed later. The phone preview should eventually support scrolling, categories, products, modifiers, announcements, cart presentation, and navigation. Preview must never create a real charge.

## Templates and Customization

Templates are professional starting layouts built from one shared component/design system, not separate apps.

Potential launch templates: **Modern, Minimal, Cozy/Rustic, Bold, Bakery, Quick Order.**

Merchants preview before selecting and can switch later without losing menu, orders, customers, Clover, staff, notifications, or operational data.

V1 customization may include:
- Business name and logo
- Primary/accent/background colors
- Curated fonts/font pairs
- Button and card styles
- Hero/product/promotional images
- Welcome/hero text
- Featured products/categories
- Announcement area
- Business description
- Section visibility and ordering
- Pickup information
- Hours/contact/social/footer
- Category ordering
- Product-card presentation
- Image/description visibility
- Sold-out presentation

Do not expose raw CSS/HTML or unrestricted drag-anything-anywhere positioning in V1.

The builder should prevent or warn about poor contrast, unreadable text, inaccessible tap targets, broken layouts, bad image proportions, unsupported files, and excessively long labels.

## Draft, Publish, Revert, and Media

Design Studio edits a **draft** while customers see the last published version.

Publishing should be validated and atomic. At minimum, merchants can restore the last successfully published design. Undo/redo should be supported where practical.

Each tenant gets a reusable media library with validation, optimization, cropping, resizing, reuse, safe deletion, and tenant isolation.

## Customer Ordering Experience

Generalize the proven Ladel's flow.

V1 supports mobile browsing, categories, products, images/descriptions, modifiers, availability/sold-out controls, cart, pickup instructions, checkout, Clover payment, payment confirmation, customer accounts, order history/status, and responsive browser/PWA behavior.

**Order Again** is a strong V1 or immediate post-V1 candidate.

## V1 URL / PWA Strategy

V1 does **not** include a full merchant website builder.

Each merchant receives a hosted branded ordering URL. The browser experience should feel app-like and may support home-screen installation as a PWA.

Possible URL models include tenant subdomains or tenant paths. Custom domains may be future/premium functionality.

## Launch Kit

Publishing should generate:
- Ordering URL
- QR code
- Printable counter card/sign
- Printable window/door sign
- Basic “Order Ahead” graphic
- Social-share asset or instructions

Assets should reflect merchant branding where practical.

## Menu Strategy

Architecture should support local/JDS-managed menus, Clover menu import, and selective Clover synchronization where useful.

V1 should choose the simplest reliable model and must not require merchants to understand Clover inventory APIs.

## Clover Integration

Generalize the proven Clover implementation for tenant-specific OAuth and merchant identity.

Requirements include secure token storage/rotation, environment isolation, Hosted Checkout/payment creation, signed webhooks, reconciliation, duplicate protections, merchant/currency validation, diagnostics, and safe reconnect behavior.

Credentials remain backend-only.

## Fulfillment and Existing Hardware

A core principle is **no additional hardware required whenever practical**.

Merchants may have full Clover setups or only small handheld terminals. Do not assume a dedicated kitchen screen or second tablet.

Before finalizing V1 fulfillment, audit official Clover capabilities by device class and determine supported options such as:
- Existing Clover order workflows
- Device notifications/alerts
- Clover/kitchen printer ticket routing
- Automatic prep-ticket printing
- Sound/visual alerts
- Browser staff dashboard fallback
- Routing to another Clover device when available

Merchants should choose a workflow appropriate to their hardware. Automatic printing must not unnecessarily interrupt active POS use or create confusing receipt behavior.

## Customers, Staff, and Permissions

Customer data is tenant-specific. V1 supports login/profile, order history/status, notification preferences, and Order Again if included.

Roles:
- **Owner:** billing, Clover, Design Studio, publishing, staff, menu, notifications, analytics, settings.
- **Manager:** configurable operational permissions.
- **Staff:** fulfillment-focused access.

Prefer capability-based authorization where practical.

## Notifications and Engagement

Generalize the existing Ladel's notification capability into tenant-aware shared infrastructure.

Require tenant-specific subscribers, opt-in/out, no cross-tenant leakage, merchant-authored messages, safe audience selection, delivery status where practical, scheduling architecture, and subscription-tier enforcement.

Uses include specials, fresh products, new menu items, restocks, holiday hours, promotions, seasonal items, and closures.

Advanced automation, loyalty, segmentation, birthdays, and win-back campaigns are future premium possibilities. Notifications are a natural premium pricing feature.

## Analytics, Pricing, Billing, and JDS Administration

Potential V1 analytics: orders today/by period, platform sales, average order value, popular products, order volume, repeat customers, and basic customer activity.

Current pricing hypothesis:
- **Core/Builder:** roughly C$99–C$150/month.
- **Engagement:** higher tier with push notifications/customer engagement.
- **Pro:** future automation, loyalty, segmentation, advanced analytics.
- Optional one-time **Done For You** setup.

Pricing must account for Clover marketplace revenue share, if applicable, plus platform operating costs.

Billing lifecycle must cover trial, activation, upgrade/downgrade, failed payment, grace period, cancellation, and reactivation without immediately deleting merchant data.

JDS needs a secured platform console for tenants, subscriptions, Clover health, publishing state, errors, usage, notification health, reconciliation, diagnostics, and audit history.

## Security, Privacy, Observability, and Reliability

Build observability for application errors, OAuth/token health, webhooks, payment reconciliation, publishing failures, notification delivery, background jobs, and audit logs.

Require tenant isolation, least privilege, secure authentication, secret management, encryption where appropriate, data export/deletion/retention, customer privacy, notification consent, and applicable launch-market compliance.

Customer ordering should not unnecessarily depend on Design Studio availability. Keep design state separate from commerce state, publish atomically, use idempotent commerce operations, degrade safely, and maintain backups/recovery.

## White-Label Philosophy

The customer-facing experience belongs visually to the merchant. JDS branding should be subtle.

A “Powered by JDS” treatment may exist on some plans and potentially be removable on premium plans. Final policy is a product-owner decision.

## Explicitly Not V1

Do not autonomously expand V1 into:
- Full merchant website builder
- Native iOS/Android apps
- SMS marketing
- Apple/Google Wallet
- Advanced loyalty
- Gift cards
- Delivery logistics
- Enterprise multi-location management
- Advanced CRM
- AI-generated designs
- Unrestricted Wix-style editing
- Arbitrary custom HTML/CSS/JS
- Multiple POS/payment providers
- Full design-version history
- Advanced campaign automation

These are future possibilities, not permission to build them.

## Definition of V1

V1 is launchable when an independent merchant can, without developer assistance:

1. Create an isolated tenant.
2. Enter Design Studio.
3. Preview and choose multiple templates.
4. Upload branding/images.
5. Customize supported visual controls.
6. See changes in a live phone preview.
7. Save/resume a draft.
8. Configure business information and a functional menu.
9. Choose a supported fulfillment workflow.
10. Connect Clover via OAuth.
11. Preview the complete customer experience.
12. Publish to a merchant-specific URL.
13. Receive QR code/launch assets.
14. Have a customer browse, order, and pay from a phone.
15. Receive trustworthy payment confirmation.
16. Deliver the order into a practical merchant workflow without extra hardware whenever possible.
17. Have staff complete the order.
18. Have the customer see order/history.
19. Edit a new draft and republish without affecting commerce data.
20. Operate without routine JDS intervention.

V1 also requires tenant isolation, secure Clover handling, reliable payments/webhooks, role-based merchant administration, basic JDS administration, safe publish/revert, observability, and automated critical-flow tests.

## Decision Log

Current decisions:
- Separate SaaS repo protects Ladel's production.
- Clone/reuse Ladel's rather than rebuild.
- Platform is not coffee-shop-only.
- Self-service design is the core differentiator.
- Templates plus controlled customization, not unrestricted design.
- Design Studio uses controls left/live phone preview right.
- Drafts can be saved and resumed.
- V1 URL opens the ordering app; no full website builder.
- Browser/PWA first; no native app per merchant in V1.
- Publishing creates a Launch Kit.
- Existing hardware first; audit Clover-supported fulfillment paths.
- Notifications are a natural premium feature.
- Pricing remains a hypothesis until validated.

## Standing Success Test

> “I chose a design, made it look like my business, connected Clover, published it myself, and my customers can order from their phones.”

JDS maintains one scalable platform—not a separate custom build for every merchant.
