# JDS Branded Ordering — Tenant Architecture Audit

**Audited baseline:** `057039cf7d34c31044535b88d076b5d9acb43423`
**Baseline commit:** `feat: import proven Ladel's application baseline`
**Audit mode:** Read-only. No application changes were made as part of this audit.

## 1. Executive architecture recommendation

Evolve the imported Ladel's application by adding tenant ownership to the proven domain model, not by creating a parallel SaaS implementation. The existing `organizations` table should be the canonical tenant registry, with `Organization.id`—an internal, immutable UUID—as the canonical tenant identifier. Human-readable slugs, hostnames, Clover merchant IDs, authenticated memberships, and public routes are tenant-resolution inputs; none should replace the internal organization ID.

The central invariant should be:

> Every tenant-owned aggregate has an explicit `organization_id`, and every read, write, authorization decision, asynchronous job, cache key, external-provider lookup, and audit event executes within one verified tenant context.

Adopt an expand/backfill/verify/contract migration sequence. Preserve Ladel's as the first reference tenant, initially resolve legacy-compatible requests to that tenant, and convert one proven domain boundary at a time. Do not attempt a big-bang rewrite and do not remove working Ladel's behavior during the isolation work.

The recommended sequence is:

1. Establish tenant identity and a compatibility resolver.
2. Add ownership to the catalog and availability spine.
3. Add ownership to orders and fulfillment.
4. Introduce explicit tenant memberships and authorization.
5. Make request resolution surface-specific.
6. Replace singleton Clover configuration with tenant installations.
7. Tenant-scope notifications, loyalty, media, and caches.
8. Resolve storefronts by hostname.
9. Add tenant design configuration and atomic publishing.

The first implementation milestone should be deliberately narrow: add organization ownership to categories, products, modifier groups, and business settings; backfill the Ladel's tenant; introduce an immutable `TenantContext`; and scope only catalog/availability repositories while preserving the existing external API and UI behavior.

## 2. Canonical tenant identity model

### Canonical identity

Use the existing `organizations` model as the tenant/business registry:

- `organizations.id`: canonical internal tenant ID; UUID; immutable; used by foreign keys.
- `organizations.slug`: human-readable routing identifier; unique platform-wide initially, but mutable with controlled redirects.
- Organization status/lifecycle: active, suspended, onboarding, or archived as the product matures.
- Hostnames/custom domains: separate verified mapping records, not overloaded into the organization row or slug.
- External merchant identifiers: provider installation identifiers, never tenant identity.

Do not overload any of the following as the canonical tenant identity:

- Clover `merchant_id`: provider-specific, environment-specific, and potentially reconnected.
- A staff or owner user ID: one identity may belong to multiple organizations.
- Customer identity: customers can interact with multiple merchants.
- Hostname or slug: routing aliases may change.
- Environment variables such as `JDS_ORGANIZATION_SLUG`: deployment configuration is not row ownership.
- Business settings singleton ID `1`: an implementation artifact, not identity.
- Order number, catalog slug, email, domain, or location ID.

### Tenant context

Create an immutable request-scoped `TenantContext`, constructed only by trusted boundary resolvers. It should contain at least:

- `organization_id`
- canonical organization slug
- resolution source (hostname, membership, webhook installation, job payload, compatibility default)
- authenticated principal, when present
- membership and effective permissions, when applicable
- correlation/request ID

Repositories and services should receive `TenantContext` or a narrow tenant-scoped unit of work, rather than accepting arbitrary raw tenant IDs from route parameters. Raw user input must never directly become repository tenant scope.

### Resolution by surface

| Surface | Tenant-resolution source | Authorization rule |
|---|---|---|
| Public storefront | Verified request hostname mapped to organization; V1 compatibility may fall back to the Ladel's tenant only on the known legacy host | Organization must be storefront-active; no caller-selected tenant ID |
| Customer account | Storefront host plus authenticated global customer identity and tenant-specific customer relationship | Customer may see only resources belonging to resolved tenant and their identity |
| Owner/admin portal | Authenticated identity plus explicitly selected active organization membership | Membership role/permissions must authorize each action |
| Staff portal | Authenticated staff identity/session plus active organization membership | Staff membership and permission scope must match resolved organization |
| API request | Trusted host resolution for public APIs; authenticated membership for management APIs | Reject conflicting host, route, token, or membership tenant claims |
| Clover OAuth callback | One-time signed/state record containing initiating organization, membership, environment, nonce, and expiry | Initiator must still have installation permission; state is single-use |
| Clover webhook | Verify signature/provider authenticity, then map environment plus merchant ID to exactly one active installation and organization | Resolve tenant before any order or ledger lookup |
| Background job | Persisted organization ID in job payload, validated when job begins | Job-owned objects must all match the job tenant |

## 3. Full table/model tenancy classification

The imported schema contains approximately 35 persistent tables. The classification below preserves global identity where appropriate while making business data explicitly tenant-owned.

### A. Platform-global

| Model/table | Rationale and required treatment |
|---|---|
| `organizations` | Canonical tenant registry. The row represents the tenant and therefore is platform-managed rather than tenant-owned. |
| `jds_applications` | Platform application/OAuth client registry. Keep global; tenant installations reference applications where needed. |
| `jds_users` | Global human identity. A person can participate in multiple organizations. |
| `external_identities` | Global mapping from identity providers to `jds_users`; never use as tenant membership. |
| Authentication roles/permissions definitions | Permission vocabulary is platform-global. Tenant-specific grants belong on memberships or membership-role associations. |
| Role/permission mapping tables | Global when defining role templates; tenant-specific overrides, if later supported, require explicit ownership. |
| Rate-limit buckets | May be platform-global operational state, but keys must include tenant where limits are tenant-specific. |

### B. Tenant-owned

