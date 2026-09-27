# Phase 2 — General Purchase Intelligence Architecture

Status: TARGET / DESIGN — NOT YET IMPLEMENTED

Date: 2026-09-27

Read `PROJECT_CONTEXT.md`, `AGENTS.md`,
`docs/phase-1-domain-architecture.md`, and
`docs/phase-1-new-product-ingestion.md` before changing this design or
implementing a milestone from it.

This document is the detailed target design for the phase after the proven
Nike India tracking flow. `PROJECT_CONTEXT.md` remains the high-level durable
source of truth. Existing migrations and implementation remain authoritative
for current behavior.

Status language:

- **IMPLEMENTED / VERIFIED** — exists and has been exercised in the current
  repository or production path.
- **CURRENT LIMITATION** — true of today's runtime.
- **TARGET / FUTURE** — architecture direction; not a claim of availability.

---

# 1. Purpose

Purchase Intelligence is evolving from a Nike India URL tracker into a general
system for:

- product discovery;
- canonical product understanding;
- exact variant selection;
- official-source-first presentation;
- multi-merchant comparison;
- price and availability tracking;
- useful transition-based alerts;
- explainable, grounded purchase intelligence.

The intended primary interaction is a natural search such as:

- `S26 Ultra`
- `MacBook Pro M4 Pro`
- `Soundcore Q20i`
- `Nike Pegasus 42`
- `Levi's jeans`
- `headphones`, `laptop`, `earbuds`, `clothes`, or `shoes`

The system must not require the user to know a product page URL, although URL
ingestion can remain as an advanced/fallback path.

This document defines the target boundaries and dependency order. It does not
authorize implementing the entire design in one refactor.

---

# 2. Verified Baseline

## 2.1 Implemented and verified

The current production system has proven:

- a Vercel-hosted Next.js, TypeScript, Tailwind, App Router application;
- Supabase Auth with a private sign-in-only deployment;
- authenticated, RLS-owned watch intents;
- canonical products separate from merchant listings;
- canonical variants separate from listing variants;
- generic JSONB attribute storage in the Phase 1 schema;
- durable user-owned `tracking_requests`;
- trusted scheduled ingestion with leases, reclaim, fencing, idempotency, and
  reconciliation;
- real Nike India browser crawling and variant extraction;
- normalized catalog bootstrap and watch materialization;
- unique-listing monitoring from Phase 1 watches;
- immutable listing and listing-variant observations;
- Phase 1 target-price and size/stock evaluation;
- transition-based notification deduplication;
- real Resend email delivery;
- scheduled GitHub Actions ingestion and monitoring.

These capabilities are the foundation to generalize, not throwaway code.

## 2.2 Current limitations

The current end-to-end product remains Nike/shoe-specific:

- the entry point is a Nike India URL;
- only the Nike ingestion adapter is registered;
- the request API, variant resolver, evaluator, compatibility view model, and
  form still understand a `size` requirement;
- the homepage hardcodes UK-size controls;
- normal monitoring still selects Nike/generic scraper classes directly;
- official source is not represented as a catalog relationship;
- discovery search, classification, dynamic variants, cross-store matching,
  and multi-merchant comparison are not implemented;
- Phase 0 product/snapshot compatibility writes and the legacy history read
  path remain.

The detailed Phase 1 documents contain the implementation rationale. Phase 2
must not duplicate or bypass their security, idempotency, and migration
decisions.

---

# 3. Target Product Journey

```text
user query
    |
    v
search existing catalog + supported discovery providers
    |
    +---- fast normalized results ----------------------------+
    |                                                         |
    +---- durable async enrichment, when needed               |
                                                              v
                                                candidate normalization
                                                              |
                                           category + attribute understanding
                                                              |
                                            canonical entity resolution
                                                              |
                       +--------------------------------------+
                       |                                      |
                       v                                      v
             official reference source              alternative listings
                       |                                      |
                       +----------- comparison ---------------+
                                                              |
                                              exact variant selection
                                                              |
                                             tracking-scope selection
                                                              |
                                      monitoring and historical observations
                                                              |
                                         alerts and purchase intelligence
```

The eventual UI should answer distinct questions:

