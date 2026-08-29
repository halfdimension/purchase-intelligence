# Purchase Intelligence — Project Context

Last major architecture review: 2026-08-29

This file is the durable source of truth for AI assistants and developers working on this repository.

Before making architectural changes, read this file and `AGENTS.md`.

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

---

# 16. Current Working Prototype

The following has been proven working.

## Watchlist

- persistent Supabase-backed watchlist
- product URL
- desired size
- target price
- notification email

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

Each crawler run inserts a `price_snapshots` row.

Price-history API exists:

`GET /api/products/[id]/history`

It returns:

- historical observations
- lowest observed price
- highest observed price
- latest price
- snapshot count

Frontend includes a price-history visualization.

## Alerts

Watch evaluation currently considers:

- desired size availability
- target price

Current result states:

- WAIT
- ALERT READY

Resend email delivery has been tested.

Alert state persistence prevents duplicate notifications while a condition remains true.

A false → true transition can notify again later.

## Cloud automation

GitHub Actions runs the crawler every approximately two hours.

Workflow:
`.github/workflows/price-check.yml`

It has been tested successfully on GitHub-hosted Ubuntu runners with:

- Python 3.14
- Playwright Chromium
- Supabase secrets
- Resend secret

Laptop does not need to remain on.

---

# 17. Current Database Evolution

Existing migrations currently include:

- initial products/watchlists
- product tracking fields
- price snapshots
- product variants
- watch alert state

Current schema is prototype-oriented.

Do NOT treat it as the final domain schema.

In particular:

- `products` currently mixes canonical-product/listing concerns
- `desired_size` is category-specific
- watch ownership is email-based rather than user-account based

These are expected to change during the identity/domain redesign.

---

# 18. Architecture Phases

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

## Phase 1 — Identity + Domain Model Redesign

Status: IN PROGRESS.

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

Next:

- Milestone 3: Supabase Auth, automatic profile creation and real RLS policies

Design before coding:

- Supabase Auth
- profiles
- roles
- feature flags
- canonical products
- merchants
- merchant listings
- generic variants
- watch intents
- per-user ownership
- compatibility/migration from prototype schema

Do not begin a large migration before documenting the target schema.

## Phase 2 — Product Discovery UX

Replace URL-first workflow with:

"What do you want to buy?"

Add:

- categories
- brands
- product discovery
- images
- product selection
- source/merchant selection

## Phase 3 — Multi-Source Tracking

Add retailer adapters incrementally.

Normalize all retailer data.

Implement canonical-product matching.

## Phase 4 — Production Monitoring

When usage requires it:

- scheduler
- queue
- workers
- listing-level deduplication
- retry/backoff
- observability

## Phase 5 — Deal Intelligence

- offers
- coupons
- bank discounts
- effective price
- richer alert policies
- merchant comparison

## Phase 6 — Purchases + Personalization

- purchase recording
- ratings
- returns
- explicit preferences
- recommendation feedback loop

## Phase 7 — AI / ML

Once sufficient real data exists:

- conversational intent parsing
- listing/product matching
- recommendation ranking
- price intelligence models
- grounded explanations

## Phase 8 — Labs / Admin Features

- finance intelligence
- Telegram
- WhatsApp
- push notifications
- admin-controlled feature flags

---

# 19. Immediate Next Step

Do NOT continue randomly adding frontend features.

Next major engineering activity:

Design Phase 1 in detail before implementing it.

Specifically define:

- long-term entities
- relationships
- Supabase Auth integration
- ownership/RLS model
- canonical-product vs merchant-listing boundaries
- generic variant representation
- watch-intent model
- migration strategy from current prototype

Only after that design is reviewed should the large refactor begin.

