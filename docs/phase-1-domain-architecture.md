# Phase 1 — Identity and Domain Architecture

Status: DESIGN
Date: 2026-08-29

Read `PROJECT_CONTEXT.md` and `AGENTS.md` before changing this architecture.

This document defines the Phase 1 target domain model for Purchase Intelligence.

No legacy tables should be dropped merely because this document exists.
Phase 1 migration must be additive first and use a controlled cutover.

---

# 1. Purpose

The Phase 0 prototype proved:

- Nike product crawling
- variant extraction
- historical price recording
- target-price evaluation
- size availability evaluation
- email notifications
- duplicate-alert prevention
- frontend watchlist
- GitHub Actions monitoring

However, the Phase 0 schema is URL-centric and effectively single-user.

Phase 1 changes the foundation so the application can support:

- real accounts
- multiple users
- canonical products
- multiple merchants
- generic product variants
- user-specific watch intents
- per-user permissions
- admin feature flags
- listing-level monitoring
- future product discovery
- future purchase intelligence

---

# 2. Core Architectural Principles

## 2.1 Product is not listing

A real-world product and a merchant webpage are different entities.

Example:

Canonical product:

Soundcore Q20i

Possible merchant listings:

- Amazon Soundcore Q20i
- Flipkart Soundcore Q20i
- Soundcore official Q20i

All listings may refer to the same canonical product.

---

## 2.2 Watch is not crawl

A user's watch represents purchase intent.

Example:

User A:

- Soundcore Q20i
- target ₹4,000
- black preferred
- any supported merchant

User B:

- same Soundcore Q20i
- target ₹4,500
- Amazon only

The Q20i listing should be crawled once.

The resulting observation can then be evaluated against both watches.

---

## 2.3 Historical observations are immutable facts

Current values may be cached on listings for fast UI access.

Historical observations should remain append-only.

Example:

merchant listing:
current_price = ₹4,999

observations:
Aug 29 10:00 → ₹5,299
Aug 29 12:00 → ₹4,999
Aug 29 14:00 → ₹4,999

---

## 2.4 Product categories must not control the database schema

The application must support:

- shoes
- clothes
- phones
- headphones
- watches
- other products

Therefore the long-term model must not contain universal columns such as:

- shoe_size
- phone_storage
- clothing_fit

Variant-specific data should use normalized JSON attributes.

Examples:

Shoe:

{
  "size": "UK 9",
  "color": "Black"
}

Phone:

{
  "storage_gb": 256,
  "ram_gb": 8,
  "color": "Black"
}

Headphones:

{
  "color": "Blue"
}

---

# 3. Identity Architecture

Supabase Auth will own authentication identities.

System-owned table:

auth.users

Application-owned identity table:

profiles

Relationship:

auth.users.id
    │
    └── profiles.id

`profiles.id` must use the same UUID as `auth.users.id`.

Do not create a separate password/authentication implementation.

---

# 4. Profiles

Target table:

profiles

Suggested fields:

- id uuid primary key
- email text
- display_name text
- avatar_url text
- role text
- created_at timestamptz
- updated_at timestamptz

Role values initially:

- user
- admin
- super_admin

Default role:

user

Role must NOT be trusted from editable client metadata.

Authorization-relevant role data must remain protected in the database.

The project owner's account can later be promoted to:

super_admin

using an explicit administrative operation.

Do not hardcode a specific email address into authorization logic.

---

# 5. Authentication UX

Phase 1 initial authentication should support:

- email signup
- email login
- logout
- authenticated session
- password reset

Architecture should remain compatible with future OAuth providers such as Google.

OAuth does not need to block the initial Phase 1 implementation.

---

# 6. Categories

Target table:

categories

Suggested fields:

- id uuid primary key
- slug text unique
- name text
- parent_id uuid nullable
- attributes_schema jsonb nullable
- created_at timestamptz

Examples:

electronics
    ├── headphones
    ├── phones
    └── watches

fashion
    ├── shoes
    └── clothing

`attributes_schema` can later describe useful attributes for discovery or UI.

