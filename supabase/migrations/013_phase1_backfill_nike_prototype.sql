begin;

-- Phase 1 Nike prototype backfill
--
-- Migrates only the populated Phase 0 Nike Pegasus Premium chain.
--
-- The two empty Phase 0 prototype product rows are intentionally
-- left untouched and are not copied into the Phase 1 domain.
--
-- This migration is additive. Phase 0 tables remain operational.


-- ============================================================
-- 1. Shared catalog reference data
-- ============================================================


-- ------------------------------------------------------------
-- Category: Running Shoes
-- ------------------------------------------------------------

insert into public.categories (
    slug,
    name,
    attributes_schema
)
values (
    'running-shoes',
    'Running Shoes',
    '{
        "size": {
            "type": "string"
        }
    }'::jsonb
)
on conflict (slug)
do update set
    name = excluded.name,
    attributes_schema = excluded.attributes_schema;


-- ------------------------------------------------------------
-- Brand: Nike
-- ------------------------------------------------------------

insert into public.brands (
    slug,
    name,
    official_url
)
values (
    'nike',
    'Nike',
    'https://www.nike.com/'
)
on conflict (slug)
do update set
    name = excluded.name,
    official_url = excluded.official_url;


-- ------------------------------------------------------------
-- Merchant: Nike India
--
-- adapter_key is the logical crawler adapter identifier.
-- ------------------------------------------------------------

insert into public.merchants (
    slug,
    name,
    base_url,
    adapter_key,
    active
)
values (
    'nike-india',
    'Nike India',
    'https://www.nike.in',
    'nike',
    true
)
on conflict (slug)
do update set
    name = excluded.name,
    base_url = excluded.base_url,
    adapter_key = excluded.adapter_key,
    active = excluded.active;



-- ============================================================
-- 2. Canonical product + Nike merchant listing
-- ============================================================


-- ------------------------------------------------------------
-- Safety check
--
-- This backfill intentionally targets exactly one populated,
-- watched Nike Pegasus Premium Phase 0 product.
-- ------------------------------------------------------------

do $$
declare
    source_count integer;
begin
    select count(*)
    into source_count
    from public.products product
    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%'
      and exists (
          select 1
          from public.watchlists watch
          where watch.product_id = product.id
      );

    if source_count <> 1 then
        raise exception
            'Expected exactly 1 watched Nike Pegasus Premium Phase 0 product, found %',
            source_count;
    end if;
end;
$$;


-- ------------------------------------------------------------
-- Canonical product
--
-- Preserve the Phase 0 product UUID for the canonical product.
-- This gives the backfill a stable, traceable, idempotent key.
--
-- Merchant URL, price and stock deliberately do NOT belong here.
-- ------------------------------------------------------------

insert into public.canonical_products (
    id,
    brand_id,
    category_id,
    name,
    image_url,
    identifiers,
    attributes,
    status,
    created_at,
    updated_at
)
select
    product.id,

    (
        select brand.id
        from public.brands brand
        where brand.slug = 'nike'
    ),

    (
        select category.id
        from public.categories category
        where category.slug = 'running-shoes'
    ),

    product.name,

    product.image_url,

    jsonb_build_object(
        'legacy_phase0_product_id',
        product.id::text
    ),

    '{}'::jsonb,

    'active',

    product.created_at,
    product.updated_at

from public.products product

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'
  and exists (
      select 1
      from public.watchlists watch
      where watch.product_id = product.id
  )

on conflict (id)
do update set
    brand_id = excluded.brand_id,
    category_id = excluded.category_id,
    name = excluded.name,
    image_url = excluded.image_url,
    identifiers = excluded.identifiers,
    attributes = excluded.attributes,
    status = excluded.status;


-- ------------------------------------------------------------
-- Nike merchant listing
--
-- Latest merchant-specific state is copied from Phase 0.
-- Historical price observations are migrated separately.
-- ------------------------------------------------------------

