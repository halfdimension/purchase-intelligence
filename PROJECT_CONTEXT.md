# Purchase Intelligence — Project Context

Last major architecture review: 2026-09-27

This file is the durable source of truth for AI assistants and developers working on this repository.

Before making architectural changes, read this file and `AGENTS.md`.

Detailed architecture references:

- `docs/phase-1-domain-architecture.md` — implemented Phase 1 identity,
  catalog, observation, watch, notification, and RLS foundation
- `docs/phase-1-new-product-ingestion.md` — implemented durable request and
  trusted new-product ingestion path
- `docs/phase-2-general-purchase-intelligence.md` — target design and ordered
  roadmap for general discovery, comparison, tracking, and purchase
  intelligence

Status language used by this document:

- **IMPLEMENTED / VERIFIED** means the behavior exists and has been exercised
  in the repository or production path described.
- **CURRENT LIMITATION** means the constraint exists in today's runtime.
- **TARGET / FUTURE** means product or architecture direction, not a claim that
  the capability exists.

---

# 1. Product Vision

Purchase Intelligence is intended to become a personal purchase-intelligence platform rather than a simple URL price tracker.

The long-term user experience is:

1. User creates an account and logs in.
2. Application asks what the user wants to buy.
3. User describes a product/category, for example:
   - running shoes
   - headphones
   - phone
   - watch
   - clothes
4. Application helps refine the request:
   - brand
   - category
   - specifications
   - variant
5. Application discovers real products from supported sources.
6. Products are shown with strong visual UX:
   - images
   - names
   - prices
   - variants
   - availability
   - merchant information
7. User selects the desired product.
8. Application discovers merchant listings for the same canonical product.
9. User chooses:
   - one merchant,
   - multiple merchants,
   - or eventually "track wherever cheapest".
10. User defines relevant purchase conditions:
    - target price
    - size
    - color
    - storage
    - other variant requirements
11. System continuously monitors the listing(s).
12. User receives useful alerts when buying conditions become attractive.
13. User can later record whether they purchased the item and how they liked it.
14. Purchase history can later improve personalization and recommendations.

The user should normally NOT need to paste a product URL.

---

# 2. Intended Users

Initial real users:

- project owner
- family
- friends
- public testers through a shared link

This is not intended to remain a single-user script.

The application should therefore support:

- accounts
- per-user watchlists
- per-user preferences
- per-user notification settings
- optional personal finance settings
- purchase history
- administrative capabilities

---

# 3. Product Categories

The architecture should not be shoe-specific.

Target categories include:

- shoes
- headphones
- phones
- watches
- clothes
- other consumer products

Category-specific attributes differ.

Examples:

Shoes:
- size
- color
- gender

Phones:
- RAM
- storage
- color

Clothing:
- size
- color
- fit

Headphones:
- color
- bundle/version

Therefore long-term architecture must use generic product/variant attributes rather than only `desired_size`.

---

# 4. Core Domain Model Direction

Long-term domain concepts must be separated.

A canonical product is NOT the same as a merchant webpage.

Target conceptual model:

User
  ↓
Watch Intent
  ↓
Canonical Product
  ↓
Product Variant
  ↓
Merchant Listing
  ↓
Listing Observation / Historical Snapshot

Example:

Canonical product:
Soundcore Q20i

Merchant listings:
- Amazon Q20i
- Flipkart Q20i
- Soundcore official Q20i

All may represent the same actual product.

Another example:

Canonical product:
Nike Pegasus Premium

Listing:
Nike official product page

Variants:
- UK 7
- UK 8
- UK 9
- etc.

This separation is a major architectural requirement.

## Official source is a first-class concept

When available, the official brand/manufacturer source is the preferred
catalog reference and should be presented before alternative merchants.

Examples:

- Nike product -> Nike official first
- Adidas product -> Adidas official first
- MacBook -> Apple official first
- Samsung phone -> Samsung official first
- Levi's product -> Levi's official first

Official status and lowest price are separate dimensions. The product should
eventually show the official price, best supported market price, difference
from official, historical low, and user target without implying that the
official source is cheapest.

Official data may be higher-confidence evidence for canonical name, model,
manufacturer identifiers, specifications, official variants, and images.
Alternative merchants primarily contribute price, availability, seller,
offers, delivery, and merchant-specific variant data.

`brands.official_url` exists today, but the current schema does not yet model
the official relationship between a brand/product and a merchant listing.
That relationship is part of the next domain-generalization milestone.

## Generic attributes and dynamic variants

Product and variant representation must remain category-agnostic. Do not add
columns such as `shoe_size`, `phone_storage`, `phone_ram`, `shirt_size`, or
`laptop_gpu`. Prefer normalized structured attributes.

Examples:

```json
{"color":"Titanium Black","storage":"512 GB","ram":"12 GB"}
```

```json
{"color":"Black/White","size":"UK 9"}
```

Category schemas may describe common attribute axes, but they are guidance,
not a rigid limit on what can be stored.

The future frontend must derive controls from the actual purchasable variant
matrix. An attribute with several values becomes a selector; an attribute
with one value is displayed as a specification. A selection must resolve to a
real variant combination rather than an invented Cartesian product.

---

# 5. Product Discovery Architecture

The final product should support guided discovery instead of URL-first tracking.

Example interaction:

User:
"I want running shoes"

System:
"What brand?"

User:
"Adidas"

System:
Shows relevant Adidas running shoes with images and current information.

User selects a shoe.

System:
Finds merchant listings for that canonical product.

User chooses listing(s), variant and target price.

Tracking begins.

Discovery providers should normalize external data into an internal model.

Possible provider interface direction:

- search products
- fetch product
- fetch variants
- fetch availability
- fetch prices
- fetch offers

Potential adapters may include:

- Nike
- Adidas
- ASICS
- Amazon
- Flipkart
- Myntra
- AJIO
- other merchants

Do not expose merchant-specific scraping structures directly to the frontend.

The target entry point is natural product search rather than a URL. Examples
include `S26 Ultra`, `MacBook Pro M4 Pro`, `Soundcore Q20i`, `Nike Pegasus 42`,
`Levi's jeans`, or a broad category such as `headphones`.

Interactive discovery should be hybrid:

Fast path:
- search the existing normalized catalog
- use lightweight supported provider endpoints where available
- return usable results quickly

Asynchronous enrichment:
- create durable discovery work when Playwright or expensive retrieval is
  required
- let a background worker retrieve, normalize and persist candidates
- let the frontend poll or refresh instead of blocking one web request

The durable `tracking_requests` architecture is the proven precedent for this
kind of user-owned request plus trusted-worker processing.

Cross-store matching must prefer deterministic evidence in this order:

1. GTIN, EAN, or UPC
2. manufacturer model/part number
3. official product identifiers
4. normalized brand, model, specifications, and variant attributes
5. ML/embedding assistance when deterministic identity is insufficient
6. an unresolved/manual-review state when confidence is inadequate

An LLM must not be the sole product-identity authority, and uncertain products
must not be silently merged.

---

# 6. What Should Eventually Be Tracked

Useful purchase intelligence may include:

- current selling price
- MRP
- historical price
- selected variant availability
- all variants
- stock quantity when exposed
- discounts
- coupons
- bank offers
- cashback
- delivery fees
- sale events
- merchant/seller
- effective final price

A major future concept is:

effective_price =
selling price
- usable discounts
- coupons
- bank offers
+ unavoidable fees

---

# 7. Alert Philosophy

The system should send helpful alerts, not event spam.

Possible underlying events:

- price changed
- selected variant restocked
- historical low reached
- coupon appeared
- bank offer appeared
- target price reached
- effective price reached target

These should be combined into meaningful user notifications where possible.

Example:

"UK 9 is back in stock and the price dropped from ₹19,295 to ₹17,999, below your ₹18,000 target."

Primary stable channel:
- email

Future optional/beta channels:
- push
- Telegram
- WhatsApp

Experimental channels should be feature-flagged.

---

# 8. Admin / Feature Flags

Project owner should eventually have a `super_admin` role.

Suggested roles:

- user
- admin
- super_admin

Experimental features should NOT be enabled through hardcoded emails.

Use feature flags / entitlements.

Potential beta features:

- WhatsApp notifications
- Telegram notifications
- finance intelligence
- experimental AI capabilities

Admin should be able to enable features per user.

---

# 9. BUY / WAIT Intelligence

Do not make BUY / WAIT purely an LLM opinion.

Target layered architecture:

Layer 1:
deterministic rules

Examples:
- desired variant available?
- target price reached?
- historical low?
- effective price below threshold?

Layer 2:
statistical intelligence

Examples:
- price percentile
- historical median
- frequency of previous drops
- recent price trend
- stock pressure

Layer 3:
ML when sufficient data exists

Possible future models:
- price-drop probability
- sale-cycle detection
- stock-out probability
- deal-quality scoring
- recommendation ranking

Layer 4:
LLM explanation

The LLM should explain recommendations grounded in real computed data rather than inventing prices/products.

---

# 10. AI / ML Direction

Useful AI applications:

## Conversational discovery

Convert natural language:

"I need daily running shoes under ₹10,000"

into structured intent such as:

category = running shoes
budget <= 10000
use_case = daily running

Real discovery providers then retrieve actual products.

## Canonical product matching

Help determine whether differently named listings correspond to the same real-world product.

## Recommendation explanations

Explain why the deterministic/statistical engine produced BUY or WAIT.

## Personalization

Later use purchase history and explicit feedback to improve ranking.

ML should only be introduced when sufficient real data exists.

The near-term strategy is hybrid, not “ML controls everything”:

```text
raw merchant data
    -> trustworthy structured extraction
    -> deterministic parsing and normalization
    -> category classification
    -> attribute extraction
    -> entity matching/ranking
    -> canonical catalog
```

Structured merchant data and deterministic identifiers/rules come first. ML
may assist classification, attribute extraction, and uncertain matching, but
must return evidence/confidence and must not invent products, prices, stock,
or offers. Do not train a custom model now; there is not enough labeled data.

Collect real raw inputs, normalized outputs, identity evidence, confidence,
and later corrections so a future training decision can be data-driven. A
local open-source/pretrained model in an ephemeral worker is acceptable only
when it materially improves a measured task and remains within the zero-cost
constraint.

---

# 11. Optional Personal Finance Intelligence

Finance intelligence is an optional "Labs"/beta capability.

It must not be required for normal product tracking.

Potential voluntary inputs:

- discretionary budget
- salary cycle
- planned expenses
- purchase priority

Example future recommendation:

"The product price is excellent, but buying now would use most of the discretionary budget you configured for this month."

Financial information must remain isolated from ordinary tracking where possible.

---

# 12. Purchase History

After an alert, the product can later ask:

"Did you buy it?"

If yes, useful optional data includes:

- purchase price
- merchant
- variant
- purchase date
- coupon used
- final effective price
- rating
- returned?
- reason for return
- likes/dislikes

This data can later improve personalization.

---

# 13. Frontend Direction

The current UI is a functional prototype, not the final UX.

Long-term UX should feel like a polished shopping/research product.

Core areas may eventually include:

- Discover
- Watchlist
- Product details
- Merchant comparison
- Price history
- Offers
- Recommendations
- Purchases
- Settings
- Labs
- Admin

The user should primarily interact through guided discovery and rich product cards rather than manual URL entry.

---

# 14. Long-Term Monitoring Architecture

Current monitoring uses GitHub Actions every two hours.

That is intentional for the prototype.

It is NOT the final scale architecture.

At larger scale the system should move toward:

Scheduler
  ↓
Job Queue
  ↓
Crawler Workers
  ↓
Normalized Observations
  ↓
Database
  ↓
Watch Evaluation
  ↓
Notification Engine

Important optimization:

If 50 users track the same merchant listing:

WRONG:
50 independent crawls

CORRECT:
1 listing crawl
→ evaluate result against 50 watch intents

Crawler scheduling should therefore eventually operate on unique merchant listings rather than user watches.

The current Phase 1 scheduler already resolves unique active merchant listing
targets from watch intents. Broader distributed-systems evolution must remain
evidence-driven:

```text
start simple
    -> measure
    -> identify the actual bottleneck and cause
    -> introduce one targeted architectural change
    -> measure again
```

Possible future changes include a search service for measured search
CPU/latency, a durable queue and worker pool for crawler throughput, a cache
for demonstrated repeated-read cost, a dedicated search engine when
PostgreSQL search no longer fits, an image CDN for real media pressure, and an
API gateway/load balancer when independently deployed or replicated services
require them.

Do not add microservices or another datastore merely to appear scalable.
Polyglot persistence must answer a concrete access pattern and operational
need. ImageKit or similar media infrastructure is not a background-compute
platform.

---

# 15. Current Technology

Frontend / web backend:
- Next.js
- TypeScript
- Tailwind
- App Router

Database:
- Supabase/PostgreSQL

Current crawler:
- Python
- requests
- BeautifulSoup
- Playwright

Notifications:
- Resend email

Automation:
- GitHub Actions

Repository:
- GitHub repository `halfdimension/purchase-intelligence`

Production web application:
- `https://purchase-intelligence-lilac.vercel.app`

Current responsibility split:

- Vercel: web frontend and lightweight Next.js APIs
- Supabase/PostgreSQL: Auth and durable relational/domain data
- GitHub Actions: scheduled ingestion and monitoring workers
- Python + Playwright: crawling and trusted background processing
- Resend: email delivery
- GitHub: durable source and deployment history

## Zero-cost constraint

The personal/prototype stage has a hard deployment/runtime budget of **₹0**.

Current zero-cost-oriented choices are:

- Vercel free tier
- Supabase free tier
- GitHub Actions
- Python + Playwright in ephemeral workers
- Resend free tier
- deterministic rules and, only when useful, open-source/pretrained inference
  in ephemeral workers
- external merchant image URLs initially

Core functionality must not require a paid hosted LLM, paid inference API, or
other paid service. If a feature cannot fit legitimate free-tier limits,
reduce scope, run it less often, choose a local/free design, or defer it.
Free-tier quotas and terms are constraints to respect, not limits to evade
with fake or multiple accounts.

---

# 16. Current Implemented and Proven State

The following is **IMPLEMENTED / VERIFIED** in the current private production
application.

## Authentication and private dashboard

- Supabase Auth owns authentication identity.
- Public signup is intentionally disabled for the current personal deployment.
- Existing-account sign in and sign out are production-verified.
- `/` checks `/api/auth/me` before showing the dashboard and redirects an
  unauthenticated visitor to `/login` without flashing private content.
- The dashboard reads and deletes authenticated Phase 1 `watch_intents`.

## Current tracking setup flow

- The user submits a Nike India product URL, optional UK size, and optional
  target price.
- An already-indexed listing creates a Phase 1 watch immediately.
- An unknown supported URL creates a durable `tracking_request`.
- The scheduled ingestion worker claims one request, validates it again,
  scrapes through the Nike adapter, bootstraps normalized catalog records and
  observations, then atomically materializes the watch.
- Processing leases, expired-request reclaim, attempt fencing, idempotent
  persistence, and ambiguous-outcome reconciliation are implemented.
- The frontend shows pending/processing setup state, polls request status, and
  reloads the Phase 1 watchlist after completion.

## Nike crawler

Nike India supported through retailer-specific extraction.

Current test product:

Nike Pegasus Premium Men's Road Running Shoes

Crawler extracts:

- name
- brand
- currency
- MRP
- selling price
- product image
- overall stock
- size variants
- stock quantity when exposed

Requests may receive HTTP 403, so Playwright Chromium is used for rendered-page extraction.

## Product variants

Nike size variants are persisted.

Current tested variants include UK sizes and availability.

## Historical prices

Each monitoring run persists Phase 1 listing and listing-variant observations.
The migration-window compatibility write also inserts a legacy
`price_snapshots` row.

Price-history API exists:

`GET /api/products/[id]/history`

It returns:

- historical observations
- lowest observed price
- highest observed price
- latest price
- snapshot count

Frontend includes a price-history visualization, but its current API still
reads legacy `price_snapshots`. Migrating that read path to Phase 1
observations is required before Phase 0 cleanup.

## Alerts

Phase 1 watch evaluation currently considers:

- desired size availability
- target price

The production workflow runs with Phase 1 notifications authoritative and the
Phase 0 evaluator/email path disabled. A false -> true transition can create
and deliver an alert. A true -> true evaluation suppresses duplicate alert
spam. A true -> false transition resets the condition so a later false -> true
transition can notify again.

Logical notification uniqueness, one delivery row per notification/channel,
delivery claiming, retryable failure state, and provider idempotency are
implemented. Actual Resend delivery has been verified in production.

## Cloud automation

- `.github/workflows/phase1-ingestion.yml` runs on manual dispatch and at
  minutes 7, 22, 37, and 52 each hour. It invokes
  `python -m crawler.run_phase1_ingestion`.
- `.github/workflows/price-check.yml` runs on manual dispatch and every two
  hours at minute 17. It invokes `python -m crawler.run_tracked` with Phase 1
  notifications authoritative.
- Both use GitHub-hosted Ubuntu, Python 3.14, and Playwright Chromium.
- The laptop does not need to remain on.

## Recent production cutover checkpoints

- `2f9a636` — Add Phase 1 ingestion runner
- `0bdc664` — Fix Phase 1 Nike variant identity handling
- `13a8203` — Schedule Phase 1 ingestion worker
- `befcefa` — Cut homepage over to Phase 1 tracking
- `346b7d8` — Make authentication sign-in only
- `a8e14df` — Protect dashboard and add sign out

## Current limitations

The following is **CURRENT LIMITATION**, not hidden future behavior:

- User-facing discovery is URL-first and supports Nike India only.
- The form, compatibility view model, ingestion variant resolver, and
  evaluator still assume a shoe `size`; the UI hardcodes UK-size options.
- The ingestion adapter boundary exists, but normal monitoring still contains
  direct Nike/generic scraper selection rather than one complete shared
  merchant-adapter framework.
- There is no official-source role model, general search, category
  classification pipeline, dynamic variant UI, cross-store matching, or
  multi-merchant comparison UX yet.
- Phase 0 tables and selected compatibility writes/reads remain active.

---

# 17. Current Database Evolution

Migrations `005` through `021` add the Phase 1 model alongside the Phase 0
prototype.

Implemented Phase 1 domain areas:

- Supabase Auth-backed `profiles`
- `categories` and `brands`
- `canonical_products` and `canonical_variants`
- `merchants`, `merchant_listings`, and `listing_variants`
- immutable `listing_observations` and `listing_variant_observations`
- `watch_intents`, listing targets, and evaluator state
- notifications, delivery state, preferences, flags, and entitlements
- durable `tracking_requests` with trusted claim, lease, reclaim, catalog
  bootstrap, and watch-materialization RPCs
- RLS and column privileges separating user-owned data from crawler-owned
  catalog and worker state

The populated Nike Phase 0 chain was backfilled into Phase 1, and later a
previously unknown real Nike product was ingested into the new catalog and
picked up automatically by normal monitoring.

The following legacy tables still exist for compatibility:

- `products`
- `product_variants`
- `price_snapshots`
- `watchlists`
- `watch_alert_state`

Do not deepen dependencies on them. In particular, Phase 0 `products` mixes
canonical-product and merchant-listing concerns, `desired_size` is
category-specific, and ownership is email-based. Normal Phase 1 monitoring is
authoritative for watch evaluation and notifications, but Phase 0 product
persistence and the legacy price-history read path remain during the migration
window.

Do not drop legacy tables until replacement reads/writes are verified and an
explicit cleanup migration is approved.

---

# 18. Architecture Phases