It must not become a rigid replacement for real validation logic.

---

# 7. Brands

Target table:

brands

Suggested fields:

- id uuid primary key
- slug text unique
- name text
- official_url text nullable
- logo_url text nullable
- created_at timestamptz

Examples:

- Nike
- Adidas
- ASICS
- Soundcore
- Samsung
- Apple

---

# 8. Canonical Products

Target table:

canonical_products

Purpose:

Represent the actual product independently of where it is sold.

Suggested fields:

- id uuid primary key
- brand_id uuid nullable
- category_id uuid nullable
- name text
- model_name text nullable
- model_number text nullable
- description text nullable
- image_url text nullable
- identifiers jsonb
- attributes jsonb
- status text
- created_at timestamptz
- updated_at timestamptz

Possible `identifiers`:

{
  "gtin": "...",
  "ean": "...",
  "upc": "...",
  "mpn": "..."
}

Possible `attributes`:

{
  "gender": "men",
  "use_case": "road running"
}

Status examples:

- active
- hidden
- merged

Canonical products should NOT contain merchant URLs.

---

# 9. Canonical Variants

Target table:

canonical_variants

Purpose:

Represent meaningful variants of a canonical product independently of merchant.

Suggested fields:

- id uuid primary key
- product_id uuid
- title text nullable
- canonical_sku text nullable
- attributes jsonb
- variant_key text
- image_url text nullable
- created_at timestamptz
- updated_at timestamptz

Example:

Nike Pegasus Premium
    ├── UK 7
    ├── UK 8
    └── UK 9

Attributes:

{
  "size": "UK 9"
}

Another example:

Phone
    ├── 128 GB / Black
    └── 256 GB / Black

Attributes:

{
  "storage_gb": 256,
  "color": "Black"
}

`variant_key` must be a stable normalized representation produced by application logic.

Within one canonical product:

(product_id, variant_key)

should be unique.

A GIN index should later be considered for `attributes`.

---

# 10. Merchants

Target table:

merchants

Purpose:

Represent a retailer/platform/source.

Suggested fields:

- id uuid primary key
- slug text unique
- name text
- base_url text
- adapter_key text
- active boolean
- created_at timestamptz
- updated_at timestamptz

Examples:

nike-in
amazon-in
flipkart
myntra
ajio
adidas-in

`adapter_key` maps the merchant to the appropriate crawler/discovery implementation.

---

# 11. Merchant Listings

Target table:

merchant_listings

Purpose:

Represent one merchant's page/listing for a canonical product.

Suggested fields:

- id uuid primary key
- product_id uuid
- merchant_id uuid
- external_id text nullable
- url text
- title text nullable
- image_url text nullable
- seller_name text nullable
- current_mrp numeric nullable
- current_price numeric nullable
- currency text
- in_stock boolean nullable
- last_checked_at timestamptz nullable
- active boolean
- created_at timestamptz
- updated_at timestamptz

Important:

The `current_*` fields are cache fields for fast reads.

Historical truth lives in observation tables.

Suggested uniqueness:

- url unique
- optionally merchant_id + external_id when external_id exists

One canonical product may have many merchant listings.

---

# 12. Listing Variants

Target table:

listing_variants

Purpose:

Represent the merchant-specific purchasable variants.

Suggested fields:

- id uuid primary key
- listing_id uuid
- canonical_variant_id uuid nullable
- external_sku text nullable
- title text nullable
- attributes jsonb
- variant_key text
- current_mrp numeric nullable
- current_price numeric nullable
- currency text
- in_stock boolean nullable
- stock_remaining integer nullable
- last_checked_at timestamptz nullable
- active boolean
- created_at timestamptz
- updated_at timestamptz

Example:

Nike merchant listing
    ├── external SKU A → canonical UK 7
    ├── external SKU B → canonical UK 8
    └── external SKU C → canonical UK 9

`canonical_variant_id` can temporarily be null if matching is not yet known.

This is important for future multi-merchant canonicalization.

---

# 13. Listing Observations

Target table:

listing_observations

Purpose:

Append-only time series containing facts observed from a merchant listing.