1. What real product is this?
2. Which exact configuration does the user want?
3. What does the official manufacturer/brand source say?
4. Which supported merchants sell the same product/variant?
5. What is the official price and the best supported market price?
6. Is the desired variant available?
7. How does the current offer compare with history and the user's target?
8. Why did the system alert or recommend BUY/WAIT?

---

# 4. Architectural Principles

## 4.1 Product is not listing

A canonical product represents the real-world product independent of a store.
A merchant listing represents one merchant's page or offer for that product.

## 4.2 Canonical variant is not listing variant

A canonical variant represents an exact configuration such as:

```json
{
  "color": "Titanium Black",
  "storage": "512 GB",
  "ram": "12 GB"
}
```

A listing variant represents how a merchant exposes that configuration,
including merchant SKU, title, price, availability, and merchant-specific
attributes.

## 4.3 Watch is not crawl

A watch is user intent. A crawl is shared retrieval work. A listing should be
retrieved once per scheduled event and evaluated against every relevant watch.

## 4.4 Official and cheapest are separate dimensions

The official source is preferred as a catalog reference and presentation
anchor. The cheapest supported offer may be elsewhere. Ranking must retain
both facts instead of collapsing them into one score.

## 4.5 Categories do not create database schemas

Product categories guide normalization, validation, search facets, and UI
labels. They must not create a new group of physical columns or a new frontend
implementation for every category.

## 4.6 Merchant details stop at the adapter boundary

Merchant HTML, JSON-LD, embedded application state, APIs, selectors, browser
rules, and anti-bot behavior are adapter concerns. Shared catalog, search,
watch, and frontend layers consume normalized contracts only.

## 4.7 Retrieval facts and inference remain distinct

Prices, stock, sellers, offers, and product existence come from supported real
retrieval. Classification/matching models may interpret evidence; they must
not manufacture commerce facts.

## 4.8 Long-running work is durable and asynchronous

Playwright and expensive discovery do not belong in an interactive request.
Use a fast path plus durable background enrichment with visible status,
idempotency, leases, and reconciliation.

## 4.9 Trust boundaries remain explicit

Authenticated browser/API operations are user-scoped and RLS-protected.
Trusted workers own catalog mutation, observations, classification state,
evaluation, and notification delivery state.

## 4.10 Complexity follows evidence

No microservice, queue, cache, search engine, datastore, gateway, or load
balancer is introduced before a measured workload justifies it.

---

# 5. Target Logical Architecture

```text
                              +-----------------------+
                              | Browser / Next.js UI  |
                              +-----------+-----------+
                                          |
                         authenticated user-scoped APIs
                                          |
             +----------------------------+----------------------------+
             |                            |                            |
             v                            v                            v
       Catalog Search              Discovery Requests             Watch Intents
       (fast path)                 (durable async)                (user-owned)
             |                            |                            |
             +---------------+------------+                            |
                             v                                         |
                  Discovery Orchestrator                               |
                             |                                         |
                supported adapter capabilities                         |
                             |                                         |
                  raw candidates + provenance                          |
                             |                                         |
          deterministic extraction / classification / normalization    |
                             |                                         |
                   canonical entity resolution                         |
                             |                                         |
        +--------------------+--------------------+                    |
        |                                         |                    |
        v                                         v                    |
 Canonical catalog                        Merchant listings/offers <----+
        |                                         |
        +--------------------+--------------------+
                             |
                        crawl scheduler
                             |
                         adapter workers
                             |
                  immutable observations
                             |
                       watch evaluation
                             |
                notification and delivery state
                             |
               grounded purchase-intelligence signals
```

This is a logical layout. It can remain a Next.js application, PostgreSQL, and
Python workers until measured scale requires physical service separation.

---

# 6. Target Domain Model

Phase 2 evolves the existing Phase 1 tables. It does not silently replace them.
Exact SQL belongs in reviewed additive migrations.

## 6.1 Brands

Current `brands` rows already provide stable brand identity plus optional
official URL/logo metadata.

Target responsibilities:

- stable normalized brand identity;
- display name and aliases where required;
- manufacturer/brand reference URLs;
- relationship to official merchant sources;
- evidence used to resolve brand identity.

A URL alone is insufficient to prove that a listing is official.

## 6.2 Categories

Current `categories.attributes_schema` is the seed for category guidance.

Target category schema may describe:

