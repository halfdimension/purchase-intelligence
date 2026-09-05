# Phase 1 — New Product Ingestion Architecture

Status: IMPLEMENTED AND VERIFIED; SCHEDULING/CUTOVER PENDING
Date: 2026-09-05

Read `PROJECT_CONTEXT.md`, `AGENTS.md`, and
`docs/phase-1-domain-architecture.md` before changing this design.

---

# 1. Problem

The authenticated Phase 1 watch API can currently create a
`watch_intent` when the requested merchant listing already exists
in the Phase 1 catalog.

For an unindexed URL it intentionally returns HTTP 422.

This is correct because normal authenticated users must not receive
permission to create or modify crawler-owned catalog data such as:

- canonical_products
- canonical_variants
- merchant_listings
- listing_variants
- listing_observations
- listing_variant_observations

The missing capability is therefore not simply another watch insert.

The missing capability is a trusted ingestion path that can turn a
new supported merchant URL into normalized Phase 1 catalog data and
then materialize the user's watch intent.

---

# 2. Security Boundary

The browser must remain a user-scoped client.

User request path:

Browser
    ↓
authenticated Next.js API
    ↓
Supabase user session
    ↓
RLS
    ↓
user-owned data

Catalog ingestion path:

tracking request
    ↓
trusted Python crawler / worker
    ↓
Supabase service role
    ↓
catalog + observation writes

The browser must never receive the Supabase service-role key.

The normal authenticated API must not use service-role access as a
general way to bypass catalog RLS.

---

# 3. Architecture Decision

Introduce a durable user-owned staging concept:

`tracking_requests`

A tracking request represents:

"Please set up tracking for this product/listing, but the system may
need to ingest and normalize it before a real watch can exist."

This table is not the historical watch itself.

Successful completion produces the real:

`watch_intents`

and, where appropriate:

`watch_listing_targets`

---

# 4. Why Asynchronous Ingestion

Scraping may require:

- network requests
- retailer-specific adapters
- Playwright
- retries
- merchant validation
- variant extraction
- normalization
- several database writes

These operations must not be performed inside the normal Next.js
browser request lifecycle.

The existing Python crawler already owns scraping and normalization.

Therefore ingestion should be asynchronous.

Initial prototype:

tracking request
    ↓
existing scheduled Python crawler

Future production architecture:

tracking request
    ↓
job queue
    ↓
crawler worker

The browser/API contract does not need to change when the worker
infrastructure changes later.

---

# 5. Proposed tracking_requests Table

Initial fields:

- id uuid primary key
- user_id uuid
- requested_url text
- normalized_url text
- variant_requirements jsonb
- target_price numeric nullable
- target_currency text
- conditions jsonb
- status text
- attempt_count integer
- result_product_id uuid nullable
- result_listing_id uuid nullable
- result_watch_id uuid nullable
- error_code text nullable
- error_message text nullable
- created_at timestamptz
- updated_at timestamptz
- started_at timestamptz nullable
- completed_at timestamptz nullable

Initial status values:

- pending
- processing
- completed
- failed
- cancelled

`status`, result IDs, attempts and processing timestamps are
worker-owned state.

Authenticated users must not be able to manufacture a successful
ingestion result.

---

# 6. RLS Direction

Authenticated users may:

- create their own tracking request
- read their own tracking requests

Initial implementation does not require users to update processing
state.

Insert ownership rule:

auth.uid() = user_id

Select ownership rule:

auth.uid() = user_id

The authenticated role should receive INSERT privileges only for
user-supplied request fields.

It must not receive INSERT or UPDATE privilege for:

- status
- attempt_count
- result_product_id
- result_listing_id
- result_watch_id
- error_code
- error_message
- started_at
- completed_at

The trusted crawler/service role owns those fields.

---

# 7. API Behavior

The existing authenticated Phase 1 watch POST should preserve its
current synchronous path for already-indexed listings.

Existing indexed listing:

POST tracking request / watch setup
    ↓
listing already exists
    ↓
validate variant
    ↓
create watch_intent
    ↓
create watch_listing_target
    ↓
201 Created

New supported URL:

POST tracking request / watch setup
    ↓
listing does not exist
    ↓
create tracking_requests row
    ↓
202 Accepted

Unsupported merchant or invalid URL:

4xx response

No catalog rows should be written merely because an arbitrary
untrusted URL was submitted.

---

# 8. Merchant Validation

Initial ingestion must support only explicit merchant adapters.

Example:

nike.in
    ↓
Nike adapter

The application must not treat every arbitrary hostname as a
supported crawler target.

Merchant validation must happen before the request becomes executable.

This reduces:

- SSRF risk
- unsupported crawler jobs
- junk catalog rows
- ambiguous merchant identity

The supported-host mapping must live in backend/crawler logic rather
than frontend presentation code.

---

# 9. Worker Flow

The trusted crawler will process pending tracking requests.

Conceptual flow:

pending tracking request
    ↓
claim request
    ↓
status = processing
    ↓
resolve merchant adapter
    ↓
scrape URL
    ↓
normalize into ProductData
    ↓
bootstrap / resolve Phase 1 catalog
    ↓
resolve requested variant
    ↓
create watch_intent
    ↓
create watch_listing_target
    ↓
store result IDs
    ↓
status = completed

Failure:

processing
    ↓
record error
    ↓
status = failed or retryable pending

Retries must be idempotent.

---

# 10. Catalog Bootstrap

Current controlled Phase 1 crawler persistence assumes that the
merchant listing already exists.

A separate bootstrap-capable persistence path is therefore required.

Conceptual function:

`bootstrap_product_phase1(product: ProductData, ...)`

Responsibilities:

1. resolve supported merchant
2. check whether merchant listing URL already exists
3. if it exists, reuse it
4. otherwise create the initial canonical product
5. create the merchant listing
6. create canonical variants
7. create listing variants
8. write the initial listing observation
9. write initial variant observations
10. return normalized Phase 1 identifiers

During this migration stage, do NOT perform aggressive cross-merchant
canonical-product merging.

A new unique merchant URL may initially create its own canonical
product.

Correct cross-merchant matching belongs to later product-discovery
and canonicalization work.

---

# 11. Existing Listing Race

The worker must always re-check the merchant listing by normalized URL
before creating catalog data.

Example:

User A requests URL
User B requests same URL

Only one merchant listing should ultimately represent that URL.

Both users may then receive independent watch intents pointing to the
same listing.

Crawler scheduling remains listing-deduplicated.

---

# 12. Watch Materialization

After successful catalog ingestion:

tracking_request.user_id
    ↓
watch_intents.user_id

tracking request target price
    ↓
watch_intents.target_price

tracking request variant requirements
    ↓
watch_intents.variant_requirements

resolved canonical variant
    ↓
watch_intents.canonical_variant_id

resolved merchant listing
    ↓
watch_listing_targets

The final watch must obey the same Phase 1 domain rules as a watch
created for an already-indexed listing.

---

# 13. Evaluation Timing

The first implementation does not need to guarantee that evaluation
happens in the same HTTP request that created the tracking request.

After the real watch exists, normal Phase 1 crawler scheduling will
include its merchant listing.

A later optimization may reuse the ingestion scrape result to perform
the first watch evaluation immediately.

Do not introduce duplicate crawls merely to make setup appear
synchronous.

---

# 14. Frontend State

Until ingestion finishes, the UI should eventually be able to show:

"Setting up tracking..."

rather than pretending that a complete watch already exists.

Possible user-visible states:

- Setting up
- Tracking
- Setup failed

The current prototype UI does not need to implement these states in
the first database milestone.

---

# 15. Current GitHub Actions Compatibility

Pending tracking requests must not yet be processed by the existing
scheduled crawler execution. Stale `processing`
lease/reclaim/reconciliation must be implemented before production
ingestion scheduling is enabled.