Suggested fields:

- id bigint identity primary key
- listing_id uuid
- checked_at timestamptz
- mrp numeric nullable
- selling_price numeric nullable
- currency text
- in_stock boolean nullable
- stock_remaining integer nullable
- delivery_fee numeric nullable
- effective_price numeric nullable
- raw_data jsonb nullable

Indexes:

- listing_id
- checked_at desc
- listing_id + checked_at desc

Observation rows should generally not be updated after creation.

---

# 14. Listing Variant Observations

Target table:

listing_variant_observations

Purpose:

Historical state for merchant-specific variants.

Suggested fields:

- id bigint identity primary key
- listing_variant_id uuid
- checked_at timestamptz
- mrp numeric nullable
- selling_price numeric nullable
- currency text
- in_stock boolean nullable
- stock_remaining integer nullable
- raw_data jsonb nullable

This allows histories such as:

UK 9:
10:00 → out of stock
12:00 → out of stock
14:00 → in stock
16:00 → in stock

without confusing overall product availability.

---

# 15. Watch Intents

Target table:

watch_intents

Purpose:

Represent what a user wants to monitor.

Suggested fields:

- id uuid primary key
- user_id uuid
- product_id uuid
- canonical_variant_id uuid nullable
- tracking_scope text
- target_price numeric nullable
- currency text
- variant_requirements jsonb
- conditions jsonb
- status text
- created_at timestamptz
- updated_at timestamptz

Initial `tracking_scope` values:

- specific_listing
- selected_listings
- any_listing

Status values:

- active
- paused
- fulfilled
- archived

Example:

{
  "product_id": "Soundcore Q20i",
  "tracking_scope": "any_listing",
  "target_price": 4000,
  "variant_requirements": {
    "color": "Black"
  }
}

Another example:

Nike Pegasus:

{
  "target_price": 18000,
  "variant_requirements": {
    "size": "UK 9"
  }
}

---

# 16. Watch Conditions

Common conditions should eventually be represented explicitly where useful.

`conditions jsonb` allows future evolution without a new database migration for every alert experiment.

Example:

{
  "require_in_stock": true,
  "notify_target_price": true,
  "notify_any_price_drop": false,
  "notify_historical_low": true,
  "notify_restock": true
}

Critical high-frequency/query fields may later become dedicated columns.

Do not put every possible future rule into columns immediately.

---

# 17. Watch Listing Targets

Target table:

watch_listing_targets

Purpose:

Support watches that select one or multiple merchant listings.

Suggested fields:

- watch_id uuid
- listing_id uuid
- created_at timestamptz

Primary key:

(watch_id, listing_id)

Examples:

specific_listing:
one row

selected_listings:
multiple rows

any_listing:
no explicit target rows required; evaluator considers active listings for the canonical product

---

# 18. Watch Evaluation State

Target table:

watch_evaluation_state

Purpose:

Store current evaluation/deduplication state without confusing it with immutable notification history.

Suggested fields:

- watch_id uuid primary key
- condition_met boolean
- last_reason text nullable
- state jsonb
- last_evaluated_at timestamptz
- last_notified_at timestamptz nullable
- last_notified_effective_price numeric nullable

This replaces the conceptual role currently served by `watch_alert_state`.

---

# 19. Notification Preferences

Target table:

notification_preferences

Initial fields:

- user_id uuid
- email_enabled boolean
- email_address text nullable
- push_enabled boolean
- telegram_enabled boolean
- whatsapp_enabled boolean
- updated_at timestamptz

Email is the initial stable channel.

Experimental channels may remain disabled by feature flag even if the preference exists.

---

# 20. Notifications

Target table:

notifications

Purpose:

Store meaningful notification events.

Suggested fields:

- id uuid primary key
- user_id uuid
- watch_id uuid nullable
- type text
- title text
- body text
- payload jsonb
- dedupe_key text nullable
- created_at timestamptz

Example notification type:

target_price_and_restock

Example payload:

{
  "old_price": 19295,
  "new_price": 17999,
  "target_price": 18000,
  "variant": {
    "size": "UK 9"
  }
}