| Model/table | Current ownership/path | Required tenant boundary |
|---|---|---|
| Organization memberships | Already relate users and organizations | Preserve explicit organization FK; authorize through active membership, not inferred user role |
| Sessions | Currently identity/session oriented | Bind management and tenant customer sessions to resolved organization or make tenant scope explicit in session context |
| Invitations | Membership onboarding | Require organization FK and tenant-aware invitation lookup/acceptance |
| Business settings | Singleton behavior (`id = 1`) | Add required `organization_id`; one settings row per organization; unique on organization |
| Business hours | Global/single-business | Add organization ownership, or parent through tenant-owned settings with direct scope available for safe querying |
| Business closures | Global/single-business | Add organization ownership and tenant-aware date indexes |
| Categories | Global catalog | Add organization FK; category slug uniqueness becomes `(organization_id, slug)` |
| Products | Global catalog | Add organization FK; product slug/external keys become tenant-aware |
| Product/category associations | Inherit from global catalog | Ensure both sides belong to the same organization; avoid cross-tenant join rows |
| Modifier groups | Global catalog | Add organization FK; key/name uniqueness becomes tenant-aware |
| Modifier options | Parent-owned | Inherit tenant through modifier group, with cross-tenant FK protections where practical |
| Product modifier assignments | Join table | Both product and modifier group must share organization |
| Product variants/options | Parent-owned | Inherit product tenant; tenant-aware external identifiers where queried directly |
| Availability/scheduling records | Single-business | Add organization ownership or enforce a safe FK path to tenant-owned catalog/settings |
| Orders | Global order repository behavior | Add organization FK at aggregate root; all lookup/idempotency/state operations require tenant |
| Order items | Parent-owned | Inherit from order; product references must belong to the same tenant or be immutable snapshots |
| Order item modifiers | Parent-owned | Inherit from order item; preserve purchase snapshots and prevent cross-tenant references |
| Fulfillment/kitchen state | Order-owned | Scope dashboards, transitions, queues, and counts by organization |
| Clover installations | Singleton environment configuration | One active installation per organization/provider environment as product policy permits |
| Clover payment/webhook event ledger | Globally queried | Add organization and installation ownership; dedupe constraints include provider/environment/merchant context |
| Notification preferences | Currently globally unique by subscriber/user | Tenant-own delivery preferences where merchant communications differ; global channel consent may be modeled separately |
| Push subscriptions/subscribers | Current queries can select all subscribers | Associate subscriptions with global identity/device plus explicit tenant subscriptions; never broadcast globally by default |
| Announcements | Already partly organization-scoped | Preserve direct organization FK; publish and query within tenant |
| Notification delivery attempts | Operational record | Carry organization and source notification/announcement relationship |
| Loyalty programs | Partly organization-scoped | Require organization FK and tenant-scoped queries |
| Loyalty product/config records | Current product assumptions can be global | Add organization ownership and cross-tenant FK validation |
| Loyalty events/balances | Customer/program-owned | Scope by organization and customer relationship; tenant-aware idempotency |
| Audit events for tenant actions | Mixed/global | Carry organization ID for every tenant action; platform actions may have null tenant plus platform scope |

### C. Tenant-scoped but possibly shared/reference

| Model/concept | Recommendation |
|---|---|
| Permission definitions | Keep vocabulary global; grants and enforcement are membership/tenant-scoped. |
| Catalog media binaries | Blob deduplication may be global internally, but every logical media record, access policy, and URL binding must be tenant-scoped. |
| Product snapshots in orders | Snapshot content belongs to the order tenant even if copied from catalog reference data. |
| Tax/currency definitions | ISO/reference definitions may be global; configured rates, applicability, and display are tenant operational settings. |
| Notification channel metadata | Provider/channel definitions can be global; subscriptions, consent, templates, and sends are tenant-scoped. |
| Design templates/defaults | Platform-curated templates can be global; applied configuration and tenant assets are tenant-owned. |

### D. Requires architectural decision

| Area | Decision required |
|---|---|
| `staff_pin_credentials` | Should attach to a membership—or uniquely to `(organization_id, user_id)`—rather than a global user. Decide whether one PIN may be reused across organizations. |
| Customer profile | Split global identity/contact facts from tenant-owned merchant relationship, preferences, notes, loyalty, and order history. Define which fields the platform vs merchant controls. |
| Customer membership terminology | A customer relationship is not workforce membership. Choose a separate `tenant_customers`/`organization_customers` model. |
| Clover webhook secret scope | Confirm whether provider/app environment supplies a global app secret or per-installation secret. Model actual provider semantics without sharing merchant tokens. |
| Multi-location tenants | The product currently frames organization/business tenancy. Decide whether locations become children now or later; do not use location as tenant. |
| Tax policy | Decide whether V1 is Canada-only or supports tenant jurisdiction configuration immediately. |

### Constraints and indexes that must become tenant-aware

The following current/global patterns are dangerous in a multi-tenant schema:

- Category slug uniqueness must become `(organization_id, slug)`.
- Product slug, SKU, public key, or provider reference uniqueness must be tenant-aware unless an external provider explicitly guarantees global uniqueness.
- Modifier group key/name uniqueness must become tenant-aware.
- The partial unique index enforcing one lunch special is currently global; it must enforce the intended rule per organization, such as one active lunch-special product per tenant.
- Order idempotency keys must be unique within tenant and channel/provider context, not globally inferred.
- Notification preference uniqueness must include organization when preferences are merchant-specific.
- Business settings must be uniquely keyed by organization instead of singleton ID `1`.
- Provider event deduplication must include provider, environment, merchant/installation, and event identifier.
- Membership uniqueness should be `(organization_id, user_id)` or another explicit membership key.

Every tenant-owned table needs an index beginning with `organization_id` for its common access path. Composite indexes should mirror actual predicates—for example `(organization_id, status, created_at)`, `(organization_id, slug)`, and `(organization_id, fulfillment_date, status)`.

## 4. Repository and service risk inventory

### Catalog repository

The current `CatalogRepository` is built around one global catalog:

- “Get all” category/product/modifier queries have no tenant predicate.
- Slug/key lookups assume global uniqueness.
- Write and reorder operations can affect any record by identifier.
- `clear_lunch_special` is global and can clear another merchant's special.
- The advisory lock used for catalog mutations is global rather than tenant-keyed, unnecessarily coupling tenants and potentially masking missing scope.

Required change: construct a tenant-scoped repository/unit of work and require the tenant predicate in every root query and mutation. Validate that associated categories, products, and modifier groups share the same tenant.

### Availability and business settings

The availability service assumes singleton `BusinessSettings(id=1)` and global hours/closures. This is a direct cross-tenant risk: one merchant's hours, cutoff, fulfillment configuration, or closure could control all storefronts.

Required change: settings, hours, closures, and availability queries must resolve through tenant context. Cache keys must include organization ID and configuration/version identity.

### Order repository and fulfillment

The current order repository exposes global active/history/get/transition/dashboard/idempotency patterns. Reusing these unchanged would allow enumeration or mutation across tenants, especially through opaque order IDs supplied by callers.

Required change:

- Include tenant in every order lookup, list, state transition, fulfillment queue, aggregate, and idempotency operation.
- Never fetch globally by order ID and authorize afterward.
- Tenant-scope kitchen dashboards and status event streams.
- Ensure product/modifier references match order tenant at creation time.
- Persist tenant in jobs, notifications, and reconciliation work spawned from an order.

### Customer repository

The current customer repository is principally user-oriented and does not distinguish global identity from merchant relationship. Customer “get all,” profile, order history, preferences, and loyalty can leak across merchants if keyed only by user.

Required change: retain a global identity but introduce a tenant customer relationship. Query orders and merchant-owned customer data using both tenant and user/customer relationship.

### Authentication services

The imported code uses environment-selected `JDS_ORGANIZATION_SLUG` and other single-business assumptions. This is acceptable only as an explicitly temporary Ladel's compatibility resolver; it cannot become the SaaS tenancy mechanism.