insert into public.merchant_listings (
    product_id,
    merchant_id,
    external_id,
    url,
    title,
    image_url,
    seller_name,
    current_mrp,
    current_price,
    currency,
    in_stock,
    last_checked_at,
    active,
    created_at,
    updated_at
)
select
    product.id,

    (
        select merchant.id
        from public.merchants merchant
        where merchant.slug = 'nike-india'
    ),

    substring(
        product.url
        from '/p/([^/?#]+)'
    ),

    product.url,
    product.name,
    product.image_url,
    'Nike',
    product.mrp,
    product.current_price,
    coalesce(product.currency, 'INR'),
    product.in_stock,
    product.last_checked_at,
    true,
    product.created_at,
    product.updated_at

from public.products product

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'
  and exists (
      select 1
      from public.watchlists watch
      where watch.product_id = product.id
  )

on conflict (url)
do update set
    product_id = excluded.product_id,
    merchant_id = excluded.merchant_id,
    external_id = excluded.external_id,
    title = excluded.title,
    image_url = excluded.image_url,
    seller_name = excluded.seller_name,
    current_mrp = excluded.current_mrp,
    current_price = excluded.current_price,
    currency = excluded.currency,
    in_stock = excluded.in_stock,
    last_checked_at = excluded.last_checked_at,
    active = excluded.active;



-- ============================================================
-- 3. Canonical variants + Nike listing variants
-- ============================================================


-- ------------------------------------------------------------
-- Safety check
--
-- The inspected Phase 0 Nike prototype currently has exactly
-- six merchant size variants.
--
-- If that source changes before this migration is applied,
-- abort instead of silently backfilling a different dataset.
-- ------------------------------------------------------------

do $$
declare
    source_variant_count integer;
begin
    select count(*)
    into source_variant_count
    from public.product_variants variant
    join public.products product
      on product.id = variant.product_id
    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%'
      and exists (
          select 1
          from public.watchlists watch
          where watch.product_id = product.id
      );

    if source_variant_count <> 6 then
        raise exception
            'Expected exactly 6 Nike Pegasus Premium Phase 0 variants, found %',
            source_variant_count;
    end if;
end;
$$;


-- ------------------------------------------------------------
-- Canonical variants
--
-- Phase 0 variant UUIDs are preserved as canonical-variant UUIDs.
--
-- Merchant-specific SKU is intentionally NOT copied into
-- canonical_sku. The current SKU belongs to Nike's listing and
-- is copied into listing_variants.external_sku below.
--
-- Examples:
--
--   "UK 7"          -> canonical size "UK 7"
--   "UK 6 (EU 40)"  -> canonical size "UK 6"
--
-- ------------------------------------------------------------

with source_variants as (
    select
        variant.id,
        product.id as canonical_product_id,
        product.image_url,

        variant.size as merchant_size_label,

        regexp_replace(
            upper(trim(variant.size)),
            '^.*UK[[:space:]]*([0-9]+([.][0-9]+)?).*$',
            'UK \1'
        ) as normalized_size

    from public.product_variants variant

    join public.products product
      on product.id = variant.product_id

    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%'
      and exists (
          select 1
          from public.watchlists watch
          where watch.product_id = product.id
      )
)

insert into public.canonical_variants (
    id,
    product_id,
    title,
    canonical_sku,
    attributes,
    variant_key,
    image_url
)
select
    source.id,
    source.canonical_product_id,
    source.normalized_size,
    null,

    jsonb_build_object(
        'size',
        source.normalized_size
    ),

    'size:' || regexp_replace(
        lower(source.normalized_size),
        '[^a-z0-9.]+',
        '-',
        'g'
    ),

    source.image_url

from source_variants source

on conflict (id)
do update set
    product_id = excluded.product_id,
    title = excluded.title,
    canonical_sku = excluded.canonical_sku,
    attributes = excluded.attributes,
    variant_key = excluded.variant_key,
    image_url = excluded.image_url;


-- ------------------------------------------------------------
-- Nike listing variants
--
-- Preserve:
--
--   Nike merchant SKU
--   raw merchant size label
--   normalized size
--   latest MRP / price
--   stock state
--   stock_remaining
--   last_checked_at
--
-- ------------------------------------------------------------