---

# 21. Notification Deliveries

Target table:

notification_deliveries

Purpose:

Track delivery separately from the notification itself.

Suggested fields:

- id uuid primary key
- notification_id uuid
- channel text
- status text
- provider_message_id text nullable
- attempted_at timestamptz nullable
- delivered_at timestamptz nullable
- failure_reason text nullable

Possible channel values:

- email
- push
- telegram
- whatsapp

Possible statuses:

- pending
- sent
- delivered
- failed

This prevents Resend-specific details from leaking into generic notification domain logic.

---

# 22. Feature Flags

Target table:

feature_flags

Suggested fields:

- key text primary key
- description text
- default_enabled boolean
- created_at timestamptz

Examples:

finance_intelligence
telegram_notifications
whatsapp_notifications
experimental_ai
price_prediction

---

# 23. User Feature Entitlements

Target table:

user_feature_entitlements

Suggested fields:

- user_id uuid
- feature_key text
- enabled boolean
- granted_by uuid nullable
- updated_at timestamptz

Primary key:

(user_id, feature_key)

The project owner/super-admin can enable experimental capabilities for selected users.

Do not hardcode user emails to determine beta access.

---

# 24. Future Tables — Not Phase 1 Implementation

The architecture should leave space for these, but Phase 1 does not need to implement all of them.

Future:

purchases
purchase_feedback
finance_profiles
planned_expenses
listing_offers
bank_offers
coupon_observations
recommendation_events
recommendation_feedback
search_sessions
discovery_events

Do not build them merely because they are listed here.

---

# 25. Authorization and RLS

RLS is required for user-owned data.

User-owned tables include:

- profiles
- watch_intents
- watch_listing_targets
- watch_evaluation_state where appropriate
- notification_preferences
- notifications
- notification_deliveries where user-visible
- future purchases
- future finance data

Core ownership rule:

auth.uid() = user_id

Users should only read/change their own watches and preferences.

---

# 26. Catalog RLS

Catalog/domain data such as:

- categories
- brands
- canonical_products
- canonical_variants
- merchants
- merchant_listings
- listing_variants
- observations

may be readable by authenticated users.

Normal clients must NOT be allowed to arbitrarily mutate crawler-owned catalog or historical observation data.

Writes should come from:

- trusted backend operations
- crawler/background workers
- explicit administrative tooling

---

# 27. Service Role Boundary

This is a critical security rule.

The Supabase service/secret key bypasses normal RLS protections.

Therefore:

CLIENT / USER REQUEST PATH:

Browser
    ↓
authenticated Supabase session
    ↓
user-scoped server/client
    ↓
RLS
    ↓
user-owned data

BACKGROUND PATH:

GitHub Actions / crawler / privileged backend
    ↓
service role
    ↓
catalog + observation writes

Do NOT use the service-role client as the default implementation for user-scoped CRUD APIs.

The current prototype does this for convenience.

Phase 1 must separate:

- user-scoped Supabase client
- privileged/admin Supabase client

---

# 28. Profile Creation

When a new Supabase Auth user is created:

auth.users insert
    ↓
database trigger
    ↓
profiles insert
    ↓
default role = user

Profile email can be copied from the Auth record for application/notification convenience.

If Auth email changes, the application should keep the profile/contact record synchronized.

---

# 29. Legacy Schema Interpretation

Current Phase 0 tables must be interpreted carefully.

## Current `products`

Current meaning:

primarily merchant listing / URL.

It currently mixes:

- URL
- merchant identity via hostname/brand
- product identity
- current price
- current stock
- image
- last checked state

Future mapping:

current products
    ↓
canonical_products
+
merchant_listings

---

# 30. Current `product_variants`

Current rows contain:

- size
- merchant SKU
- merchant-specific price
- merchant-specific availability
- stock count

Therefore they are closer to:

listing_variants

than pure canonical variants.

During migration they can initially create:

canonical_variant
+
listing_variant

for each legacy variant.

For the existing Nike data this mapping is initially 1:1.

---