This section preserves the chronological Phase 0/Phase 1 implementation
record. Statements inside a milestone describe the state at that milestone;
sections 16, 17, and 19 are authoritative for current state and next work.

## Phase 0 — Working Vertical Slice

Status: substantially complete.

Proves:

- frontend
- Supabase
- Nike scraping
- price persistence
- historical snapshots
- variant availability
- watch evaluation
- Resend email
- deduplication
- GitHub Actions

## Phase 1 — Identity, Domain, Ingestion, and Authenticated Runtime

Status: **IMPLEMENTED / VERIFIED for the active production path; legacy
compatibility cleanup remains.**

Completed:

- Phase 1 domain architecture documented
- migration `005_phase1_catalog_identity.sql`
- profiles/catalog/listing foundation created in Supabase
- RLS enabled on the new Phase 1 foundation
- migration `006_phase1_observations.sql`
- listing and listing-variant historical observation tables created
- RLS enabled on observation tables
- migration `007_phase1_watch_notifications.sql`
- watch-intent and notification domain created
- feature flags and per-user entitlements created
- RLS enabled on Milestone 2 tables
- initial experimental feature flags inserted disabled by default
- legacy Phase 0 tables verified intact

Milestone 3 progress:

- Milestone 3A Auth profile trigger installed
- first real Supabase Auth user created
- automatic `auth.users` -> `public.profiles` creation verified end-to-end
- Auth user UUID and profile UUID verified identical
- new profile defaults to role `user`
- Milestone 3B profile RLS installed and verified
- authenticated users can read only their own profile
- authenticated users can update only `display_name` and `avatar_url`
- authenticated users cannot update `role`, `email`, or `id`
- cross-user profile visibility verified as blocked
- Milestone 3C catalog read RLS installed and verified
- authenticated users have read-only access to shared catalog tables
- active catalog records are visible to authenticated users
- inactive merchants, hidden products and inactive listings/variants are blocked
- authenticated users have no catalog INSERT, UPDATE or DELETE privileges
- positive and negative catalog RLS paths verified with rollback-only test fixtures
- Milestone 3D per-user watch ownership RLS installed and verified
- authenticated users can create, read, update, and delete only their own watch intents
- watch `user_id` and `product_id` are immutable after creation
- authenticated users can manage listing targets only for their own watches
- listing targets must reference listings for the same canonical product as the watch
- watch listing target ownership correctly inherits through `watch_id`
- authenticated users can read evaluator state only for their own watches
- authenticated users cannot insert, update, or delete evaluator state
- cross-user watch, target, evaluator visibility and modification were verified as blocked
- Milestone 3E notification and feature-entitlement RLS installed and verified
- authenticated users can read, create, and update only their own notification preferences
- notification preference ownership cannot be changed
- push, Telegram, and WhatsApp preferences are entitlement-gated
- enabling an experimental notification channel without entitlement is blocked
- enabling the channel succeeds after a valid entitlement is granted
- authenticated users can read only their own notifications and delivery state
- authenticated users cannot create or modify notifications or provider delivery state
- authenticated users can read shared feature definitions but cannot modify them
- authenticated users can read only their own feature entitlements
- authenticated users cannot grant, revoke, or modify feature entitlements
- cross-user preference, notification, delivery, and entitlement visibility verified as blocked
- substantial Phase 1 RLS/database-security work is complete

Milestone 5 — Phase 1 data backfill:

- migration `013_phase1_backfill_nike_prototype.sql` created
- migration dry-run executed successfully inside a transaction with rollback
- real migration executed successfully and committed
- existing populated Nike Pegasus Premium Phase 0 chain backfilled
- 1 canonical product created
- 1 Nike India merchant listing created
- 6 canonical variants created
- 6 merchant listing variants created
- 14 historical Phase 0 price snapshots preserved as listing observations
- legacy watch mapped to the authenticated profile
- UK 9 watch mapped to the canonical UK 9 variant
- target price of 18000 INR preserved
- specific Nike listing target created
- legacy watch evaluation/deduplication state preserved
- email notification preference created
- post-migration row counts verified
- two unused/empty Phase 0 prototype product rows intentionally not migrated
- Phase 0 tables remain intact and current Phase 0 runtime behavior has not been cut over

Milestone 6 — Phase 1 crawler persistence:

Status: COMPLETE for the controlled Phase 1 cutover.

- new `crawler/phase1_database.py` persistence layer added
- existing Phase 1 merchant listing is resolved by URL during controlled cutover
- crawler updates Phase 1 merchant-listing latest state
- crawler inserts immutable listing observations
- crawler updates all existing merchant listing variants
- crawler inserts immutable listing-variant observations
- one shared `checked_at` timestamp is used for a complete crawl persistence event
- `save_product_phase1()` provides the Phase 1 persistence entry point
- normal crawler execution performs Phase 0 persistence plus Phase 1 persistence during the migration window
- Phase 1 shadow-write failures do not prevent the existing Phase 0 evaluator/notification path from running
- the overall crawler job exits non-zero after processing if a Phase 1 persistence write failed
- Phase 1 crawl-target resolution is now driven by active `watch_intents`
- `specific_listing` and `selected_listings` use `watch_listing_targets`
- `any_listing` resolves active merchant listings for the watched canonical product
- crawl targets are deduplicated so the same merchant listing is crawled only once
- inactive listings and inactive merchants are excluded
- Phase 0 and Phase 1 crawl-source parity was verified before switching scheduling
- normal `crawler.run_tracked` now obtains crawl work from Phase 1 instead of Phase 0 `watchlists/products`
- real Phase 1-driven run verified with one Nike listing, six variants, one listing observation, and six variant observations
- runtime verified with `Succeeded: 1`, `Failed: 0`, and zero Phase 1 failures
- Phase 1 persistence can still operate in migration/shadow mode when required
- production notification execution has now moved to Phase 1 under Milestone 7
- Phase 0 product persistence is still retained temporarily during the migration window
- checkpoint commits:
  - `bbfbcb2` — `Add Phase 1 crawler shadow persistence`
  - `5fd6399` — `Drive crawler scheduling from Phase 1 watches`

Milestone 7 — Phase 1 watch evaluation and notification cutover:

Status: COMPLETE.