- common product specification keys;
- common purchasable variant axes;
- labels and display order;
- expected value type or unit;
- normalization hints;
- filter/facet eligibility;
- whether an attribute is normally identity-bearing.

Example concept:

```json
{
  "variant_axes": [
    {"key":"color","label":"Color","order":10},
    {"key":"storage","label":"Storage","order":20},
    {"key":"ram","label":"RAM","order":30}
  ],
  "specifications": [
    {"key":"screen_size","label":"Screen size","unit":"inch"}
  ]
}
```

This is metadata and guidance. A product may contain a valid attribute not yet
listed in its category schema. The schema must not become a rigid, loss-making
allowlist.

## 6.3 Canonical products

`canonical_products` remains the merchant-independent identity.

Target data includes:

- brand and category references;
- canonical name/model/model number;
- identifiers such as GTIN/EAN/UPC/MPN and official product ID;
- normalized product-level attributes;
- preferred reference imagery/provenance;
- identity/evidence state where matching is uncertain.

Product-level attributes describe the model shared by all variants. Values
that change what the user can purchase belong on canonical variants.

## 6.4 Canonical variants

`canonical_variants.attributes` remains the generic variant representation.

Examples:

```json
{"color":"Black/White","size":"UK 9"}
```

```json
{"processor":"M4 Pro","ram":"24 GB","storage":"512 GB","color":"Space Black"}
```

```json
{"color":"Navy","size":"L","fit":"Regular"}
```

`variant_key` remains a stable normalized identity within one product. It must
be derived from canonical attribute keys and normalized values, not from
display order or a merchant SKU.

The exact serialization convention must be centralized and versionable. Do
not let individual adapters independently invent keys for the same concept.

## 6.5 Merchants and source roles

Current `merchants` identifies a source and maps it to an `adapter_key`. It does
not yet express official-source semantics.

Phase 2 must represent two separate concepts:

1. **merchant/channel type** — for example brand-direct, retailer, or
   marketplace;
2. **brand/product relationship** — for example official manufacturer store,
   authorized retailer, marketplace seller, or ordinary alternative.

Officialness must not be one global boolean on a merchant. A marketplace can
contain both official and third-party sellers; a retailer can be official for
one relationship and merely an alternative for another.

Recommended relational direction:

```text
brand
  |
  +---- verified source relationship ---- merchant
                                          |
                                          +---- merchant listing
```

The relationship needs enough evidence/context to answer:

- which brand it applies to;
- the source role;
- region/market where relevant;
- how it was verified;
- whether it is active.

A listing-specific role/evidence override may later be necessary for official
stores inside marketplaces. The next milestone should choose the smallest
model that represents current brand-direct sources without blocking that
future case.

## 6.6 Merchant listings and listing variants

`merchant_listings` and `listing_variants` remain source-specific.

They provide:

- merchant URL and external identity;
- seller/channel information;
- current price/MRP/currency;
- stock and latest-check cache;
- merchant variant SKU/title/attributes;
- link to canonical product and, when resolved, canonical variant.

Official and alternative listings share the same normalized listing model.
Official treatment is metadata/ranking, not a separate product table.

## 6.7 Offers

The current listing cache can represent one current selling price. Later,
reliable coupon, bank, cashback, delivery, or seller-specific offer data may
require a separate offer model.

Do not add it in the first generalization migration unless current retrieval
has real offer data and a concrete access pattern. Never claim an effective
price unless eligibility and unavoidable fees are known.

## 6.8 Observations

Listing and listing-variant observations remain append-only historical facts.
Future offer observations should follow the same pattern:

- immutable event history;
- source and retrieval timestamp;
- idempotent event identity;
- latest-state cache updated only by newer observations;
- raw evidence/provenance retained where safe and useful.

## 6.9 Watch intents and tracking scope

The current model already has:

- canonical product;
- optional canonical variant;
- generic `variant_requirements` JSONB;
- `tracking_scope` values for specific, selected, or any listing;
- explicit listing targets.

The target experience maps those concepts to user choices:

- official store only;
- selected supported merchants;
- all supported merchants / best supported offer.

Exact UX and API details are deferred until discovery and comparison exist.
Do not encode these choices as category-specific watch columns.

---

# 7. Generic Attribute Contract

Generic JSON alone is not sufficient; keys and values must be normalized.

## 7.1 Attribute-key registry