Required change: authenticate globally, then authorize through an explicit organization membership or tenant customer relationship. The server, not the browser, derives effective tenant scope.

### Loyalty

Loyalty is partially organization-scoped but includes globally assumed products and organization inference from memberships. Inference is unsafe for a user with multiple memberships.

Required change: require tenant context, make program/product/event/balance ownership explicit, and prevent program or order references from crossing tenants.

### Notifications

This is one of the highest-risk areas:

- Announcements are partly organization-scoped.
- Subscribers and preferences are not consistently scoped.
- Notification queue selection can select all subscribers.
- Activity/history queries are global.
- Timezone and wording are globally configured.

Required change: every audience query begins with organization ownership; tenant preference and consent are explicit; templates/settings/timezone come from tenant context; delivery attempts retain tenant; no default “all subscribers” repository API exists without an explicit platform-only capability.

### Clover services

Clover currently depends on singleton environment configuration and merchant assumptions. Tokens, merchant ID, webhook handling, Hosted Checkout settings, reconciliation, callback state, and diagnostics need installation-level ownership.

Required change: split platform Clover application/environment configuration from tenant Clover installation data. Resolve and lock one installation before all payment operations.

### Frontend state and services

The frontend imports a single branded application and contains module-level caches, unscoped local-storage keys, static PWA metadata, hard-coded business copy/assets, and service clients that assume one business.

Required change later:

- Establish a boot-time tenant descriptor derived from the server/host.
- Include tenant identity/version in all query/cache keys.
- Namespace cart, authentication-adjacent state, recent orders, and preferences by tenant.
- Clear or reject state when the resolved tenant changes.
- Generate or serve tenant-specific manifests/icons rather than mutating one static manifest at runtime without cache isolation.

### Repository API design recommendation

Avoid threading raw tenant IDs through dozens of method parameters. Prefer one of:

- A tenant-scoped unit of work that creates repositories bound to an immutable `TenantContext`.
- Repository constructors/factories requiring `TenantContext`.
- Database session helpers that expose explicit scoped query builders while still requiring repository-level predicates.

Do not rely solely on implicit global context variables. Database row-level security can be defense-in-depth later, but application predicates and authorization remain mandatory.

## 5. API tenant-resolution map

### Public tenant storefront APIs

Includes public catalog, product detail, availability, business hours/closures, announcements, storefront configuration, checkout creation, and public order confirmation/status access.

Resolution: verified hostname mapping. During migration, only the known Ladel's host may use a compatibility default. Route slugs may be used for canonical links or path-based fallback, but conflicting host and path tenants must be rejected.

Risks if unchanged:

- Global catalog and availability responses can expose another tenant.
- Order status by opaque ID can reveal another tenant.
- Checkout can combine Tenant A cart data with Tenant B configuration.
- Shared caches can return another storefront's content.

### Authenticated customer APIs

Includes customer profile, tenant order history, loyalty, notification preferences, saved information, and authenticated checkout.

Resolution: storefront hostname plus authenticated global identity. Authorization requires a tenant customer relationship where relevant; order queries require both tenant and customer identity.

Risks if unchanged: globally keyed user queries can combine profiles, history, loyalty, or preferences across merchants.

### Owner/admin APIs

Includes catalog maintenance, availability, settings, staff, reporting, announcements, loyalty, Clover installation/diagnostics, design configuration, and publishing.

Resolution: authenticated user plus active selected organization membership. If organization appears in a route, it must equal the authorized selected membership context. Never trust a body-supplied organization ID.

Risks if unchanged: every global “get all,” record-by-ID update, catalog reorder, settings singleton, subscriber audience, and Clover diagnostic endpoint can cross tenant boundaries.

### Staff APIs

Includes kitchen/fulfillment queues, order transitions, staff authentication/PIN, customer lookup required for service, and operational dashboards.

Resolution: tenant-bound staff session/membership, normally established from the staff portal host or an explicit authorized business selection. Every transition must fetch `(organization_id, order_id)` together.

Risks if unchanged: global dashboards and transitions expose or mutate other merchants' orders.

### Clover callbacks and webhooks

OAuth callback resolution: single-use state record containing organization, initiating membership, app/environment, nonce, return target, and expiry. Validate callback and membership again before persisting installation.

Webhook resolution: authenticate webhook first, then map `(provider, environment, merchant_id)` to exactly one active installation and tenant before looking up an order, checkout session, or payment event.

Risks if unchanged: singleton merchant configuration and global order lookup can apply Tenant A payment events to Tenant B orders.

### Internal/system APIs

Includes health endpoints, platform administration, scheduled jobs, delivery workers, and diagnostics.

Resolution: health may be platform-global and must expose no tenant data. Tenant jobs carry persisted organization scope. Platform administration uses a distinct platform role/capability and explicit audited tenant selection.

## 6. Authentication and membership model

### Identity layers

Use four distinct concepts:

1. **Global identity (`jds_users`)**: the person known to JDS/Supabase or another identity provider.
2. **Workforce membership**: the user's owner/admin/staff relationship to one organization, with status and permissions.
3. **Tenant customer relationship**: the merchant-specific customer record linked to global identity when available; supports guest-to-account linking without pretending customers are staff members.
4. **Platform/JDS administration**: a separately granted platform capability, not an organization owner role.

### Owners and staff

- One owner can have memberships in multiple organizations.
- One staff identity can belong to one or multiple organizations.
- Roles/permissions are evaluated per membership.
- Staff PIN credentials should be attached to a membership or uniquely keyed by organization and user.
- Sessions used by management surfaces should record the selected organization and membership version/status.
- Changing organization should issue/refresh context rather than accepting arbitrary tenant IDs in later calls.
- Suspended memberships must invalidate or fail authorization even if a token remains cryptographically valid.

### Customers

- Customer identity and tenant membership are not the same concept.
- A single global customer can interact with multiple merchants.
- Merchant-specific profile fields, notes, loyalty, communication choices, and history belong to the tenant customer relationship.
- Global identity fields should be limited to platform-owned authentication/contact facts with clear ownership and consent.
- Guest checkout should still persist organization ownership and use tenant-scoped lookup/linking.
- Carts and recent-order access must be namespaced by tenant.

### Token/session claims

Tokens may include a selected organization and membership identifier for efficiency, but the server must verify current membership/status for privileged actions. Claims should not grant access to all organizations associated with a user. Platform administrators need explicit platform claims and audited tenant impersonation/selection behavior.

### Supabase/external identity

Supabase identity mapping should terminate at global `jds_users`/`external_identities`. Organization authorization belongs in the application database. Do not encode the entire evolving tenant permission model solely in external-provider metadata.

## 7. Clover tenant-isolation design

### Data model

Separate Clover concerns into:

- **Clover application/environment configuration (platform-global):** client/app identity, environment, callback configuration, and any provider-defined app-level verification secret.
- **Clover installation (tenant-owned):** organization, environment, merchant ID, encrypted token material/reference, scopes, installation status, timestamps, diagnostic state, and configuration.
- **Payment/checkout records (tenant-owned):** organization and installation IDs alongside order and provider identifiers.
- **Webhook/payment event ledger (tenant-owned):** organization, installation, merchant ID, environment, event ID/type, verification result, processing state, and idempotency key.

At minimum, active installation uniqueness should prevent an environment/merchant pair from mapping to multiple organizations. Product policy should decide whether an organization may have multiple Clover installations/locations.

### OAuth

1. An authenticated membership authorized to manage integrations initiates OAuth for a specific organization.
2. Server persists or signs a short-lived, single-use state containing organization ID, membership ID, app/environment, nonce, expiry, and safe return target.
3. Callback validates signature/state, expiry, nonce, app/environment, and current membership permission.
4. The returned merchant ID is checked for an existing installation mapping before tokens are stored.
5. Token material is encrypted or stored in an approved secret facility; logs and diagnostics never expose values.
6. Installation activation is transactional and audited.

### Hosted Checkout and order creation

- The checkout request starts from a tenant-scoped order/cart.
- Resolve that tenant's active installation and page configuration.
- Persist organization, installation, order, checkout/session, currency, and expected amount together.
- Do not select installation from a global environment merchant ID.
- Reconciliation must verify that order, checkout, event, merchant, and installation all resolve to the same organization.

### Webhooks

1. Verify provider authenticity/signature according to Clover's actual app/environment semantics.
2. Extract merchant/environment identifiers without looking up an order globally.
3. Resolve exactly one active Clover installation and organization.
4. Persist/dedupe the event within that installation scope.
5. Find checkout/order using organization plus provider references.
6. Assert organization equality among installation, ledger, checkout, and order before mutation.
7. Process state transition idempotently and record an audit trail.
8. Quarantine unmatched or conflicting events; never fall back to another tenant or a global order search.

### Singleton configuration to replace

- Environment-level merchant selection.
- Global merchant/token getters.
- Global Hosted Checkout page/config selection.
- Global webhook-to-order lookup.
- Global payment event ledger queries/dedupe.
- Global reconciliation and merchant diagnostics.
- Callback state lacking an initiating organization.

## 8. Public storefront hostname/routing recommendation

### Recommendation for V1

Use merchant subdomains for hosted storefronts:

`merchant-slug.jdsstudio.ca`

Use a separate stable origin for owner/platform administration. Support custom domains later through the same verified hostname mapping model. A path form such as `order.jdsstudio.ca/merchant-slug` can exist as a redirect or operational fallback, but should not be the canonical V1 storefront architecture.

### Comparison

| Concern | Subdomain tenancy | Path tenancy |
|---|---|---|
| Routing | Requires host resolver and wildcard routing | Simpler single-host router, but tenant prefix must propagate everywhere |
| SSL/DNS | Requires wildcard DNS/certificate and host verification | One hostname/certificate |
| Browser isolation | Stronger origin separation for cookies, storage, service workers, and caches | Shared origin increases risk of storage/service-worker/cache collisions |
| PWA | Natural tenant origin and manifest scope | More careful service-worker scope and manifest routing required |
| SEO/share links | Merchant-branded canonical URL | Platform-first URL with merchant path |
| Customer sessions | Can use host-only tenant sessions; global SSO requires intentional flow | Easier shared cookies, but greater accidental cross-tenant session coupling |
| Caching/CDN | Host is a clear cache dimension | Every cache key/path rule must preserve tenant prefix |
| Custom domains | Natural extension of hostname mapping | Requires changing the fundamental resolution model later |
| Deployment | Wildcard configuration is more operational work | Simplest initial deployment |
| Tenant isolation | Better defense through origin boundaries | Must compensate entirely in application/storage/cache design |

The product specification's branded storefront direction, PWA requirements, future custom domains, and isolation goals justify the modest V1 DNS/SSL complexity of subdomains.

### Required safeguards

- Canonical hostname mapping table with verification and status.
- Reject unknown hosts; do not silently serve a default tenant except a narrowly controlled legacy compatibility host.
- Include hostname/organization in CDN and application cache keys.
- Host-only customer/storefront cookies by default.
- Tenant-scoped service worker, manifest, icons, theme, and offline caches.
- Canonical URLs and redirects when slugs/domains change.

## 9. Design Studio data-boundary recommendation

Do not mix design state with the commerce domain. The storefront renderer may combine published design configuration with live commerce data, but design snapshots must never contain authoritative products, prices, availability, taxes, orders, inventory, payment settings, or fulfillment state.

### A. Commerce/domain data

- Categories and products
- Variants and modifier groups/options
- Prices, tax behavior, currency
- Product/category availability and scheduling
- Carts, customers, orders, order items, payment state
- Loyalty rules/balances tied to commerce

### B. Design/presentation data

- Logo and brand marks
- Display business name/tagline
- Color tokens and surfaces
- Typography/font choices
- Hero imagery and layout
- Category presentation/layout
- Product-card presentation
- Button shape/style tokens
- Navigation style and visible sections
- Homepage section composition/order
- Announcement visual treatment
- Footer/social presentation
- PWA icon set, theme color, background color, and display metadata
- Optional decorative imagery and design-template selection

### C. Operational settings

- Legal business name and contact information
- Business hours and closures
- Pickup/delivery modes and instructions
- Scheduling windows, lead time, cutoffs, capacity
- Timezone, currency, tax policy
- Notification sender/reply settings and operational wording
- Clover installation and payment settings
- Staff workflow and order-state configuration

### D. Platform settings

- JDS application/environment configuration
- Feature flags and plan entitlements
- Platform roles and policy definitions
- Billing/subscription configuration
- Global templates/defaults
- Domain verification policy
- Platform observability and retention policy

Operational values may be displayed by design components but should be referenced at render time, not copied into a design snapshot as authoritative state.

## 10. Draft/publish/revert architecture

Use a mutable draft workspace plus immutable published snapshots.

### Recommended records

- Tenant design workspace: one mutable draft document/configuration per tenant, with revision/concurrency metadata.
- Immutable design versions: append-only snapshots containing validated design/presentation configuration and asset references.
- Published pointer: tenant storefront configuration references exactly one published version.
- Optional preview token/session: authorizes access to the draft or a selected version without making it public.

### Preview

- Owner/admin preview resolves the authenticated tenant membership and draft revision.
- A shareable preview uses a short-lived, unguessable, tenant-bound token.
- Preview responses must be `no-store` or use tenant/draft/version-aware cache keys.
- Preview must never change public cache state or the published pointer.

### Publish

1. Validate draft schema and referenced tenant-owned assets.
2. Create an immutable version snapshot.
3. Atomically update the tenant's published-version pointer in the same transaction.
4. Emit a tenant-scoped cache invalidation/version event after commit.
5. Record publisher, source draft revision, timestamp, and audit event.