- `crawler/phase1_evaluator.py` evaluates Phase 1 `watch_intents`
- current evaluator supports the controlled shoe-size requirement used by the Nike prototype
- unsupported future variant requirements fail explicitly rather than being silently mis-evaluated
- `crawler/phase1_notification_policy.py` owns false/true transition policy
- false -> true creates a notification opportunity
- true -> true suppresses duplicate notification delivery
- true -> false resets the condition so a later false -> true transition may notify again
- `crawler/phase1_notification_builder.py` creates normalized logical notification drafts
- logical notifications use stable deduplication keys
- migration `014_phase1_notification_dedupe.sql` adds database-level notification deduplication
- `crawler/phase1_notification_database.py` provides idempotent get-or-create notification persistence
- migration `015_phase1_notification_delivery_dedupe.sql` prevents duplicate delivery rows per notification/channel
- `crawler/phase1_delivery_database.py` implements delivery claiming/lease semantics
- stale pending deliveries can be reclaimed
- sent/delivered states are terminal
- failed deliveries remain retryable
- `crawler/phase1_email.py` provides Phase 1 Resend email delivery
- Resend provider idempotency is keyed by persisted notification id
- `crawler/phase1_notification_delivery.py` orchestrates delivery claiming, provider execution and delivery-state persistence
- `crawler/phase1_watch_processor.py` composes evaluation, transition policy, notification creation, delivery and evaluation-state persistence
- evaluation state and notification metadata advance only after notification execution is complete
- provider failures leave the watch transition available for retry
- email-disabled watches advance logical evaluation state without falsely updating `last_notified_at` or `last_notified_effective_price`
- `crawler/notification_runtime.py` provides explicit notification runtime modes
- `shadow` mode keeps Phase 0 notifications authoritative while Phase 1 evaluates without sending
- `phase1` mode makes Phase 1 notifications authoritative and disables the Phase 0 evaluator/email flow
- runtime modes were verified to be mutually exclusive
- real Nike crawler smoke test verified `phase1` runtime mode with Phase 0 notification functions blocked
- controlled real-database false -> true integration test verified:
  - real Phase 1 notification-row creation
  - real notification-delivery-row creation
  - delivery transition to `sent`
  - watch evaluation state transition to true
  - `last_notified_at` persistence
  - notified effective price persistence
  - external Resend call safely mocked
  - complete database cleanup and exact baseline restoration afterward
- scheduled GitHub Actions workflow now sets `PURCHASE_INTELLIGENCE_NOTIFICATION_MODE: phase1`
- production workflow-dispatch run `33295034636` completed successfully
- production run verified:
  - notification runtime mode `phase1`
  - one Phase 1 crawl target
  - Nike HTTP/browser extraction succeeded
  - six variants extracted
  - Phase 1 persistence succeeded
  - Phase 1 watch evaluation succeeded
  - current watch remained false because UK 9 was out of stock
  - Phase 0 evaluator/notification flow was disabled
  - crawler completed with one success and zero failures
- Phase 1 failure behavior is fail-safe in production mode:
  - no fallback into Phase 0 notifications
  - job exits non-zero
- shadow-mode fallback behavior remains available for controlled migration/debug use
- crawler runtime logging was updated so production Phase 1 execution is no longer mislabeled as shadow execution
- checkpoint commits include:
  - `24ac2ea` — `Add Phase 1 watch evaluation foundation`
  - `61e648b` — Phase 1 notification dedupe migration
  - `9072a36` — Phase 1 notification persistence
  - `5a63102` — Phase 1 delivery lease persistence
  - `2890b0e` — Phase 1 email delivery orchestration
  - `724e1af` — Phase 1 watch processing pipeline
  - `963bc97` — Phase 1 notification shadow mode
  - `0259801` — Phase 1 watch evaluation in crawler shadow mode
  - `6198148` — notification runtime cutover mode
  - `4017ec1` — runtime cutover wiring
  - `ff69b85` — preserve notification metadata when email is disabled
  - `41d5e01` — cut over scheduled notifications to Phase 1
  - `149ee42` — clarify Phase 1 crawler runtime logging

Milestone 8/9 — Authenticated web/API cutover:

Status: COMPLETE for the current private production application.

Completed:

- Supabase SSR authentication foundation added for Next.js
- authenticated login, logout and signup API routes added
- authenticated session verification through `/api/auth/me`
- email-confirmation callback route added
- login/signup UI added
- authenticated profile API added through `/api/profile/me`
- homepage alert identity now comes from the authenticated account profile
- authenticated Phase 1 watch API added at `/api/watch-intents`
- Phase 1 watch reads return:
  - watch intent
  - canonical product
  - canonical variant
  - merchant listing
  - merchant
  - listing variants
  - current variant stock/price
  - evaluator state
- homepage watch READ path migrated from legacy `/api/watchlist` to `/api/watch-intents`
- compatibility adapter added so the existing prototype cards can render Phase 1 data during cutover
- authenticated Phase 1 watch creation implemented for listings already present in the Phase 1 catalog
- Phase 1 POST runtime paths verified:
  - duplicate watch -> 409
  - unknown/unindexed URL -> 422
  - valid indexed listing/variant -> 201
- authenticated Phase 1 DELETE endpoint added at `/api/watch-intents/[id]`
- DELETE ownership is enforced through authenticated user identity and RLS
- temporary UK 7 watch creation/deletion was verified end-to-end
- homepage Remove button migrated to the Phase 1 DELETE endpoint
- homepage watch DELETE flow verified end-to-end without affecting the existing UK 9 watch
- homepage CREATE first uses the indexed Phase 1 watch path and then creates a
  durable `tracking_request` for an unknown supported Nike URL
- pending/processing setup state is displayed and polled
- completed setup reloads the normal Phase 1 watchlist
- public signup is intentionally disabled; authentication is sign-in only
- `/` verifies `/api/auth/me` before rendering private content
- sign out uses `/api/auth/logout`
- production sign-in/sign-out and dashboard protection are verified
- recent checkpoints:
  - `f58317c` — `Migrate homepage watch reads to Phase 1`
  - `3a355ba` — `Show account email for watch alerts`
  - `1eb41c8` — `Add authenticated Phase 1 watch creation`
  - `1fbefcb` — `Add authenticated Phase 1 watch deletion`
  - `9f35bac` — `Migrate homepage watch deletion to Phase 1`

Current intentional compatibility state:

- homepage READ, CREATE, and DELETE use the Phase 1 domain path
- indexed listings create watches synchronously through
  `POST /api/watch-intents`
- unindexed supported Nike URLs stage work through authenticated
  `POST /api/tracking-requests`
- the trusted Phase 1 ingestion worker is scheduled and can bootstrap the
  catalog and materialize the resulting watch
- the client remains user-scoped and cannot mutate crawler-owned catalog data
- legacy Phase 0 tables remain intact
- monitoring still performs Phase 0 product/snapshot compatibility writes
- price-history UI still uses the legacy `price_snapshots` API

Keep Phase 0 tables intact until required historical-read and compatibility
paths have Phase 1 replacements and the production cutover is observed.

## Phase 2 — General Purchase Intelligence

Status: **TARGET / FUTURE.**