Later options include:

- workflow dispatch
- dedicated scheduler
- job queue
- worker service

These infrastructure changes must not be required to establish the
domain/security boundary now.

---

# 16. Compatibility Strategy

During implementation:

homepage READ
    -> Phase 1

homepage DELETE
    -> Phase 1

homepage CREATE
    -> Phase 0 until ingestion scheduling and setup UI are ready

Phase 0 tables remain intact.

Do not switch the homepage create form until the worker can be
scheduled safely and pending/setup UI is ready.

---

# 17. Implementation Milestones

Milestone A:
- add `tracking_requests` migration
- add RLS
- verify authenticated ownership

Milestone B:
- add authenticated API for submitting and reading tracking requests
- indexed listing behavior remains working
- new supported URL returns 202 + request id

Milestone C:
- add crawler request claiming
- add supported-host / adapter validation

Milestone D:
- add Phase 1 catalog bootstrap persistence
- create listing and variants from normalized ProductData
- ensure retries are idempotent

Status: COMPLETE

Implemented by migrations 018-019 and the trusted Python bootstrap
contract/database/payload layers. Catalog bootstrap remains a
service-role-only `SECURITY INVOKER` RPC.

Milestone E:
- materialize watch_intent and listing target
- update tracking request result IDs/status

Status: COMPLETE

Implementation details:

- generic worker orchestration is separate from the initial Nike
  adapter and Nike size normalization
- Nike ingestion requires a recognizable `/p/<id>` target before
  browser execution
- Nike browser rendering guards main-frame navigation independently
  of external image, JavaScript and CDN subresources
- scraped `ProductData.url` must remain in the Nike India hostname
  family and preserve the submitted merchant product id; canonical
  path/name redirects for the same id are accepted
- the worker scrapes the authoritative normalized target into the
  existing `ProductData` model
- `crawl_event_id` is deterministic for the claimed request attempt
- `checked_at` is derived from timezone-aware claim `started_at` and
  normalized to UTC
- only ambiguous HTTP transport/request failures receive one retry,
  using the exact same persistence request
- deterministic PostgREST failures are not retried and persist only
  controlled user-safe messages; full exceptions remain in worker logs
- contract/invariant `RuntimeError` failures are not retried or hidden
- if both transport attempts leave commit status unknown, the request
  remains `processing` for operator reconciliation rather than being
  falsely completed or failed
- requested variant requirements resolve in the Python adapter layer
- migration 020 adds the service-role-only
  `materialize_phase1_tracking_request(...)` RPC
- watch intent insertion, listing-target insertion, result IDs and
  request completion occur in one transaction
- completion is guarded by request id, `processing` state and exact
  `attempt_count`
- completed RPC calls are idempotently replayable after ambiguous
  client responses
- duplicate worker materializations for the same user/listing/variant
  are serialized; the later tracking request becomes `failed` with
  stable `duplicate_watch` state rather than creating another watch
- the RPC verifies active product/listing/merchant relationships,
  authoritative listing URL, currency, and resolved generic variant
  identity
- expected worker failures persist stable error codes and do not mark
  the request completed
- the high-level processor claims exactly one request per invocation
- the ingestion worker is not yet wired into `crawler.run_tracked` or
  the scheduled production workflow
- durable processing leases/reclaim are required before production
  scheduling or batch claiming is enabled

Real Supabase PostgreSQL verification:

- the exact committed migration 020 was rollback-tested
- the rollback harness verified installation, successful
  materialization, `watch_listing_target` creation, request
  completion, completed-call replay, stale-attempt rejection,
  duplicate-watch handling/replay and transaction atomicity on a
  forced target failure
- privileges were verified as `SECURITY INVOKER` and
  service-role-only
- rollback cleanup left no helper, function, trigger or test row
- the exact committed migration was then applied permanently
- production verification confirmed:
  - function installed: true
  - `SECURITY INVOKER`: true
  - `search_path`: `""`
  - `service_role` execute: true
  - `authenticated` execute: false
  - `anon` execute: false