with source_variants as (
    select
        variant.id as canonical_variant_id,

        product.url as listing_url,
        product.currency,

        variant.size as merchant_size_label,
        variant.sku,
        variant.mrp,
        variant.current_price,
        variant.in_stock,
        variant.stock_remaining,
        variant.last_checked_at,

        regexp_replace(
            upper(trim(variant.size)),
            '^.*UK[[:space:]]*([0-9]+([.][0-9]+)?).*$',
            'UK \1'
        ) as normalized_size

    from public.product_variants variant

    join public.products product
      on product.id = variant.product_id

    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%'
      and exists (
          select 1
          from public.watchlists watch
          where watch.product_id = product.id
      )
)

insert into public.listing_variants (
    listing_id,
    canonical_variant_id,
    external_sku,
    title,
    attributes,
    variant_key,
    current_mrp,
    current_price,
    currency,
    in_stock,
    stock_remaining,
    last_checked_at,
    active
)
select
    listing.id,

    source.canonical_variant_id,

    source.sku,

    source.merchant_size_label,

    jsonb_build_object(
        'size',
        source.normalized_size,
        'merchant_size_label',
        source.merchant_size_label
    ),

    'size:' || regexp_replace(
        lower(source.normalized_size),
        '[^a-z0-9.]+',
        '-',
        'g'
    ),

    source.mrp,
    source.current_price,
    coalesce(source.currency, 'INR'),
    source.in_stock,
    source.stock_remaining,
    source.last_checked_at,
    true

from source_variants source

join public.merchant_listings listing
  on listing.url = source.listing_url

on conflict (listing_id, variant_key)
do update set
    canonical_variant_id = excluded.canonical_variant_id,
    external_sku = excluded.external_sku,
    title = excluded.title,
    attributes = excluded.attributes,
    current_mrp = excluded.current_mrp,
    current_price = excluded.current_price,
    currency = excluded.currency,
    in_stock = excluded.in_stock,
    stock_remaining = excluded.stock_remaining,
    last_checked_at = excluded.last_checked_at,
    active = excluded.active;



-- ============================================================
-- 4. Historical Nike listing observations
-- ============================================================


-- ------------------------------------------------------------
-- Safety check
--
-- We inspected 14 Phase 0 historical snapshots.
--
-- The Phase 0 crawler remains operational while this migration
-- is being prepared, so additional snapshots are acceptable.
--
-- Fewer than 14 means the inspected source history changed or
-- was removed, so abort rather than silently losing history.
-- ------------------------------------------------------------

do $$
declare
    source_snapshot_count integer;
begin
    select count(*)
    into source_snapshot_count

    from public.price_snapshots snapshot

    join public.products product
      on product.id = snapshot.product_id

    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%'
      and exists (
          select 1
          from public.watchlists watch
          where watch.product_id = product.id
      );

    if source_snapshot_count < 14 then
        raise exception
            'Expected at least 14 Nike Pegasus Premium Phase 0 snapshots, found %',
            source_snapshot_count;
    end if;
end;
$$;


-- ------------------------------------------------------------
-- Listing observations
--
-- Preserve exactly what Phase 0 knew:
--
--   checked_at
--   MRP
--   selling price
--   currency
--   overall stock state
--
-- Phase 0 did not know delivery_fee or a separately calculated
-- effective_price, so those remain NULL.
--
-- The Phase 0 snapshot UUID is retained inside raw_data for
-- traceability and idempotency.
-- ------------------------------------------------------------

insert into public.listing_observations (
    listing_id,
    checked_at,
    mrp,
    selling_price,
    currency,
    in_stock,
    stock_remaining,
    delivery_fee,
    effective_price,
    raw_data
)
select
    listing.id,
    snapshot.checked_at,
    snapshot.mrp,
    snapshot.selling_price,
    snapshot.currency,
    snapshot.in_stock,
    null,
    null,
    null,

    jsonb_build_object(
        'source',
        'phase0_price_snapshots',
        'legacy_phase0_price_snapshot_id',
        snapshot.id::text
    )

from public.price_snapshots snapshot

join public.products product
  on product.id = snapshot.product_id