The target is search-first discovery, generic product/variant understanding,
official-source-first comparison, multi-merchant offers, generalized tracking,
and grounded purchase intelligence. The detailed architecture and dependency
order are in `docs/phase-2-general-purchase-intelligence.md`.

## Phase 2 dependency order

The implementation order is intentional:

1. **Generalize the domain model** — remove remaining Nike/shoe assumptions;
   clarify brand, category, merchant/source role, official-source metadata,
   and generic product/variant attributes while preserving production.
2. **Merchant adapter framework** — derive a shared boundary from current code
   and refactor Nike behind it.
3. **Classification and normalization** — deterministic category detection,
   category schemas, and generic attribute normalization; ML fallback later.
4. **Discovery/search backend** — catalog search, supported provider discovery,
   and durable asynchronous enrichment for expensive work.
5. **Search-first homepage and result cards** — retain URL ingestion as an
   advanced/fallback path initially.
6. **Dynamic variant selection** — render controls from normalized variant
   metadata instead of hardcoding shoe size.
7. **Product detail and official-first comparison** — present the official
   source prominently and alternatives separately; official and cheapest stay
   distinct.
8. **Second, very different category/source** — use an electronics example to
   prove that one architecture handles footwear and electronics without
   schema/UI redesign.
9. **Cross-store entity resolution** — deterministic identifiers first,
   normalized specifications next, ML/embedding assistance only where needed.
10. **Generalized tracking** — official only, selected merchants, or all
    supported merchants/best supported offer.
11. **Purchase intelligence** — official-versus-market price, history,
    historical low, target distance, stock comparison, and grounded BUY/WAIT
    reasoning.
12. **Scale from real evidence** — add observability and introduce queues,
    caches, search infrastructure, services, gateways, or load balancing only
    for measured bottlenecks.
13. **Legacy cleanup** — remove Phase 0 paths only after their replacements are
    proven.

Later optional work includes purchases/feedback, personalization, finance
Labs, additional notification channels, and admin tooling. It must not jump
ahead of the catalog/discovery/tracking dependency chain.

---

# 19. Immediate Next Step

The next engineering milestone after the 2026-09-27 documentation update is:

## Generalize the current catalog/domain model

Goal:

The same architecture must represent both:

```json
{
  "product": "Nike Pegasus 42",
  "variant_attributes": {
    "color": "Black/White",
    "size": "UK 9"
  }
}
```

and:

```json
{
  "product": "Samsung Galaxy S26 Ultra",
  "variant_attributes": {
    "color": "Titanium Black",
    "storage": "512 GB",
    "ram": "12 GB"
  }
}
```

without category-specific database columns or a Samsung-only/Nike-only shared
frontend model.

This milestone should:

- evolve the existing Phase 1 catalog rather than create a parallel schema;
- define stable generic product/variant attribute conventions;
- clarify category schema guidance and display metadata;
- represent merchant/source type and official brand/manufacturer relationship
  explicitly enough for later official-first behavior;
- keep official status independent from price rank;
- update shared normalized contracts so later UI code can consume attribute
  metadata instead of assuming `size`;
- use additive migrations with a production compatibility/backfill plan;
- preserve the current Nike ingestion, monitoring, evaluation, and alert path.

Definition of done should include a documented/migrated generic model,
footwear and phone fixtures or contract tests, no category-specific columns,
passing relevant validation, a verified production migration strategy, and
updated architecture documentation.

Do not bundle search, a second live merchant, custom ML, premature
microservices, or legacy-table deletion into this milestone.

Do not delete Phase 0 tables yet. Phase 0 product/snapshot compatibility and
the legacy price-history read must be replaced and verified before cleanup.

---

# 20. Historical Phase 1 Ingestion Record — 2026-09-05

This section preserves useful implementation evidence from the Phase 1
ingestion handoff. Its original “next work” and compatibility statements have
been updated below to reflect the later production cutover. Sections 16–19 and
`docs/phase-2-general-purchase-intelligence.md` are authoritative for current
status and future direction.

## Phase 1 New-Product Ingestion

Architecture reference:

`docs/phase-1-new-product-ingestion.md`

The ingestion boundary is:

authenticated user intent
→ `tracking_requests`
→ trusted Python crawler/worker
→ Phase 1 catalog bootstrap
→ real `watch_intent`
→ normal Phase 1 monitoring

The browser must remain user-scoped.

The browser/Next.js API must not use the Supabase
service-role key to manufacture catalog state.

Catalog truth remains crawler-owned.

## Milestone A — Tracking Request Foundation

Status: COMPLETE

Commit:

`133dc3a` — Add Phase 1 tracking requests

Completed and production-verified:

- `tracking_requests` table created
- authenticated users can SELECT only their own requests
- authenticated users can INSERT only user-controlled fields
- worker-owned processing fields are protected
- status defaults to `pending`
- attempt count defaults to `0`
- result IDs default to null
- RLS enabled
- positive own-user insertion verified
- cross-user insertion blocked
- authenticated worker-state spoofing blocked
- production table, policies and column privileges verified

User-controlled insert fields:

- user_id
- requested_url
- normalized_url
- variant_requirements
- target_price
- target_currency
- conditions

Worker-owned fields include:

- status
- attempt_count
- result_product_id
- result_listing_id
- result_watch_id
- error_code
- error_message
- started_at
- completed_at

## Milestone B — Authenticated Tracking Request API

Status: COMPLETE

Read endpoint commit:

`b923542` — Add authenticated tracking request reads

Submission endpoint commit:

`3300df6` — Add authenticated tracking request submission

Implemented:

`GET /api/tracking-requests`

Behavior verified:

- anonymous request -> 401
- authenticated request -> 200
- only current user's rows are read through RLS
- empty production table -> `{"requests":[]}`

Implemented:

`POST /api/tracking-requests`

Current request inputs:

- productUrl
- optional size
- optional targetPrice

Current Phase 1 submission behavior:

- unauthenticated -> 401
- malformed/missing URL -> 400
- invalid URL -> 400
- non-HTTP(S) URL -> 400
- URL containing credentials -> 400
- invalid/non-positive target price -> 400
- unsupported merchant -> 422
- already-indexed active listing -> 409
- unindexed supported Nike URL -> 202 + pending request

Current API-side supported host:

- nike.in
- subdomains of nike.in

This API-side host check is NOT authoritative crawler security.

The trusted worker must independently validate the merchant and
adapter again before any network access or catalog write.

The POST creates only user-owned staging data.

It does NOT:

- scrape the URL
- run Playwright
- create canonical products
- create canonical variants
- create merchant listings
- create listing variants
- create observations
- create a watch intent

Those remain trusted worker responsibilities.