Shared normalization should define stable keys such as:

- `color`
- `size`
- `fit`
- `storage`
- `ram`
- `processor`
- `gpu`
- `connectivity`
- `screen_size`
- `version`
- `bundle`

The registry is an application/domain convention, not necessarily a table in
the first milestone. It should define aliases, canonical key, value type,
optional unit, and display label.

Examples:

```text
storage_capacity, capacity, storage_gb -> storage
memory, installed_ram, ram_gb          -> ram
colour                                 -> color
```

Do not normalize two semantically different concepts merely because their
merchant labels look similar.

## 7.2 Value normalization

Normalization should preserve a user-friendly canonical display value while
supporting deterministic comparison.

Examples:

```text
"512GB", "512 GB"       -> "512 GB"
"12gb ram", "12 GB"     -> "12 GB"
"uk9", "UK 9"           -> "UK 9"
"titanium black"         -> "Titanium Black"
```

If query requirements later demand numeric/unit decomposition, introduce it in
a consistent generic value representation rather than a phone-only column.

## 7.3 Product versus variant attributes

Use this rule:

- if the value describes the model regardless of the purchasable choice, it
  is a product attribute;
- if changing the value selects a different purchasable configuration, it is
  a variant attribute;
- if a merchant exposes extra source-only detail, keep it on the listing or
  listing variant until canonicalized.

Some categories and merchants disagree about what constitutes a variant. The
normalizer should record evidence and avoid forced canonicalization when the
identity is ambiguous.

## 7.4 Stable variant keys

A stable canonical variant key must:

- use normalized attribute keys and values;
- have deterministic key ordering;
- exclude merchant SKU and volatile price/stock;
- distinguish valid configurations that differ on an identity-bearing axis;
- be generated centrally;
- preserve compatibility or provide an explicit key migration when rules
  change.

---

# 8. Dynamic Variant UI

The frontend must not globally render a “size selector.” It consumes a
normalized product/variant view model.

Given variants:

```text
Black  / 256 GB / 12 GB
Black  / 512 GB / 12 GB
Silver / 256 GB / 12 GB
Silver / 512 GB / 12 GB
```

The UI derives:

- Color: Black, Silver -> selector
- Storage: 256 GB, 512 GB -> selector
- RAM: 12 GB -> specification

Selection algorithm:

1. Start from the real active canonical/listing variants.
2. Determine attribute axes and value cardinality.
3. Order/label known axes using category metadata; retain unknown axes safely.
4. Render multi-value axes as controls.
5. Render single-value axes as specifications.
6. As the user chooses values, filter the real variant set.
7. Disable combinations that do not map to a real purchasable variant.
8. Resolve the final selection to canonical and listing variant identities.

Never construct every mathematical combination of values and assume it exists.
Availability and price may differ by merchant listing variant and should be
shown at the resolved configuration level.

The same machinery must work for footwear, phones, clothing, laptops, and
headphones without category-specific React branches.

---

# 9. Merchant Adapter Architecture

## 9.1 Current state

The ingestion worker already has a `Phase1IngestionAdapter` boundary, with Nike
as its only registered implementation. Normal monitoring still contains
direct Nike/generic scraper selection. Search capability does not exist.

## 9.2 Target boundary

The shared design should be capability-based because not every source supports
the same operations.

Conceptual capabilities:

- recognize and normalize a supported merchant URL;
- search/query products, when the source provides a suitable path;
- fetch a product/listing;
- extract current listing and variant state;
- return source identifiers and provenance;
- normalize raw source data into shared candidate/domain contracts.

Conceptual contract:

```text
MerchantAdapter
    identity/capabilities
    normalize_url(...)
    search(...), if supported
    fetch_listing(...)
    normalize_candidate(...)
    extract_variants/current_state(...)
```

Exact Python interfaces must be derived from the current ingestion, scraper,
and monitoring code during the adapter milestone. Do not copy this conceptual
shape blindly.

## 9.3 Adapter output

Shared layers should receive normalized values such as:

- merchant and external listing identity;
- raw title/description/category evidence;
- brand evidence;
- identifiers;
- product attributes;
- variant attributes and merchant SKU;
- price, currency, stock, seller, images, and retrieval timestamp;
- raw/provenance data appropriate for debugging and later learning.

They must not receive merchant DOM selectors or embedded-JSON paths.