join public.merchant_listings listing
  on listing.url = product.url

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'
  and exists (
      select 1
      from public.watchlists watch
      where watch.product_id = product.id
  )

  and not exists (
      select 1
      from public.listing_observations existing
      where existing.listing_id = listing.id
        and existing.raw_data
            ->> 'legacy_phase0_price_snapshot_id'
            = snapshot.id::text
  );



-- ============================================================
-- 5. User watch intent + Nike listing target
-- ============================================================


-- ------------------------------------------------------------
-- Safety checks
--
-- Expected source:
--
--   exactly 1 Phase 0 watch
--   exactly 1 matching authenticated profile
--   exactly 1 canonical variant matching desired size
--
-- ------------------------------------------------------------

do $$
declare
    source_watch_count integer;
    matched_profile_count integer;
    matched_variant_count integer;
begin

    select count(*)
    into source_watch_count
    from public.watchlists watch
    join public.products product
      on product.id = watch.product_id
    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%';

    if source_watch_count <> 1 then
        raise exception
            'Expected exactly 1 Nike Pegasus Premium Phase 0 watch, found %',
            source_watch_count;
    end if;


    select count(*)
    into matched_profile_count

    from public.watchlists watch

    join public.products product
      on product.id = watch.product_id

    join public.profiles profile
      on lower(profile.email) = lower(watch.email)

    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%';

    if matched_profile_count <> 1 then
        raise exception
            'Expected exactly 1 authenticated profile matching the Phase 0 watch email, found %',
            matched_profile_count;
    end if;


    select count(*)
    into matched_variant_count

    from public.watchlists watch

    join public.products product
      on product.id = watch.product_id

    join public.canonical_variants variant
      on variant.product_id = product.id
     and variant.attributes ->> 'size' =
         regexp_replace(
             upper(trim(watch.desired_size)),
             '^.*UK[[:space:]]*([0-9]+([.][0-9]+)?).*$',
             'UK \1'
         )

    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%';

    if matched_variant_count <> 1 then
        raise exception
            'Expected exactly 1 canonical variant matching the Phase 0 desired size, found %',
            matched_variant_count;
    end if;

end;
$$;


-- ------------------------------------------------------------
-- Watch intent
--
-- Phase 0:
--
--   desired_size = "UK 9"
--   target_price = 18000
--
-- Phase 1:
--
--   canonical_variant_id
--   variant_requirements = {"size":"UK 9"}
--   tracking_scope = specific_listing
--
-- The Phase 0 watch UUID is preserved.
-- ------------------------------------------------------------

insert into public.watch_intents (
    id,
    user_id,
    product_id,
    canonical_variant_id,
    tracking_scope,
    target_price,
    currency,
    variant_requirements,
    conditions,
    status,
    created_at,
    updated_at
)
select
    watch.id,

    profile.id,

    product.id,

    variant.id,

    'specific_listing',

    watch.target_price,

    coalesce(product.currency, 'INR'),

    jsonb_build_object(
        'size',
        variant.attributes ->> 'size'
    ),

    jsonb_build_object(
        'require_in_stock',
        true,
        'notify_target_price',
        true,
        'notify_restock',
        true
    ),

    'active',

    watch.created_at,

    watch.created_at

from public.watchlists watch

join public.products product
  on product.id = watch.product_id

join public.profiles profile
  on lower(profile.email) = lower(watch.email)

join public.canonical_variants variant
  on variant.product_id = product.id
 and variant.attributes ->> 'size' =
     regexp_replace(
         upper(trim(watch.desired_size)),
         '^.*UK[[:space:]]*([0-9]+([.][0-9]+)?).*$',
         'UK \1'
     )

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'

on conflict (id)
do update set
    user_id = excluded.user_id,
    product_id = excluded.product_id,
    canonical_variant_id = excluded.canonical_variant_id,
    tracking_scope = excluded.tracking_scope,
    target_price = excluded.target_price,
    currency = excluded.currency,
    variant_requirements = excluded.variant_requirements,
    conditions = excluded.conditions,
    status = excluded.status;


-- ------------------------------------------------------------
-- Watch -> Nike listing target
--
-- The migrated watch intentionally tracks this specific Nike
-- listing.
--
-- ------------------------------------------------------------