Milestone F:
- local end-to-end test using a different real supported product URL
- verify crawler persistence
- verify watch creation
- verify normal subsequent monitoring

Status: COMPLETE

Verified with Nike Pegasus 42 Men's Road-Running Shoes:

- external product id: `27763518`
- URL:
  `https://www.nike.in/nike-pegasus-42-men-s-road-running-shoes/p/27763518`
- no listing existed by URL or external id before ingestion
- authenticated `POST /api/tracking-requests` returned HTTP 202 for
  UK 9 at a target price of INR 13000
- the staged request was `pending` with `attempt_count = 0`
- the guarded browser returned HTTP 200 and preserved `/p/27763518`
- the scrape returned INR 13995 price/MRP and seven variants from UK 6
  through UK 12
- `process_phase1_ingestion_requests(1)` completed successfully
- result identities:
  - product: `fb3bcf39-063a-47ba-beeb-0e3d8888ac98`
  - listing: `84505eb3-ae9f-499b-80dd-b0e582c21598`
  - watch: `db26593f-0714-4f5e-b3c3-3fa962c4a9c7`
  - tracking request: `e2fb50d7-5aa7-4ad2-a8d3-d860f1e6186b`
- persistence verification confirmed:
  - completed request with `attempt_count = 1` and null error code
  - listing external id `27763518`, INR 13995 and in stock
  - active INR 13000 watch with `{"size":"UK 9"}`
  - canonical `size:uk-9` / UK 9 variant
  - seven listing variants
  - one initial listing observation
  - seven initial variant observations
  - exactly one `watch_listing_target`
- normal monitoring automatically discovered and scraped the listing,
  persisted another observation, found the watch and evaluated it
- notification execution was disabled; evaluation persisted
  `condition_met = false`, transition `false -> false`, no required or
  created notification, and reason
  `Current price ₹13,995 is above target ₹13,000.`
- output ended with `MILESTONE_F_MONITORING_TEST: PASSED`

Milestones D, E and F are complete.

Milestone G:
- implement processing lease/reclaim/reconciliation
- verify safe ingestion-worker scheduling and cloud execution

Milestone H:
- update homepage CREATE to use `tracking_requests`
- add pending/setup UI and verify the production UX
- retain Phase 0 rollback path until stability is proven

Required next sequence:

1. implement processing lease/reclaim/reconciliation for trusted
   ingestion
2. verify worker scheduling/cloud execution safely
3. cut homepage CREATE over to `tracking_requests` and add
   pending/setup UI
4. verify production UX
5. retain Phase 0 compatibility until final cutover confidence

Until lease/reclaim/reconciliation exists, production ingestion
scheduling and batch processing remain disabled, the high-level
processor remains limited to one request per invocation, and exhausted
ambiguous transport outcomes intentionally remain `processing`.

---

# 18. Non-Goals

This ingestion milestone does NOT implement:

- Amazon
- Flipkart
- multi-merchant canonical matching
- AI product matching
- guided product discovery
- offer ingestion
- coupons
- bank offers
- ML price prediction

Those remain later phases.

---

# 19. Final Responsibility Split

Browser
    │
    │ authenticated user intent
    ▼
tracking_requests
    │
    │ trusted processing
    ▼
Python crawler / ingestion worker
    │
    ├── merchant adapter
    ├── scrape
    ├── normalize
    └── catalog persistence
    │
    ▼
canonical_products
    │
    ├── canonical_variants
    │
    ▼
merchant_listings
    │
    ├── listing_variants
    ├── listing_observations
    └── listing_variant_observations
    │
    ▼
watch_intents
    │
    ▼
watch_listing_targets
    │
    ▼
normal Phase 1 monitoring/evaluation

This preserves the critical rule:

user intent is user-owned;
catalog truth is crawler-owned.