## 9.4 Explicit support

Potential future adapters include Nike India, Apple India, Samsung India,
Croma, Adidas, and Soundcore. This is not a promise that all are technically
or legally retrievable. Add sources incrementally, respect provider terms, and
do not claim support until the path is verified.

---

# 10. Discovery and Search

## 10.1 Search pipeline

```text
query
    -> intent/query normalization
    -> existing catalog search
    -> supported provider discovery
    -> raw candidates
    -> deterministic normalization
    -> category classification
    -> attribute extraction
    -> canonical product matching
    -> official-source identification
    -> canonical product cards + merchant offers
```

## 10.2 Fast path

The interactive request should first:

- search indexed canonical products and variants;
- return cached current listing state;
- use lightweight supported provider APIs/endpoints where reliable and within
  limits;
- make partial/provisional status clear.

## 10.3 Asynchronous enrichment

When discovery needs browser crawling or expensive classification:

```text
authenticated discovery intent
    -> durable discovery request
    -> trusted worker claim/lease
    -> provider discovery and retrieval
    -> normalization and persistence
    -> request result/status
    -> frontend poll/refresh
```

This can reuse the principles proven by `tracking_requests`, but should not
overload that table without a deliberate domain decision. Search intent and a
request to materialize a watch are related but not identical.

Required properties:

- user ownership and RLS;
- server/worker revalidation of source inputs;
- bounded work and explicit capabilities;
- idempotent persistence;
- retry/lease/reconciliation semantics;
- safe user-visible errors;
- deduplication of equivalent in-flight discovery where practical.

## 10.4 Search result shape

A result card should represent a canonical product, not one raw listing. It may
include:

- canonical image/name/brand/category;
- concise normalized specifications;
- variant summary;
- official source availability/price;
- best supported alternative price;
- number of supported sources;
- freshness/provisional state.

Do not rank only by cheapest listing. Relevance, identity confidence, official
reference status, freshness, stock, and price are separate inputs.

## 10.5 Target information architecture

```text
/
    discovery/search

/search?q=...
    canonical product result cards

/product/<canonical-product-id>
    canonical product, dynamic variants, official source, alternatives,
    price history, and tracking action

/watchlist
    tracked products and setup state

/login
    authentication
```

These routes are target direction, not part of this documentation task and not
authorization to implement them all in one milestone.

---

# 11. Cross-Store Entity Resolution

Multiple merchant listings may describe the same product:

```text
Samsung official: Galaxy S26 Ultra 5G
Retailer A:        SAMSUNG Galaxy S26 Ultra 5G (Black, 512 GB)
Retailer B:        Samsung S26 Ultra 512 GB Black
```

They should converge to one canonical product with merchant listings and
matched variants when the evidence is adequate.

Matching layers:

1. exact global identifier match;
2. manufacturer model/part number match;
3. official product identifier or verified official reference;
4. normalized brand/model/specification match;
5. exact variant-attribute compatibility;
6. fuzzy/embedding/ML assistance;
7. manual review or unresolved state.

Every match should retain evidence and confidence appropriate to its layer.
High-confidence deterministic evidence may auto-link. Lower-confidence model
matches should be reviewable and must not silently merge catalog entities.

Merging canonical products is a data migration with downstream watch/history
impact, not a display-only action. It requires explicit survivor identity and
reference remapping rules.

---

# 12. Official-Source-First Behavior

## 12.1 Catalog authority

When a verified official source exists, prefer it for:

- canonical product name and model;
- manufacturer identifiers;
- official specifications;
- official variant set;
- official imagery;
- manufacturer list/reference price.

“Prefer” does not mean blindly overwrite stronger existing evidence. Store
provenance and resolve contradictions explicitly.

## 12.2 Comparison

Target presentation:

```text
Official store
Samsung India       Rs 124,999

Alternatives
Croma               Rs 112,999
Merchant X          Rs 109,999

Best supported price:        Rs 109,999
Difference from official:    Rs 15,000
User target:                 Rs 110,000
```

Alternative ranking may consider effective supported price, stock, seller
confidence, freshness, delivery, and user choice. It must retain the official
source as a separate labeled reference.

## 12.3 Missing official source

If no official source is supported or retrievable, show the best available
catalog evidence without falsely labeling a retailer as official. Absence of
an official listing is valid state.