The public storefront reads only the published pointer/version. It never falls back to a mutable draft.

### Revert

Revert should republish a prior immutable snapshot as a new version or atomically point to a validated prior version while recording a new publish event. Creating a new version preserves an append-only publication history and makes the action explicit. Revert must not roll back live commerce data.

### Commerce data excluded from snapshots

Never include authoritative:

- Product/category records or ordering
- Prices, variants, modifiers, tax, or availability
- Orders/customers/loyalty balances
- Fulfillment settings/state
- Clover/payment configuration
- Business hours/closures
- Authentication/membership data

Design configuration may reference stable commerce presentation concepts (for example a category section component), but current commerce data is resolved live under the same tenant.

## 11. Complete Ladel's-specific assumption inventory

Classification:

- **A — Safe reference/default:** useful seed/template or reference behavior, not a runtime global.
- **B — Must become tenant configuration.**
- **C — Must become platform configuration.**
- **D — Must be removed from reusable runtime.**
- **E — Needs product decision.**

| Area/assumption | Classification | Treatment |
|---|---|---|
| “Ladel's” and “The Guest House” names | B | Tenant display/legal naming, never global runtime identity |
| Existing logo and brand marks | A/B | Preserve as Ladel's reference tenant assets; other tenants provide their own |
| Brand colors, typography, visual tokens | A/B | Safe reference template, ultimately tenant design configuration |
| Hero and promotional imagery | A/B | Preserve for Ladel's tenant; tenant-owned media/design references |
| Ladel's-specific navigation/homepage copy | B | Tenant design/content configuration |
| Menu/category/product seed data | A | Valid seed/reference data for the Ladel's tenant, never a platform-global catalog |
| Product photos and catalog imagery | A/B | Preserve originals and associate with Ladel's tenant catalog/media records |
| Lunch-special behavior | E | Existing feature is proven, but determine whether it is a configurable tenant capability/template or generalized promotion type |
| Global one-lunch-special constraint | D | Replace with tenant-aware constraint before multiple tenants |
| HST assumptions and labels | B/E | Tenant jurisdiction/tax configuration; decide V1 tax-market scope |
| CAD currency assumptions | B/E | Ladel's tenant default; decide supported currencies for V1 |
| Canadian address/phone formatting | B/E | Tenant/customer locale configuration; define V1 regional scope |
| Pickup-only or current fulfillment modes | A/B/E | Preserve as Ladel's configuration; decide platform-supported modes and extensibility |
| Current lead times, cutoff times, hours, closures | B | Tenant operational settings |
| Single timezone | B | Required tenant setting used consistently by scheduling and notifications |
| Kitchen/fulfillment status workflow | A/B/E | Safe proven default; decide whether workflows are configurable or fixed platform behavior |
| Staff portal wording and operational labels | A/B | Default template with tenant branding where appropriate |
| Staff PIN assumptions | B/E | Tenant membership credential policy; decide cross-tenant behavior |
| Single-owner/single-business auth selection | D | Replace with explicit memberships and selected organization context |
| `JDS_ORGANIZATION_SLUG` as runtime selector | C/D | Temporary compatibility configuration only; not canonical tenancy |
| Customer profile as one merchant's customer | D | Split global identity from tenant customer relationship |
| Notification wording naming Ladel's/Guest House | B | Tenant template/content with platform-safe defaults |
| Notification timezone/sender assumptions | B/C | Tenant operational settings; provider credentials/settings may be platform-level |
| Ladel's domain names and absolute URLs | B/D | Tenant hostname/link configuration; remove hard-coded reusable runtime values |
| Social links/contact/location copy | B | Tenant configuration |
| PWA app name, short name, icons, theme colors | B | Tenant published design/PWA metadata |
| Static service-worker/cache identity | D | Tenant/version-aware caching required |
| Netlify build/deploy assumptions | C/E | New SaaS deployment architecture decision; imported config is baseline reference only |
| Render/Supabase production assumptions | C/E | Platform environment/deployment configuration; never tenant identity |
| Clover merchant ID/token/page configuration | B/D | Tenant Clover installation; remove singleton merchant runtime behavior |
| Clover app/environment credentials | C | Platform secret/configuration, isolated from tenant tokens |
| Hosted Checkout wording/return URLs | B/C | Tenant brand and verified platform routing combined safely |
| Merchant diagnostics assumptions | B/C | Tenant installation diagnostics exposed through authorized platform capability |
| Guest-house-specific SEO metadata/share text | B | Tenant published design/content configuration |
| Static asset paths that imply one tenant | B/D | Move to tenant media bindings or Ladel's tenant reference assets |
| Proven ordering, modifier, pricing, scheduling, fulfillment semantics | A | Preserve and tenant-scope before considering generalization |

## 12. Safe database migration strategy

### Principles

- Expand before contract.
- Backfill a deterministic initial Ladel's organization.
- Preserve current behavior through explicit compatibility code.
- Verify tenant ownership and invariants before enforcing `NOT NULL`.
- Change one aggregate boundary at a time.
- Never mix tenancy migration with broad renaming, redesign, or feature work.

### Initial tenant

Use the existing Ladel's organization if one is already deterministically present; otherwise create it in a migration with a fixed UUID and canonical slug. Do not generate a different UUID per environment if fixtures, references, or rollback verification need a stable identity. Store environment-specific hostnames/configuration separately.

### Dependency-ordered migration sequence

1. **Organization foundation**
   - Verify/create deterministic Ladel's organization.
   - Add lifecycle/status fields only if required for resolution.
   - Establish the compatibility tenant resolver.

2. **Catalog and business settings expansion**
   - Add nullable `organization_id` to categories, products, modifier groups, and business settings.
   - Backfill all existing rows to Ladel's.
   - Add tenant-leading indexes.
   - Add new tenant-aware unique constraints/indexes without prematurely dropping compatibility constraints where rollout requires both.
   - Convert repositories and validate ownership.
   - Make columns `NOT NULL` after verification.

3. **Availability and scheduling**
   - Add/backfill organization ownership for hours, closures, availability configuration, and scheduling records.
   - Replace settings singleton logic.

4. **Orders and fulfillment**
   - Add nullable organization to orders and backfill from the initial tenant/catalog where unambiguous.
   - Propagate/inherit ownership for items, modifiers, state history, and fulfillment records.
   - Add tenant-aware idempotency and dashboard indexes.
   - Convert all reads/writes before enforcing non-null and dropping global patterns.

5. **Identity and tenant relationships**
   - Preserve global users/external identities.
   - Normalize memberships and tenant customer relationships.
   - Bind invitations, sessions, staff credentials, preferences, and loyalty to organization.