# 31. Current `price_snapshots`

Current meaning:

historical observation for one legacy product URL.

Future mapping:

price_snapshots
    ↓
listing_observations

Historical timestamps and prices must be preserved.

---

# 32. Current `watchlists`

Current fields:

- product_id
- email
- desired_size
- target_price

Future mapping:

watchlists
    ↓
watch_intents

Mapping:

email
    ↓
profiles/user_id

desired_size
    ↓
variant_requirements:
{
  "size": "UK 9"
}

target_price
    ↓
watch_intents.target_price

product_id
    ↓
migrated canonical product / listing target

---

# 33. Current `watch_alert_state`

Future mapping:

watch_alert_state
    ↓
watch_evaluation_state

Preserve:

- condition_met
- last_reason
- last_evaluated_at
- last_notified_at
- last_notified_price

---

# 34. Migration Safety Strategy

Do NOT replace the current schema in one destructive migration.

Use staged migration.

## Stage A — Add new schema

Create Phase 1 tables alongside legacy tables.

Do not modify working production behavior yet.

Current crawler and frontend continue working.

---

## Stage B — Add authentication

Implement Supabase Auth.

Create profile trigger.

Create initial project-owner account through normal signup.

Promote that profile to super_admin through an explicit administrative SQL operation.

---

## Stage C — Backfill catalog

For each legacy `products` row:

1. create one canonical product,
2. determine merchant,
3. create one merchant listing,
4. map legacy product ID to new IDs.

Do NOT attempt aggressive cross-merchant product merging during initial backfill.

One legacy product may initially become one canonical product.

Correct merging can happen later.

---

## Stage D — Backfill variants

For each legacy `product_variants` row:

1. create canonical variant,
2. create listing variant,
3. preserve SKU,
4. preserve latest price,
5. preserve availability,
6. preserve stock count.

---

## Stage E — Backfill history

Copy legacy `price_snapshots` into `listing_observations`.

Preserve:

- checked_at
- MRP
- selling_price
- currency
- availability

---

## Stage F — Backfill watches

This can only happen after the corresponding authenticated user/profile exists.

Match legacy watch email to profile email.

Create:

watch_intent

and appropriate:

watch_listing_target

Convert:

desired_size

into:

variant_requirements JSON.

---

## Stage G — Backfill alert state

Map old watch IDs to new watch IDs.

Copy existing deduplication state into `watch_evaluation_state`.

---

# 35. Temporary Migration Mapping

During migration we need deterministic mapping between old and new identifiers.

Temporary migration mapping tables may be created, for example:

migration_legacy_product_map

legacy_product_id
canonical_product_id
listing_id

and:

migration_legacy_watch_map

legacy_watch_id
watch_intent_id

These mapping tables can be removed in a later cleanup migration after successful cutover.

Do not rely on guessed joins after IDs have changed.

---

# 36. Application Cutover Strategy

The existing production path remains functional until V2 is proven.

Recommended implementation workflow:

1. create additive schema
2. test schema
3. add Auth
4. create project-owner account
5. backfill current data
6. verify row counts/data
7. update crawler storage layer
8. update watch evaluator
9. update APIs
10. update frontend
11. run local end-to-end tests
12. run cloud crawler test
13. verify email alert flow
14. switch production usage to Phase 1 schema
15. freeze legacy writes
16. observe for a period
17. only later remove legacy tables

---

# 37. No Destructive Migration During Initial Phase 1

The following operations are NOT allowed during the first Phase 1 migration:

- drop products
- drop watchlists
- drop product_variants
- drop price_snapshots
- drop watch_alert_state
- rename legacy tables in a way that breaks Phase 0 code

The current working application must remain recoverable during migration.

---

# 38. Crawler Target Architecture

Current:

watch
    ↓
product URL
    ↓
crawl

Future:

unique active merchant listing
    ↓
crawl once
    ↓
store observation
    ↓
find watches that care about product/listing
    ↓
evaluate all watches

This becomes critical when multiple users track the same listing.

---

# 39. Crawler Adapter Boundary

Crawler implementations remain merchant-specific.