---

# 13. Generalized Tracking and Monitoring

Target watch identity:

```text
user
  -> canonical product
  -> optional exact canonical variant
  -> tracking scope
  -> optional merchant listing targets
  -> target/conditions
```

Tracking scopes should eventually map to:

- official only;
- selected supported merchants;
- all supported merchants / best supported offer.

Monitoring remains listing-oriented:

```text
unique due listing
    -> retrieve once
    -> persist current state + immutable observations
    -> find all relevant watches
    -> evaluate each watch against its scope and exact variant
```

The evaluator must become generic. It should consume normalized requirements
and resolved variant/listing state rather than contain a fixed set containing
only `size`.

An eventual multi-merchant alert may explain:

```text
Target: Rs 110,000
Samsung official: Rs 124,999
Croma:            Rs 112,999
Merchant X:       Rs 109,999

Target reached on Merchant X. Official is Rs 15,000 higher.
```

The exact UX/API is deferred; the domain must make it possible.

---

# 14. Purchase Intelligence

Tracking is an input to intelligence, not the final product.

Grounded signals may include:

- official price;
- best supported current market price;
- difference from official;
- price history and historical low;
- target-price gap;
- stock across supported merchants;
- sale/offer changes;
- coupon/bank offer data only when reliably retrievable;
- effective price only when applicability and fees are known.

BUY/WAIT should be layered:

1. deterministic conditions — stock, target reached, historical-low rules;
2. statistical history — percentile, median, trend, drop frequency;
3. ML — only after sufficient real labeled/history data exists;
4. LLM explanation — only as a grounded explanation of computed evidence.

An LLM must not freely decide BUY/WAIT or invent a reason unsupported by
observations.

---

# 15. AI and ML Strategy

## 15.1 Hybrid pipeline

```text
raw merchant evidence
    -> structured extraction
    -> deterministic parsing/rules
    -> category classification
    -> attribute extraction
    -> normalization
    -> entity matching/ranking
    -> canonical catalog
```

Use structured merchant data first where trustworthy. Use deterministic rules
for explicit identifiers, known units, and obvious attribute patterns. Use ML
as fallback/assistance when unstructured ambiguity remains.

## 15.2 Useful future ML tasks

- category classification;
- attribute extraction from titles/descriptions;
- cross-store entity-match scoring;
- search and recommendation ranking;
- later price/sale-cycle models when enough history exists.

## 15.3 Data collection before training

Do not train a custom model now. The repository lacks sufficient labeled data.

Preserve or derive useful future examples such as:

- raw title and description;
- merchant and raw category/breadcrumbs;
- predicted and confirmed normalized category;
- raw and normalized attributes;
- model number and global identifiers;
- canonical product/variant decisions;
- matching evidence/confidence;
- later human corrections.

Do not let model output invent a schema per request. Category schemas and the
attribute registry remain controlled application/domain artifacts.

## 15.4 Zero-cost inference

Core functionality cannot depend on a paid hosted LLM/API. If model assistance
materially improves a task, prefer a suitable open-source/pretrained model in
an ephemeral worker, subject to GitHub Actions/runtime limits. Deterministic
fallback must preserve core operation when inference is unavailable.

---

# 16. Infrastructure and Zero-Cost Constraint

The personal/prototype runtime budget is **Rs 0**.

Current platform:

| Responsibility | Component |
| --- | --- |
| Web and lightweight APIs | Vercel free tier |
| Auth and relational/domain data | Supabase free tier |
| Scheduled/background work | GitHub Actions |
| Crawling | Python + Playwright in workers |
| Email | Resend free tier |
| Source/deployment history | GitHub |

Phase 2 should initially stay within this topology.

Rules:

- no paid model/service may be required for core behavior;
- respect free-tier limits and provider terms;
- do not evade quotas with fake or multiple accounts;
- prefer merchant image URLs initially;
- consider a free image/CDN product only for a demonstrated media need;
- do not treat media infrastructure as generic compute;
- keep browser crawling out of Vercel request handlers.

Operational limits to observe include workflow minutes/duration, database
size, egress/bandwidth, request rates, email limits, crawl duration, and
provider policy changes.

---

# 17. Scaling and Distributed-Systems Evolution