6. **Clover and external events**
   - Create tenant-owned installations.
   - Backfill the Ladel's installation using metadata references without embedding secrets in migration files.
   - Add tenant/installation to checkout, payment, webhook, and reconciliation ledgers.
   - Enforce environment/merchant mapping uniqueness.

7. **Notifications, loyalty, media, design**
   - Tenant-scope audiences, preferences, delivery attempts, program records, and logical media.
   - Add design workspace/version/published pointer only after tenant resolution is reliable.

8. **Contract**
   - Remove compatibility fallback only after every production route/job has verified tenant resolution.
   - Remove obsolete global unique constraints and singleton paths.
   - Enforce non-null ownership and cross-tenant integrity.

### Foreign keys and cross-tenant integrity

Simple foreign keys ensure existence but not same-tenant ownership. For critical relationships, use one or more of:

- Composite unique keys such as `(organization_id, id)` and composite foreign keys.
- Repository/service invariants checked transactionally.
- Database triggers only where necessary and maintainable.
- Row-level security later as defense-in-depth.

Orders, catalog assignments, modifier joins, loyalty relationships, media links, and Clover payment relationships require explicit same-tenant validation.

### Transitional compatibility

- A compatibility resolver maps only known legacy Ladel's surfaces to the initial organization.
- Existing API response shapes and visible storefront behavior stay unchanged.
- Repository methods become tenant-bound internally before routes expose tenant selection.
- Dual-read/dual-write is used only where necessary and short-lived; avoid indefinite optional tenant predicates.
- Emit metrics/assertions for missing tenant context during rollout.

### Rollback concerns

- Adding nullable columns and indexes is readily reversible; dropping global constraints or columns is not.
- Keep old constraints until new code is deployed and verified where they do not block multi-tenant fixtures.
- Once multiple tenants contain duplicate slugs/keys, rolling back to globally unique constraints is impossible without data loss or renaming.
- Never down-migrate by deleting tenant data.
- Clover installation/token migration needs a tested restoration plan that does not print or duplicate secrets.
- Published design versions and media references require referential-safe rollback.

### Tests before each stage

- Migration upgrade from a representative baseline database.
- Verification that every existing row maps to Ladel's exactly once.
- Constraint tests for same-tenant and cross-tenant records.
- Legacy behavior regression suite.
- Two-tenant repository tests before accepting route changes.
- Migration downgrade only where safely supported, plus documented irreversible boundaries.

## 13. Required tenant-isolation test matrix

The minimum credible multi-tenant suite must use at least two tenants with deliberately colliding slugs, product names, customer identities, order-like identifiers, and external-provider references where valid.

| Boundary | Required adversarial proof |
|---|---|
| Catalog | Tenant A cannot list, fetch, update, reorder, archive, or attach Tenant B categories/products/modifiers |
| Catalog uniqueness | Same slug/key can exist in A and B; duplicates within one tenant fail |
| Lunch special | Clearing/setting A's special does not change B's special |
| Availability | A's hours, closures, lead time, and capacity never affect B |
| Customers | A owner/staff cannot list or fetch B customer relationship/profile/history |
| Customer identity | One global customer interacting with A and B receives only the current tenant's history/preferences/loyalty |
| Orders | A cannot read B order by guessed UUID, public token, idempotency key, or dashboard query |
| Order mutation | A staff cannot transition, refund/reconcile, annotate, or fulfill B order |
| Staff | Staff membership in A grants no access to B; multi-membership selection scopes exactly one tenant |
| Owners | Owner of A cannot manage B without a B membership; body/route tenant substitution is rejected |
| Platform admin | Platform access is separately granted and every tenant selection is audited |
| Sessions | A-bound management session cannot be replayed against B; membership suspension takes effect |
| Cart/storage | Customer cart, recent order, and cached catalog for A never appear in B |
| Checkout | A cart cannot use B products, pricing, settings, or Clover installation |
| Clover OAuth | Callback state for A cannot install or overwrite B; state is single-use and expires |
| Clover webhook | Merchant A event cannot look up or mutate Merchant B order even with colliding provider/order references |
| Reconciliation | Order, checkout, event, installation, merchant, and tenant mismatch fails closed and is quarantined |
| Webhook dedupe | Same provider event IDs in distinct valid installation scopes do not collide; duplicates within one scope are idempotent |
| Notifications | A announcement cannot select B subscribers; activity and delivery logs remain scoped |
| Loyalty | A cannot read/change B program, balance, award, or product mapping |
| Media | A cannot reference, enumerate, update, or delete B logical media/assets |
| Draft design | A draft is invisible to public users and B; preview token is tenant-bound |
| Published design | A published version never renders on B; publish pointer changes atomically |
| Revert | Reverting design changes only A design and never commerce state |
| Host routing | Unknown hosts fail; host/path conflict fails; A host cannot request B via a parameter |
| Caching | Identical paths and query strings on A and B return distinct tenant content; invalidation is tenant/version-scoped |
| PWA | Manifest, icons, service worker scope, and offline cache cannot cross tenants |
| Background jobs | A job payload cannot process B object IDs; missing tenant context fails closed |
| Audit logs | Tenant users cannot read another tenant's audit records; platform access remains explicit |

Tests must cover repository, service, API, and browser/cache layers. Route-only tests are insufficient because workers, webhooks, and internal services can bypass HTTP authorization.

## 14. Dependency-ordered implementation roadmap

### Milestone 1 — Tenant identity and compatibility foundation

- **Goal:** Establish canonical organization identity and immutable tenant context while preserving Ladel's behavior.
- **Affected areas:** organizations, compatibility resolution, dependency injection/unit of work, logging/audit context.
- **Prerequisites:** Clean baseline and deterministic Ladel's organization.
- **Migrations:** Organization verification/seed; first nullable ownership columns for the catalog spine.
- **Tests:** Tenant-context construction, known legacy fallback, unknown/conflicting tenant rejection, migration backfill.
- **Major risks:** Allowing compatibility fallback on arbitrary hosts; treating slug/env as canonical identity.
- **Ladel's behavior:** No intended visible change.

### Milestone 2 — Catalog and availability persistence isolation

- **Goal:** Tenant-own products, categories, modifiers, business settings, hours, closures, and availability.
- **Affected areas:** catalog/availability models, repositories, services, owner and public routes, caches.
- **Prerequisites:** Milestone 1.
- **Migrations:** Organization FKs, backfill, tenant-aware unique/partial indexes, settings singleton replacement.
- **Tests:** Two-tenant catalog and scheduling isolation, collision constraints, unchanged Ladel's snapshots/behavior.
- **Major risks:** Missed global write helpers and lunch-special logic; cross-tenant joins.
- **Ladel's behavior:** No intended functional change; data becomes explicitly owned.

### Milestone 3 — Orders and fulfillment isolation