insert into public.watch_listing_targets (
    watch_id,
    listing_id,
    created_at
)
select
    watch.id,
    listing.id,
    watch.created_at

from public.watchlists watch

join public.products product
  on product.id = watch.product_id

join public.merchant_listings listing
  on listing.product_id = product.id
 and listing.url = product.url

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'

on conflict (
    watch_id,
    listing_id
)
do nothing;



-- ============================================================
-- 6. Watch evaluation state + notification preference
-- ============================================================


-- ------------------------------------------------------------
-- Watch evaluation state
--
-- Preserve the Phase 0 evaluator/deduplication state.
--
-- Phase 0:
--
--   last_notified_price
--
-- maps to:
--
--   last_notified_effective_price
--
-- because Phase 0 had no separate offer/effective-price model.
-- ------------------------------------------------------------

insert into public.watch_evaluation_state (
    watch_id,
    condition_met,
    last_reason,
    state,
    last_evaluated_at,
    last_notified_at,
    last_notified_effective_price
)
select
    watch.id,

    legacy_state.condition_met,

    legacy_state.last_reason,

    jsonb_build_object(
        'source',
        'phase0_watch_alert_state',
        'legacy_phase0_watchlist_id',
        watch.id::text
    ),

    legacy_state.last_evaluated_at,

    legacy_state.last_notified_at,

    legacy_state.last_notified_price

from public.watchlists watch

join public.products product
  on product.id = watch.product_id

join public.watch_alert_state legacy_state
  on legacy_state.watchlist_id = watch.id

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'

on conflict (watch_id)
do update set
    condition_met = excluded.condition_met,
    last_reason = excluded.last_reason,
    state = excluded.state,
    last_evaluated_at = excluded.last_evaluated_at,
    last_notified_at = excluded.last_notified_at,
    last_notified_effective_price =
        excluded.last_notified_effective_price;


-- ------------------------------------------------------------
-- Initial notification preference
--
-- Phase 0 used email as its notification channel.
--
-- Experimental channels remain disabled.
--
-- ON CONFLICT DO NOTHING is deliberate:
-- rerunning the backfill must not overwrite later user choices.
-- ------------------------------------------------------------

insert into public.notification_preferences (
    user_id,
    email_enabled,
    email_address,
    push_enabled,
    telegram_enabled,
    whatsapp_enabled
)
select
    profile.id,
    true,
    watch.email,
    false,
    false,
    false

from public.watchlists watch

join public.products product
  on product.id = watch.product_id

join public.profiles profile
  on lower(profile.email) = lower(watch.email)

where product.brand = 'Nike'
  and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
  and product.url like 'https://www.nike.in/%'

on conflict (user_id)
do nothing;



-- ============================================================
-- 7. Final backfill validation
-- ============================================================
--
-- Any mismatch raises an exception.
--
-- Because this migration is wrapped in BEGIN / COMMIT, an
-- exception here rolls back the entire backfill.
-- ============================================================

do $$
declare
    source_product_id uuid;
    source_product_url text;
    source_watch_id uuid;

    source_snapshot_count integer;

    canonical_product_count integer;
    merchant_listing_count integer;
    canonical_variant_count integer;
    listing_variant_count integer;
    migrated_snapshot_count integer;
    watch_intent_count integer;
    watch_target_count integer;
    evaluation_state_count integer;
    notification_preference_count integer;