```text
start simple
    -> instrument
    -> measure
    -> identify bottleneck and cause
    -> introduce targeted architecture
    -> measure again
```

Evidence-driven options:

- search becomes CPU/latency heavy -> isolate Search Service;
- crawler throughput/fairness becomes limiting -> durable queue + worker pool;
- repeated reads dominate -> cache with explicit invalidation/freshness;
- PostgreSQL catalog search no longer fits -> dedicated search system;
- image bandwidth/transforms become material -> image CDN;
- multiple services need one stable boundary -> API gateway;
- one service needs multiple instances -> load balancer;
- a workload needs a different data model -> a purpose-specific datastore.

Potential later physical layout:

```text
Internet
   -> API Gateway
      -> Search Service
      -> Catalog Service
      -> Watch Service
         -> datastores / cache / queues
         -> crawler workers
         -> classification workers
         -> monitoring workers
```

This is not the immediate implementation. MongoDB, a message broker, or a
microservice is not progress unless a measured access pattern requires it.

Useful early observability before service separation:

- search latency and result source;
- discovery request queue age and completion/failure rate;
- crawl duration by adapter;
- lease reclaim and attempt counts;
- listing freshness;
- normalization and match confidence distributions;
- watch evaluation and notification outcomes;
- free-tier resource usage.

---

# 18. Migration and Compatibility Strategy

Phase 2 changes must be additive and milestone-based.

## 18.1 Before a substantial refactor

1. ensure Git is clean and checkpointed;
2. document the exact target and decision;
3. inventory affected tables/contracts/APIs/workers/UI;
4. define migration and rollback/compatibility behavior;
5. implement one bounded milestone;
6. validate locally and, where needed, against real PostgreSQL/cloud runtime;
7. inspect the diff, commit, push, and update documentation.

## 18.2 Database evolution

- Reuse/evolve Phase 1 tables.
- Add migrations under `supabase/migrations/`.
- Backfill current Nike rows deterministically.
- Keep old keys/fields readable until all consumers migrate.
- Do not mutate production schema manually without a committed migration and
  verification instructions.
- Do not drop Phase 0 tables while product/snapshot compatibility and legacy
  history reads still exist.

## 18.3 Runtime compatibility

During generalization:

- existing Nike URL submission must still work;
- scheduled ingestion and monitoring must still succeed;
- current Nike variant identity must remain stable or have an explicit mapped
  migration;
- current watches, evaluation state, and notification dedupe must survive;
- service-role boundaries and RLS must not be weakened;
- new generic contracts should be introduced before old size-only adapters are
  removed.

## 18.4 Proving generality

Use at least two structurally different fixtures/contracts before adding a
second live source:

```json
{"category":"shoe","variant":{"color":"Black/White","size":"UK 9"}}
```

```json
{"category":"smartphone","variant":{"color":"Titanium Black","storage":"512 GB","ram":"12 GB"}}
```

The purpose is to catch hidden category assumptions early. A second live
electronics adapter comes later in the roadmap after the generalized domain,
normalization, discovery, and UI contracts are ready.

---

# 19. Ordered Roadmap

1. **Generalize the domain model**
   - remove remaining Nike/shoe assumptions;
   - clarify brands, categories, merchant/source roles, and official-source
     metadata;
   - standardize generic product and variant attributes;
   - preserve current production behavior.

2. **Merchant adapter framework**
   - define the shared capability boundary from current code;
   - refactor Nike ingestion and monitoring behind it;
   - keep merchant extraction isolated.

3. **Classification and normalization**
   - category detection;
   - category schemas;
   - generic attribute normalization;
   - deterministic rules first, ML fallback later.

4. **Discovery/search backend**
   - catalog search;
   - supported provider discovery;
   - durable asynchronous enrichment for expensive crawling.

5. **Search-first homepage and result cards**
   - query-driven discovery becomes primary;
   - URL ingestion remains a fallback/advanced path initially.

6. **Dynamic variant selection**
   - derive controls from normalized variant attributes;
   - remove the global shoe-size selector.

7. **Product detail and official-first comparison**
   - official source prominent;
   - alternatives separately ranked/compared;
   - official and cheapest remain distinct.

8. **Second very different category/source**
   - add an electronics example after footwear;
   - prove one architecture handles both without schema/UI redesign.