Default request conditions currently match the existing watch flow:

- require_in_stock = true
- notify_target_price = target price was supplied
- notify_restock = true

Size normalization currently follows the existing UK-size convention.

## Milestone B Tests Completed

Verified:

- lint passes
- Next.js production build passes
- anonymous GET -> 401
- authenticated GET -> 200
- anonymous POST -> 401
- unsupported merchant -> 422
- missing URL -> 400
- malformed URL -> 400
- invalid target price -> 400
- credential-bearing URL -> 400
- existing indexed Nike Pegasus listing -> 409
- existing `/api/watch-intents` indexed path still resolves and
  correctly returns duplicate-watch 409
- unindexed Nike-shaped test URL -> 202
- new request returned:
  - status `pending`
  - attempt_count `0`
  - result IDs null
  - normalized UK 9 variant requirement
  - INR target currency
- authenticated GET read the created request
- disposable test requests were deleted afterward
- production `tracking_requests` table returned to zero rows

## Compatibility State

Homepage:

- READ -> Phase 1
- DELETE -> Phase 1
- CREATE -> Phase 1 indexed-watch path, with durable `tracking_requests` for
  unknown supported Nike URLs

Existing indexed-listing creation continues through:

`POST /api/watch-intents`

New unindexed supported URLs flow through:

`POST /api/tracking-requests`

The scheduled ingestion worker, pending/setup UI, and end-to-end production
flow are now implemented. Phase 0 tables and product/history compatibility
remain, but Phase 0 is no longer the authoritative watch/evaluator/notification
path.

## Milestone C — Trusted Crawler Request Processing

Status: COMPLETE

Completed implementation:

- migration `017_phase1_tracking_request_claim.sql`
- atomic PostgreSQL request claiming using
  `FOR UPDATE SKIP LOCKED`
- only the trusted service role may execute the claim function
- Python service-role claim wrapper added
- authoritative worker-side URL and merchant validation added
- supported ingestion target currently resolves:
  - merchant: `nike-india`
  - adapter: `nike`
  - hostname: `nike.in` or a valid subdomain
- worker rejects:
  - unsupported merchants
  - lookalike/suffix hosts
  - credential-bearing URLs
  - explicit ports
  - localhost/IP targets
  - malformed or encoded hostnames
- invalid claimed requests are persisted as `failed`
- failure updates are guarded by:
  - request id
  - `processing` status
  - exact `attempt_count`
- stale worker attempts therefore cannot overwrite a newer attempt
- orchestration now combines:
  - atomic claim
  - authoritative target validation
  - invalid-target failure persistence
- valid requests are returned as prepared ingestion work items
- this layer intentionally performs no scraping and no catalog writes

Milestone C checkpoints:

- `5ea63a1` — Add atomic tracking request claiming
- `d5921af` — Add tracking request claim wrapper
- `8ba1e81` — Add worker ingestion URL validation
- `432d42d` — Add tracking request failure persistence
- `c9e3c42` — Add tracking request worker preparation

Milestone C verification completed:

- empty production claim RPC verified
- positive pending -> processing claim verified
- processing -> failed persistence verified
- exact attempt-count stale-worker guard verified
- valid + invalid mixed worker batch verified
- valid Nike request remained prepared/processing
- invalid merchant request became failed
- disposable production test rows were removed
- production `tracking_requests` table returned to zero rows

The production Phase 1 crawler and notification execution path has
not been modified by Milestone C.

## Milestone D — Idempotent Catalog Bootstrap

Status: COMPLETE

Completed implementation:

- migration 018 added explicit observation `crawl_event_id`
  idempotency
- migration 019 added transactional
  `bootstrap_phase1_catalog(...)`
- migration 019 is applied in production
- bootstrap RPC is `SECURITY INVOKER` and service-role-only
- normalized Python bootstrap request/result contracts exist
- Nike `ProductData` payload construction remains in Python
- catalog persistence wrapper has been fake-client tested
- bootstrap request construction has been fake-tested
- merchant URL races, observation retries, variant identities and
  monotonic latest-state updates are handled transactionally

## Milestone E — Watch Materialization and Completion

Status: COMPLETE

Implemented:

- `crawler/phase1_ingestion_adapters.py` keeps generic worker
  orchestration separate from Nike scraper/payload/size behavior
- Nike targets must contain a recognizable non-empty `/p/<id>`
  merchant product identity before scraping
- Nike browser rendering guards top-level navigation against leaving
  the supported Nike India hostname family while allowing external
  subresources
- the scraped final `ProductData.url` is revalidated and must preserve
  the authoritative target product id; canonical path/name redirects
  for the same product id are accepted
- the trusted worker now performs:
  - adapter selection
  - authoritative normalized-URL scrape
  - `ProductData` bootstrap request construction
  - catalog bootstrap persistence
  - requested variant resolution
  - watch materialization
- crawl event identity is deterministic per request attempt
- `checked_at` comes from timezone-aware claim `started_at` and is
  normalized to UTC
- only ambiguous HTTP transport/request failures receive one safe
  retry with the exact same request identity
- deterministic PostgREST failures are not retried, and raw database
  or transport exceptions are never stored in user-readable request
  errors
- contract/invariant runtime failures remain operator-visible
- exhausted ambiguous transport attempts leave the request processing
  for reconciliation rather than manufacturing a terminal state
- migration `020_phase1_tracking_request_materialization.sql` adds
  atomic watch/target/request completion
- the new RPC is `SECURITY INVOKER` and service-role-only
- request ownership/settings are read from the locked
  `tracking_requests` row
- result/status mutation is guarded by request id, processing state
  and exact attempt count
- catalog product/listing/variant relationships are verified before
  watch creation
- duplicate worker materialization is serialized and produces stable
  `duplicate_watch` failure state instead of another watch
- completed materialization can be idempotently replayed after an
  ambiguous client response
- expected scrape, bootstrap, variant, and watch-materialization
  failures persist stable error codes
- the high-level ingestion processor claims exactly one request per
  invocation
- deterministic fake scraper, fake RPC and orchestration tests cover
  happy path, failures, wrong adapter/brand and retry behavior

Migration 020 real-database verification completed:

- the exact committed migration was rollback-tested against real
  Supabase PostgreSQL
- the rollback harness verified:
  - installation
  - `SECURITY INVOKER` and service-role-only privileges
  - successful watch materialization
  - `watch_listing_target` creation
  - tracking-request completion
  - completed-call idempotent replay
  - stale-attempt rejection
  - duplicate-watch handling and replay
  - transaction atomicity on a forced target failure
- rollback cleanup confirmed that no helper, function, trigger or test
  row remained