- **Goal:** Make the order aggregate, kitchen queues, status transitions, and idempotency tenant-safe.
- **Affected areas:** orders/items/modifiers, repository, checkout, dashboards, fulfillment workers/events.
- **Prerequisites:** Tenant-owned catalog/settings.
- **Migrations:** Order organization FK/backfill, tenant-aware idempotency/indexes, inherited ownership validation.
- **Tests:** Cross-tenant read/mutation denial, dashboard isolation, same-tenant product validation, regression ordering flow.
- **Major risks:** Global order-by-ID paths and asynchronous work without tenant scope.
- **Ladel's behavior:** No intended workflow change.

### Milestone 4 — Authentication and membership model

- **Goal:** Separate global identity, workforce membership, tenant customer relationship, and platform administration.
- **Affected areas:** users, external identities, memberships, sessions, invitations, staff PINs, customer profiles.
- **Prerequisites:** Reliable tenant-owned commerce roots.
- **Migrations:** Normalize tenant relationships and session/membership references.
- **Tests:** Multi-business owner/staff, customer across merchants, suspension, permission boundaries.
- **Major risks:** Inferring organization from a user with multiple memberships; conflating customers with staff.
- **Ladel's behavior:** Login UX may later gain business selection, but current single-business path remains compatible.

### Milestone 5 — Request tenant resolution and authorization

- **Goal:** Apply surface-specific resolution to every route and worker boundary.
- **Affected areas:** FastAPI dependencies/middleware, frontend bootstrapping, API clients, jobs, cache keys.
- **Prerequisites:** Membership model and tenant-owned primary aggregates.
- **Migrations:** Hostname mapping records if introduced here.
- **Tests:** Host/claim/route conflict, unknown host, tenant substitution, job context.
- **Major risks:** Trusting client tenant headers/IDs; inconsistent dependencies between route groups.
- **Ladel's behavior:** Legacy host resolves to the same initial tenant.

### Milestone 6 — Clover tenant isolation

- **Goal:** One safely isolated Clover connection per merchant/tenant and fail-closed payment processing.
- **Affected areas:** OAuth, token storage, Hosted Checkout, webhook ledger, reconciliation, diagnostics.
- **Prerequisites:** Orders and authorization fully tenant-scoped; request context established.
- **Migrations:** Tenant Clover installations, tenant/installation references on checkout/events, scoped constraints.
- **Tests:** OAuth state, merchant mapping, adversarial webhook/reconciliation, token redaction.
- **Major risks:** Cross-tenant payment mutation and provider environment ambiguity.
- **Ladel's behavior:** Existing Clover behavior must remain functionally identical for the Ladel's installation.

### Milestone 7 — Notifications and loyalty isolation

- **Goal:** Scope audiences, preferences, sends, programs, balances, and activity.
- **Affected areas:** notification queue/workers, subscribers, preferences, announcements, loyalty repositories.
- **Prerequisites:** Identity/customer relationships and tenant jobs.
- **Migrations:** Organization ownership and scoped unique/index changes.
- **Tests:** Cross-tenant audience and loyalty denial, correct timezone/templates, delivery ledger ownership.
- **Major risks:** Global broadcast queries and user-only preference keys.
- **Ladel's behavior:** Same messages and loyalty semantics, now sourced from Ladel's settings.

### Milestone 8 — Hosted storefront resolution

- **Goal:** Serve tenant storefronts canonically by subdomain with isolated browser state.
- **Affected areas:** host mapping, frontend bootstrap, routes, sessions, caching/CDN, links.
- **Prerequisites:** Request resolution and tenant-scoped commerce.
- **Migrations:** Verified hostname mapping and canonical host records.
- **Tests:** Host isolation, unknown/conflicting host, storage/cart/cache separation.
- **Major risks:** CDN/service-worker cache contamination and permissive fallback.
- **Ladel's behavior:** Ladel's receives its canonical hosted tenant domain while legacy links redirect safely.

### Milestone 9 — Media and design configuration

- **Goal:** Move hard-coded presentation into tenant-owned design configuration without moving commerce data.
- **Affected areas:** assets/media, storefront renderer, design tokens, PWA metadata.
- **Prerequisites:** Host isolation and tenant asset access controls.
- **Migrations:** Tenant logical media and design workspace schema.
- **Tests:** Media ownership, tenant render isolation, Ladel's visual regression.
- **Major risks:** Broken reference assets and treating operational values as mutable design.
- **Ladel's behavior:** Preserved as the reference/default design.

### Milestone 10 — Draft/publish/revert

- **Goal:** Safe mutable preview and atomic immutable publication.
- **Affected areas:** design versions, preview API, publication service, cache invalidation.
- **Prerequisites:** Tenant design configuration/media.
- **Migrations:** Draft workspace, immutable versions, published pointer, audit metadata.
- **Tests:** Draft invisibility, atomic publish, cross-tenant version denial, revert without commerce change.
- **Major risks:** Draft leakage through caches and partial publication.
- **Ladel's behavior:** Public storefront stays on a validated published Ladel's snapshot.

### Milestone 11 — Onboarding and fulfillment configuration

- **Goal:** Allow a merchant to establish tenant operational data using proven defaults.
- **Affected areas:** organization creation, catalog setup/import, hours, fulfillment, notifications, Clover readiness.
- **Prerequisites:** Isolated core domains and design publishing.
- **Migrations:** Onboarding state/checkpoints if required.
- **Tests:** Incomplete onboarding isolation, retry/idempotency, default cloning ownership.
- **Major risks:** Copying references across tenants and exposing half-configured storefronts.
- **Ladel's behavior:** Ladel's remains the reference, not the mutable source for every tenant.

### Milestone 12 — Platform administration and observability

- **Goal:** Provide JDS operational control without weakening tenant boundaries.
- **Affected areas:** platform roles, support access, audit, metrics/logging, tenant health.
- **Prerequisites:** Stable tenant context across all services.
- **Migrations:** Platform grants/support sessions and audit records as needed.
- **Tests:** Explicit platform authorization, audited tenant selection, redaction.
- **Major risks:** Hidden superuser bypasses and secrets/PII in logs.
- **Ladel's behavior:** No commerce behavior change.

### Milestone 13 — Billing and entitlements

- **Goal:** Add SaaS plans/billing without coupling payments for orders to platform billing.
- **Affected areas:** subscriptions, entitlements, limits, platform billing provider.
- **Prerequisites:** Organization lifecycle and platform administration.
- **Migrations:** Billing accounts/subscriptions/entitlements.
- **Tests:** Tenant billing isolation and fail-safe entitlement behavior.
- **Major risks:** Confusing merchant customer payments with JDS SaaS billing.
- **Ladel's behavior:** No order-payment change.

### Milestone 14 — Ladel's reference-tenant migration rehearsal and contract