begin

    -- --------------------------------------------------------
    -- Resolve the one Phase 0 product and watch being migrated.
    -- --------------------------------------------------------

    select
        product.id,
        product.url
    into
        source_product_id,
        source_product_url
    from public.products product
    where product.brand = 'Nike'
      and product.name = 'Nike Pegasus Premium Men''s Road Running Shoes'
      and product.url like 'https://www.nike.in/%'
      and exists (
          select 1
          from public.watchlists watch
          where watch.product_id = product.id
      );


    select watch.id
    into source_watch_id
    from public.watchlists watch
    where watch.product_id = source_product_id;


    -- --------------------------------------------------------
    -- Canonical product
    -- --------------------------------------------------------

    select count(*)
    into canonical_product_count
    from public.canonical_products product
    where product.id = source_product_id;

    if canonical_product_count <> 1 then
        raise exception
            'Backfill validation failed: expected 1 canonical product, found %',
            canonical_product_count;
    end if;


    -- --------------------------------------------------------
    -- Merchant listing
    -- --------------------------------------------------------

    select count(*)
    into merchant_listing_count
    from public.merchant_listings listing
    where listing.product_id = source_product_id
      and listing.url = source_product_url;

    if merchant_listing_count <> 1 then
        raise exception
            'Backfill validation failed: expected 1 Nike listing, found %',
            merchant_listing_count;
    end if;


    -- --------------------------------------------------------
    -- Variants
    -- --------------------------------------------------------

    select count(*)
    into canonical_variant_count
    from public.canonical_variants variant
    where variant.product_id = source_product_id;

    if canonical_variant_count <> 6 then
        raise exception
            'Backfill validation failed: expected 6 canonical variants, found %',
            canonical_variant_count;
    end if;


    select count(*)
    into listing_variant_count
    from public.listing_variants variant
    join public.merchant_listings listing
      on listing.id = variant.listing_id
    where listing.product_id = source_product_id
      and listing.url = source_product_url;

    if listing_variant_count <> 6 then
        raise exception
            'Backfill validation failed: expected 6 listing variants, found %',
            listing_variant_count;
    end if;


    -- --------------------------------------------------------
    -- Historical observations
    --
    -- Compare against the CURRENT Phase 0 source count rather
    -- than hardcoding 14 because the crawler may have added
    -- observations after our inspection.
    -- --------------------------------------------------------

    select count(*)
    into source_snapshot_count
    from public.price_snapshots snapshot
    where snapshot.product_id = source_product_id;


    select count(*)
    into migrated_snapshot_count
    from public.listing_observations observation
    join public.merchant_listings listing
      on listing.id = observation.listing_id
    where listing.product_id = source_product_id
      and listing.url = source_product_url
      and observation.raw_data
            ->> 'source'
            = 'phase0_price_snapshots';

    if migrated_snapshot_count <> source_snapshot_count then
        raise exception
            'Backfill validation failed: expected % migrated snapshots, found %',
            source_snapshot_count,
            migrated_snapshot_count;
    end if;


    -- --------------------------------------------------------
    -- Watch intent
    -- --------------------------------------------------------

    select count(*)
    into watch_intent_count
    from public.watch_intents watch
    where watch.id = source_watch_id
      and watch.product_id = source_product_id
      and watch.tracking_scope = 'specific_listing';

    if watch_intent_count <> 1 then
        raise exception
            'Backfill validation failed: expected 1 watch intent, found %',
            watch_intent_count;
    end if;


    -- --------------------------------------------------------
    -- Watch listing target
    -- --------------------------------------------------------

    select count(*)
    into watch_target_count
    from public.watch_listing_targets target
    join public.merchant_listings listing
      on listing.id = target.listing_id
    where target.watch_id = source_watch_id
      and listing.product_id = source_product_id
      and listing.url = source_product_url;

    if watch_target_count <> 1 then
        raise exception
            'Backfill validation failed: expected 1 watch listing target, found %',
            watch_target_count;
    end if;


    -- --------------------------------------------------------
    -- Evaluation state
    -- --------------------------------------------------------

    select count(*)
    into evaluation_state_count
    from public.watch_evaluation_state state
    where state.watch_id = source_watch_id;

    if evaluation_state_count <> 1 then
        raise exception
            'Backfill validation failed: expected 1 evaluation state, found %',
            evaluation_state_count;
    end if;


    -- --------------------------------------------------------
    -- Notification preference
    -- --------------------------------------------------------

    select count(*)
    into notification_preference_count
    from public.notification_preferences preference
    join public.watch_intents watch
      on watch.user_id = preference.user_id
    where watch.id = source_watch_id;

    if notification_preference_count <> 1 then
        raise exception
            'Backfill validation failed: expected 1 notification preference, found %',
            notification_preference_count;
    end if;

end;
$$;


commit;