Conceptual interface:

search_products(...)
fetch_listing(...)
fetch_variants(...)
fetch_current_state(...)

Merchant-specific details may include:

- JSON-LD
- embedded application state
- HTML selectors
- Playwright
- merchant APIs

These details must be converted into normalized internal models before persistence.

---

# 40. Current Price Cache vs History

For fast frontend reads:

merchant_listings.current_price

may contain latest state.

For historical analysis:

listing_observations

contains immutable historical observations.

Similarly:

listing_variants.current_price

is latest cache.

listing_variant_observations

is historical truth.

---

# 41. Effective Price

Phase 1 only prepares for this concept.

Future:

effective_price =
selling_price
+ mandatory fees
- applicable coupon discount
- applicable bank discount
- applicable cashback where appropriate

Do not pretend an offer applies to a user unless eligibility is known.

---

# 42. Product Matching

Initial migration:

Do not automatically merge legacy products.

Future product discovery can use identifiers and matching logic:

Priority:

1. GTIN/EAN/UPC
2. manufacturer model number
3. merchant/manufacturer IDs
4. deterministic normalized attributes
5. fuzzy/AI-assisted matching
6. manual review where uncertain

AI matching must not silently merge uncertain products.

---

# 43. Phase 1 Implementation Order

After this design is approved:

## Milestone 1

Create additive identity/catalog migration.

Includes:

- profiles
- categories
- brands
- merchants
- canonical_products
- canonical_variants
- merchant_listings
- listing_variants

No legacy changes.

## Milestone 2

Add watch/notification domain.

Includes:

- watch_intents
- watch_listing_targets
- watch_evaluation_state
- notification_preferences
- notifications
- notification_deliveries
- feature_flags
- user_feature_entitlements

## Milestone 3

Add RLS policies and Auth profile trigger.

## Milestone 4

Configure Supabase Auth and create first real user.

## Milestone 5

Backfill the existing Nike/product/history/watch data.

## Milestone 6

Refactor crawler persistence to Phase 1 schema.

## Milestone 7

Refactor evaluator and email notification pipeline.

## Milestone 8

Refactor Next.js APIs to authenticated user ownership.

## Milestone 9

Build login/signup/session UI.

## Milestone 10

Validate full cloud path.

---

# 44. Phase 1 Definition of Done

Phase 1 is complete when:

- users can register/login
- profiles exist
- watches belong to authenticated users
- users cannot read another user's private watch data
- canonical product is separate from merchant listing
- variants are generic
- current Nike product exists in new catalog model
- historical snapshots survive migration
- existing watch survives migration
- crawler writes to new listing/observation model
- watch evaluation still works
- Resend alert still works
- duplicate alert suppression still works
- GitHub Actions still monitors automatically
- frontend uses authenticated Phase 1 APIs
- legacy Phase 0 tables are no longer required for normal runtime

Dropping legacy tables is a separate cleanup decision after Phase 1 stability is proven.

---

# 45. Explicitly Deferred

Do not include these in the first Phase 1 coding milestone:

- Amazon scraping
- Flipkart scraping
- Adidas discovery
- ASICS discovery
- AI conversational search
- ML price prediction
- finance intelligence
- WhatsApp
- Telegram
- purchase feedback
- offer engine
- coupon engine

Phase 1 builds the foundation that makes those features safe to add later.

---

# 46. Architecture Summary

Final Phase 1 core:

auth.users
    │
    ▼
profiles
    │
    ▼
watch_intents
    │
    ├──────── watch_listing_targets
    │
    ▼
canonical_products
    │
    ├──────── canonical_variants
    │
    ▼
merchant_listings
    │
    ├──────── listing_variants
    │
    ├──────── listing_observations
    │
    └──────── listing_variant_observations
    │
    ▼
watch_evaluation_state
    │
    ▼
notifications
    │
    ▼
notification_deliveries

Supporting:

categories
brands
merchants
notification_preferences
feature_flags
user_feature_entitlements

This model is the foundation for Phase 2 product discovery and Phase 3 multi-merchant tracking.