- **Goal:** Prove production-safe migration and remove temporary single-tenant compatibility paths.
- **Affected areas:** full stack, migration tooling, runbooks, monitoring.
- **Prerequisites:** All tenant-aware milestones and adversarial tests.
- **Migrations:** Final non-null/constraint enforcement and obsolete singleton cleanup.
- **Tests:** Production-like copy rehearsal, rollback/restore drills, full regression and isolation suite.
- **Major risks:** Irreversible constraint changes and unobserved legacy entry points.
- **Ladel's behavior:** Must remain behaviorally equivalent except approved SaaS routing/admin changes.

## 15. Exact recommended first implementation milestone

### Name

**Tenant identity and catalog ownership spine**

### Goal

Establish the smallest durable tenant boundary around the read-mostly storefront foundation while changing as little proven commerce behavior as possible. This milestone should make Ladel's ownership explicit and prove the repository/context pattern before orders, payments, authentication selection, or UI tenancy are touched.

### Exact models/tables involved

Reuse:

- `organizations`
- existing organization memberships only as needed to identify the existing Ladel's organization; do not redesign membership yet

Add `organization_id` ownership to:

- categories
- products
- modifier groups
- business settings

Include directly dependent category/product/modifier association records in same-tenant integrity checks, but avoid broad schema redesign. Business hours/closures may be included only if they cannot safely remain behind the tenant-owned settings boundary; otherwise they are the immediately following migration.

### Migration shape

1. Verify or insert one deterministic Ladel's organization row.
2. Add nullable organization foreign keys to the four root tables.
3. Backfill every existing row to that organization; do not infer or invent multiple tenants.
4. Add organization-leading indexes.
5. Replace global uniqueness with tenant-aware constraints:
   - category slug per organization
   - product slug/key/SKU per organization as applicable
   - modifier group key per organization
   - business settings unique per organization
   - lunch-special partial uniqueness per organization
6. Add validation queries/tests proving no null/orphan/cross-tenant relationships.
7. Make organization ownership non-null only after code and data verification.
8. Preserve safe rollback until duplicate values legitimately exist across tenants.

### Compatibility approach

- Introduce immutable `TenantContext` and a server-side compatibility resolver.
- Resolve current known Ladel's requests to the deterministic Ladel's organization.
- Do not expose arbitrary tenant selection to the frontend yet.
- Keep current route shapes, response schemas, visual behavior, and ordering behavior unchanged.
- Restrict fallback to explicitly known legacy context; unknown/conflicting resolution fails closed.
- Add structured tenant ID to logs without exposing customer or secret data.

### Repository changes

- Bind `CatalogRepository` and `AvailabilityRepository`/business-settings access to `TenantContext`.
- Add tenant predicate to every catalog/settings root read and write.
- Scope catalog ordering, lunch-special clearing, and advisory locking by organization.
- Validate product/category/modifier associations are within one tenant.
- Remove direct singleton `BusinessSettings(id=1)` use from converted paths in favor of organization lookup.
- Eliminate unsafe unscoped “get all” methods from converted repository interfaces; platform-wide reads, if ever needed, require a separate explicit capability.

### Routes affected internally

- Public catalog/product/modifier endpoints
- Public scheduling/business-settings endpoints that depend on the converted settings path
- Owner catalog/product/category/modifier endpoints
- Owner scheduling/settings endpoints that use the converted repository

External URL and response behavior should remain unchanged during this milestone.

### Required tests

- Migration backfills all baseline rows to the Ladel's organization.
- Ladel's catalog/availability regression fixtures remain unchanged.
- Tenant A cannot list/fetch/update/reorder Tenant B catalog records.
- Same category/product/modifier slugs or keys can coexist across tenants.
- Duplicates within one tenant fail.
- Setting/clearing Tenant A lunch special does not alter Tenant B.
- Tenant A settings do not affect Tenant B availability.
- Association attempts across tenants fail.
- Unknown tenant, conflicting tenant inputs, or missing context fail closed outside the explicit legacy path.
- Cache/advisory-lock keys are tenant-aware.
- Existing frontend catalog tests and production build continue to pass.

### Deliberately deferred

- Order and fulfillment ownership
- Customer relationship redesign
- Owner/staff multi-business selection UX
- Session/token claim changes beyond what is minimally needed internally
- Hostname/subdomain rollout
- Clover installation/token/webhook conversion
- Notification and loyalty conversion
- Media redesign
- Design Studio configuration
- Draft/publish/revert
- Platform administration
- Billing and entitlements
- Broad renaming or removal of Ladel's branding
- SaaS deployment configuration

## 16. Risks, blockers, and product decisions

### Highest architectural risks

1. **Partial tenant predicates:** converting routes but leaving global repository helpers, workers, caches, or diagnostics creates false confidence.
2. **Clover cross-tenant mutation:** merchant resolution must happen before any order lookup, with equality invariants through reconciliation.
3. **Notification broadcast leakage:** current subscriber/activity patterns require early isolation before multi-tenant sends.
4. **Identity conflation:** global identity, workforce membership, and customer relationship must remain distinct.
5. **Permissive compatibility fallback:** a default Ladel's tenant on unknown hosts would hide routing bugs and leak data.
6. **Browser/CDN caching:** backend-correct tenancy can still fail through shared local storage, service workers, manifests, or CDN keys.
7. **Constraint rollout:** dropping global uniqueness becomes effectively irreversible after valid duplicate tenant values exist.
8. **Design/commerce coupling:** snapshots must never become stale authoritative copies of catalog, price, availability, or operational settings.

### Product decisions required

- Is an organization exactly one merchant/location in V1, or can it own multiple locations/installations?
- Can a staff member use one PIN across businesses, and how is organization selected at sign-in?
- Which customer fields are global platform identity versus merchant-owned relationship data?
- Is V1 limited to Canadian/CAD/HST-compatible tenants, or must currency/tax jurisdiction be generalized immediately?
- Is lunch-special functionality a standard product capability, an optional template, or a more general promotions model?
- Which fulfillment workflows are fixed platform behavior versus tenant-configurable?
- Does Clover supply an app-level webhook secret or installation-specific verification material for the chosen integration mode?
- Are custom domains post-V1 while merchant subdomains are canonical V1?
- What platform support/impersonation capabilities are permitted, and what audit/consent is required?
- What media storage/provider will enforce tenant ownership and signed access?

### Blockers before implementation

There is no architectural blocker to beginning the narrow first milestone. Before Clover migration, confirm the provider's exact OAuth/webhook secret and environment semantics. Before customer schema migration, decide the global-versus-tenant profile boundary. Before multi-location support, decide whether location is a V1 child aggregate or deferred.

## 17. Current git status at completion of the audit

At the time the read-only architecture audit completed:

- Branch: `main`
- Baseline HEAD: `057039cf7d34c31044535b88d076b5d9acb43423`
- Local `main` matched `origin/main`
- Working tree was clean
- No files were created, modified, staged, committed, pushed, or deployed as part of the audit
- No database, Clover configuration, authentication configuration, production service, or source repository was changed

---

**TENANT ARCHITECTURE AUDIT COMPLETE — NO CHANGES MADE**