- the exact committed migration 020 was then applied permanently
- production privilege verification confirmed:
  - function installed: true
  - `SECURITY INVOKER`: true
  - `search_path`: `""`
  - `service_role` execute: true
  - `authenticated` execute: false
  - `anon` execute: false

State at Milestone E and later resolution:

- the browser/Next.js code still correctly has no service-role access
- `crawler.run_tracked` remains the monitoring runner rather than invoking
  new-product ingestion inline
- migration 021 later passed rollback/database and concurrent `SKIP LOCKED`
  verification and was applied
- the dedicated `crawler.run_phase1_ingestion` runner was added and scheduled
- homepage CREATE later cut over to the Phase 1 request flow
- Phase 0 product/history compatibility remains, but Phase 1 watch and
  notification execution is authoritative

## Milestone F — Real Ingestion and Monitoring Verification

Status: COMPLETE

Real product:

- Nike Pegasus 42 Men's Road-Running Shoes
- Nike external product id: `27763518`
- URL:
  `https://www.nike.in/nike-pegasus-42-men-s-road-running-shoes/p/27763518`
- no merchant listing existed by URL or external id before ingestion

Authenticated staging verification:

- `POST /api/tracking-requests` returned HTTP 202
- requested variant: UK 9
- target price: INR 13000
- initial state: `pending`, `attempt_count = 0`

Real ingestion-worker verification:

- guarded Nike browser scrape returned HTTP 200
- the final URL preserved `/p/27763518`
- product price/MRP was INR 13995
- seven variants, UK 6 through UK 12, were scraped
- `process_phase1_ingestion_requests(1)` completed successfully
- result identities:
  - `product_id`: `fb3bcf39-063a-47ba-beeb-0e3d8888ac98`
  - `listing_id`: `84505eb3-ae9f-499b-80dd-b0e582c21598`
  - `watch_id`: `db26593f-0714-4f5e-b3c3-3fa962c4a9c7`
  - `tracking_request_id`: `e2fb50d7-5aa7-4ad2-a8d3-d860f1e6186b`

Persistence verification:

- tracking request completed with `attempt_count = 1` and null
  `error_code`
- listing external id: `27763518`
- listing current price: INR 13995
- listing in stock: true
- active watch target: INR 13000
- variant requirements: `{"size":"UK 9"}`
- canonical variant: `size:uk-9` / UK 9
- seven listing variants
- one initial listing observation
- seven initial variant observations
- exactly one `watch_listing_target`

Normal monitoring integration verification:

- `get_phase1_crawl_targets` automatically discovered the new listing
- the normal Nike scraper completed successfully
- `save_product_phase1` created another normal observation
- `get_phase1_watches_for_listing` automatically found the new watch
- `process_phase1_watch`, with notification execution disabled,
  produced:
  - `condition_met = false`
  - transition `false -> false`
  - `notification_required = false`
  - `notification_created = false`
  - `state_persisted = true`
  - reason: `Current price ₹13,995 is above target ₹13,000.`
- output ended with `MILESTONE_F_MONITORING_TEST: PASSED`

Milestones D, E and F are complete.

## Milestone G — Processing Lease, Reclaim, and Reconciliation

Status: COMPLETE, DATABASE-VERIFIED, APPLIED, AND SCHEDULED

Implemented locally:

- additive migration `021_phase1_tracking_request_leases.sql`
- `tracking_requests.lease_expires_at` is the only new lease field
- PostgreSQL time is authoritative for lease issue, expiry, and renewal
- pre-021 processing rows with no lease become immediately reclaimable
- pending claims and expired-processing reclaims are atomic under
  `FOR UPDATE SKIP LOCKED`
- pending `created_at` and expired `lease_expires_at` share one fair
  eligibility-time order with `id` as the stable tie breaker
- reclaim increments `attempt_count`; that count remains the fencing
  generation for all tracking-request/watch materialization mutations
- terminal completed, failed, and cancelled requests are excluded from
  reclaim
- claim/reclaim/renew RPCs are `SECURITY INVOKER`, hardened with an
  empty search path, and executable only by `service_role`
- lease duration is centralized in
  `crawler/phase1_ingestion_policy.py`
- default lease is 600 seconds, configurable from 300 through 1200
  seconds with `PHASE1_INGESTION_LEASE_SECONDS`
- stage-boundary renewal occurs before browser scrape, catalog
  bootstrap, and watch materialization
- a twice-ambiguous renewal stops the worker before further side
  effects
- confirmed stale renew/failure/materialization is treated as internal
  ownership loss, not a user product failure
- ambiguous materialization reconciles same-attempt completed or
  duplicate-watch terminal state from `tracking_requests`
- ambiguous catalog bootstrap remains safely reclaimable/reprocessable
  under migration 019 idempotency and monotonic latest-state rules
- high-level ingestion remains exactly one request per invocation
- rollback-only PostgreSQL verification lives under `supabase/tests/`

The implementation intentionally has no maximum-attempt terminalization.
The earlier three-generation hypothesis was rejected because an expired
attempt may have committed valid catalog state immediately before dying,
all remaining steps are safely repeatable, and no production scheduling
data yet supports a failure threshold. Pending rows are ordered by
`created_at` and expired rows by `lease_expires_at`, so the oldest
eligible work wins with `id` as a stable tie breaker. Each reclaim issues
a fresh future deadline, preventing either a crash loop or an endless
stream of newer pending work from permanently monopolizing the queue.
Attempt counts must be observed during later scheduling and an
evidence-based dead-letter policy added separately if needed.

Migration 019 remains intentionally unfenced by tracking-request
generation. If attempt N's already-running bootstrap finishes after N+1
exists, its stable attempt event can add an older immutable observation,
but URL/catalog uniqueness prevents duplicate listing identity and
`checked_at` monotonic guards prevent older current-state overwrite.
The rollback harness covers both exact-event replay and an attempt N
making its first bootstrap only after N+1 persisted newer listing and
variant state. No concrete corruption risk was found and migrations
019/020 remain unchanged.

Completed after the original handoff:

- migration 021 passed the rollback-only Supabase integration harness
- rollback cleanup was verified
- real simultaneous-session `FOR UPDATE SKIP LOCKED` behavior was verified
- migration 021 was applied and its production schema/security state checked
- the one-request ingestion runner was added
- `.github/workflows/phase1-ingestion.yml` was enabled on a 15-minute schedule
- homepage CREATE, pending/setup polling, private dashboard protection, and
  sign-in/sign-out were cut over and verified

The exact next work is now the domain-generalization milestone in section 19,
not further Phase 1 ingestion cutover work. The one-request-per-invocation
limit remains an intentional prototype-scale policy until workload evidence
justifies batch or worker-pool changes.