9. **Cross-store entity resolution**
   - deterministic identifiers first;
   - normalized-spec matching;
   - ML/embedding assistance only where necessary.

10. **Generalized tracking**
    - official only;
    - selected merchants;
    - all supported merchants / best supported offer.

11. **Purchase intelligence**
    - official versus market;
    - history and historical low;
    - target distance;
    - best current supported offer;
    - stock comparison;
    - grounded BUY/WAIT reasoning.

12. **Scale from real evidence**
    - metrics and observability;
    - targeted queues, caches, search infrastructure, services, gateways, or
      load balancing only when justified.

13. **Legacy cleanup**
    - remove Phase 0 compatibility only after replacement architecture is
      production-proven.

---

# 20. Exact Next Engineering Milestone

## Generalize the current catalog/domain model

This is the next implementation milestone after this documentation task.

Goal:

The same shared architecture can represent a Nike Pegasus 42 variant and a
Samsung Galaxy S26 Ultra variant without new category-specific columns or a
separate category-specific shared frontend model.

## 20.1 Required design decisions

The milestone must decide and document:

- canonical attribute-key and value normalization conventions;
- product attributes versus variant attributes;
- category schema shape and how it guides display/validation;
- merchant/channel type;
- official brand/manufacturer source relationship and evidence;
- stable generic variant-key generation/versioning;
- normalized contract changes needed by later dynamic UI;
- migration/backfill and temporary compatibility behavior.

## 20.2 Expected implementation scope

- additive SQL migration(s), if schema changes are required;
- generic domain/normalization contracts;
- current Nike data backfill or metadata enrichment;
- footwear and smartphone fixtures/contract tests;
- compatibility adaptation for current size-based Nike code;
- documentation of final decisions.

## 20.3 Non-goals

- no search UI/backend yet;
- no second live merchant yet;
- no custom-trained model;
- no broad microservice split;
- no Phase 0 table deletion;
- no unsupported claim that arbitrary websites can be crawled.

## 20.4 Acceptance criteria

- Nike example:

  ```json
  {"color":"Black/White","size":"UK 9"}
  ```

  is represented using the same generic mechanism as the phone example:

  ```json
  {"color":"Titanium Black","storage":"512 GB","ram":"12 GB"}
  ```

- No columns such as `phone_storage`, `phone_ram`, `shoe_size`, or
  `laptop_gpu` are introduced.
- Official-source status can be represented without assuming official means
  cheapest and without a misleading global merchant boolean.
- Category metadata can guide a future dynamic UI while allowing additional
  real attributes.
- Variant identity is deterministic and merchant SKU remains merchant-specific.
- Existing Nike ingestion, scheduled monitoring, watch evaluation, and alerts
  remain working.
- RLS/service-role boundaries remain intact.
- Migration and rollback/compatibility verification are documented.
- Relevant tests, Python compilation/tests, and frontend lint/build pass.
- `PROJECT_CONTEXT.md` and this document are updated if implementation choices
  differ from this target design.

---

# 21. Explicitly Deferred Decisions

The following should not be guessed during the next milestone:

- exact search ranking weights;
- a specific dedicated search engine;
- a queue/broker technology;
- a custom ML architecture or training pipeline;
- exact product-detail route/API payloads;
- marketplace seller trust scoring;
- complete coupon/bank-offer modeling;
- a universal effective-price formula without eligibility data;
- a microservice deployment topology;
- a second datastore;
- Phase 0 deletion timing.

Record these decisions when real retrieval data, workload, or a bounded
milestone makes them necessary.

---

# 22. Architecture Summary

Phase 2 keeps the proven Phase 1 foundation and changes the product entry point
and generality:

```text
search-first user intent
    -> supported discovery adapters
    -> normalized evidence
    -> category + generic attributes
    -> canonical product + exact variant
    -> official reference + alternative offers
    -> generalized tracking scope
    -> shared listing monitoring
    -> immutable history
    -> useful alerts
    -> grounded purchase intelligence
```

The core rules are:

- official source first, but not automatically cheapest;
- generic structured attributes, not category columns;
- deterministic identity and retrieval before ML assistance;
- merchant-specific details behind adapters;
- durable async work for expensive discovery;
- real observations before purchase advice;
- zero-rupee operation during the personal/prototype stage;
- scale only in response to measured bottlenecks.
