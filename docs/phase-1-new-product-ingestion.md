# Phase 1 — New Product Ingestion Architecture

Status: LEASE/RECLAIM IMPLEMENTED AND DATABASE-VERIFIED;
PERMANENT MIGRATION 021 APPLICATION AND SCHEDULING/CUTOVER PENDING
Date: 2026-09-06

Lease/reclaim status: implemented locally and verified against Supabase
PostgreSQL with the rollback-only integration harness, rollback cleanup
verification, and a real two-session `FOR UPDATE SKIP LOCKED`
concurrency test. Permanent migration 021 application remains pending.

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
scheduled crawler execution. Stale `processing` lease/reclaim and
materialization reconciliation are implemented locally and have passed
rollback/database verification, including a real two-session
`FOR UPDATE SKIP LOCKED` concurrency test.

Migration 021 has not yet been permanently applied. The exact tested
migration must be committed, permanently applied, and its production
schema/security state verified before production ingestion scheduling
is enabled.

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
- durable processing leases/reclaim are implemented locally and passed
  the rollback-only Supabase integration harness, rollback cleanup
  verification, and the real two-session `FOR UPDATE SKIP LOCKED`
  concurrency test
- permanent migration 021 application and post-apply production
  schema/security verification remain required before production
  ingestion scheduling is enabled

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

Status: IMPLEMENTED LOCALLY; ROLLBACK/DATABASE VERIFICATION PENDING

Implemented locally:

- migration 021 adds database-owned processing lease deadlines
- `attempt_count` remains the fencing generation
- pending claims and expired-processing reclaims are atomic and use
  `FOR UPDATE SKIP LOCKED`
- claim fairness orders pending `created_at` and expired
  `lease_expires_at` as one eligibility timeline
- reclaims increment `attempt_count` and issue a new lease
- exact-attempt lease renewal is service-role-only
- a named 600-second worker lease is configurable from 300 through
  1200 seconds
- leases renew before browser scrape, catalog bootstrap, and watch
  materialization; no background heartbeat thread is used
- ambiguous renewal stops the worker before later side effects
- ambiguous materialization reconciles authoritative terminal request
  state when PostgreSQL already committed
- the high-level processor remains limited to one item per invocation
- the rollback-only migration harness is under `supabase/tests/`

Not yet complete:

- migration 021 has not been applied
- the rollback harness has not been run against Supabase PostgreSQL
- true simultaneous-session `SKIP LOCKED` behavior still needs the
  documented manual database check
- ingestion scheduling/cloud execution remains disabled

Milestone H:
- update homepage CREATE to use `tracking_requests`
- add pending/setup UI and verify the production UX
- retain Phase 0 rollback path until stability is proven

Required next sequence:

1. review migration 021 and run its rollback/database harness
2. decide whether to apply migration 021
3. verify worker scheduling/cloud execution safely
4. cut homepage CREATE over to `tracking_requests` and add
   pending/setup UI
5. verify production UX
6. retain Phase 0 compatibility until final cutover confidence

Until migration 021 passes rollback/database verification and is
deliberately applied, production ingestion scheduling and batch
processing remain disabled. The high-level processor remains limited
to one request per invocation.

---

# 18. Lease, Reclaim, and Reconciliation Design

## Lease state and policy

`tracking_requests.lease_expires_at` is the only new lease field.

`attempt_count` is already a durable monotonically increasing fencing
generation, so another random token would duplicate its role. A
heartbeat timestamp would not participate in any correctness decision;
the authoritative deadline is sufficient.

PostgreSQL time establishes and renews the deadline. The default lease
is 600 seconds and can be configured with
`PHASE1_INGESTION_LEASE_SECONDS`. Python and SQL both enforce a range of
300 through 1200 seconds. The lower bound covers the longest current
persistence stage: the pinned Supabase/PostgREST timeout is 120 seconds
and the worker may transmit the same request twice. It also exceeds the
current Playwright 60-second navigation plus 5-second settle. The
600-second default leaves operational margin. The 1200-second upper
bound matches the current 20-minute workflow job limit, so an abandoned
claim cannot be configured beyond the invocation budget without an
explicit policy change.

Rows created by the pre-021 worker with `status = 'processing'` receive
`lease_expires_at = now()` during migration and are therefore explicitly
reclaimable after deployment. Terminal status remains the authoritative
reclaim gate even if a row retains its final lease deadline.

## Claim and renewal

The claim RPC considers:

- pending rows; and
- processing rows whose lease has expired according to PostgreSQL.

It locks candidates with `FOR UPDATE SKIP LOCKED`, updates the state in
the same statement, increments `attempt_count`, replaces `started_at`,
issues a new deadline, and clears stale errors. Eligible work is ordered
by the time it became eligible: `created_at` for pending rows and
`lease_expires_at` for expired processing rows, followed by `id` as the
stable tie breaker. This prevents an endless stream of newer pending
requests from stranding an expired request. A reclaimed request receives
a fresh future deadline, so repeated crashes cannot continuously
monopolize the queue either.

Renewal requires request id, processing status, the exact
`attempt_count`, and an unexpired current lease. A zero-row result is a
confirmed ownership loss. Transport ambiguity is retried once with the
same guard; if both responses are ambiguous, the worker stops without
scraping or performing a later database side effect.

The worker renews only at the three meaningful long-stage boundaries:

1. before browser scrape;
2. before catalog bootstrap; and
3. before watch materialization.

No background heartbeat is needed for the bounded current operations.

## Ambiguous outcome reconciliation

Catalog bootstrap keeps its existing transport-only retry. If both
responses are ambiguous, the request stays processing. Once its lease
expires, a new generation may scrape and bootstrap again. Migration 019
converges catalog identity by normalized URL, deduplicates a single
attempt by stable `crawl_event_id`, and only updates latest-state caches
when `checked_at` is newer.

After two ambiguous materialization responses, the worker reads the
authoritative tracking request. A same-attempt completed row returns its
persisted product/listing/watch identities. A same-attempt
`failed/duplicate_watch` row returns that terminal outcome. A processing
row remains unresolved and is left for expiry. A newer generation is
reported internally as ownership loss. No uncertain outcome is turned
into a user product failure.

## Crash and concurrency windows

- A — death after claim and before validation: the initial lease
  expires; reclaim creates the next attempt generation.
- B — death during Nike browser scrape: the pre-scrape renewal bounds
  abandonment; reclaim creates the next generation.
- C — bootstrap commits, then the worker dies: catalog state remains;
  the reclaimed generation safely re-scrapes, reuses the URL identity,
  and can materialize the watch.
- D — bootstrap commits but its response is lost: same-attempt retry is
  idempotent; if both responses are lost, case C applies after expiry.
- E — materialization commits but its response is lost: watch, target,
  result ids, and completed status committed atomically. Replay or the
  reconciliation read observes that terminal state; claim ignores it.
- F — duplicate-watch handling commits but its response is lost: the
  stable failed/duplicate state is replayable and never creates a watch.
- G — attempt N expires, N+1 is reclaimed, then N resumes: N cannot
  renew, fail, or materialize the request because those writes require
  the exact current generation.
- H — explicit stale renew/fail/materialize calls: renewal returns no
  row, guarded failure affects no row, and migration 020 rejects the
  stale attempt.
- I — renewal response is ambiguous: the exact guarded renewal is
  retried once; another ambiguous response stops all later side effects.
- J — repeated crashes: each expired request remains safely reclaimable.
  No arbitrary attempt ceiling is imposed before scheduling telemetry
  exists. Fair eligibility-time ordering eventually serves stale and
  pending work, while every reclaim advances the stale row's next
  eligibility time.
- K — terminalization races reclaim: row locking chooses the winner and
  repeated status/attempt predicates prevent resurrection or stale
  completion.

Migration 019 deliberately does not know the tracking-request
generation. An already in-flight attempt-N bootstrap can therefore
finish after N+1 exists. This is acceptable: stable per-attempt event
identity prevents retry duplicates, URL/catalog uniqueness converges on
one listing, immutable observations may safely arrive out of order, and
the `checked_at` monotonic guards prevent the older attempt from
overwriting newer current state. No concrete corruption path requires a
change to the already-applied migration. The rollback harness covers
both an exact-event replay and an old attempt's first bootstrap call
after N+1 has already persisted newer listing and variant state.

## Deferred retry budget

Migration 021 intentionally does not terminalize a request after a
fixed number of expired generations. An expired attempt may have
committed useful catalog state immediately before dying, and all current
remaining work is designed to be safely repeatable. Three generations
had no production evidence behind it and could abandon a recoverable
user request. Attempt counts must be observed during later scheduling;
an operational dead-letter policy can be added when real failure data
supports a threshold and recovery workflow.

---

# 19. Non-Goals

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

# 20. Final Responsibility Split

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
