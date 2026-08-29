-- Phase 1, Milestone 1.5
-- Historical listing and variant observations.
--
-- This migration is additive.
--
-- It does NOT modify or remove the Phase 0 tables:
--
--   products
--   product_variants
--   price_snapshots
--   watchlists
--   watch_alert_state
--
-- It also does not change runtime behavior yet.
--
-- See:
--   PROJECT_CONTEXT.md
--   docs/phase-1-domain-architecture.md


-- ============================================================
-- Listing Observations
--
-- Immutable historical facts observed from a merchant listing.
--
-- merchant_listings.current_* fields remain the latest-state
-- cache for fast reads.
--
-- This table stores the time series used for:
--
--   historical lows
--   historical highs
--   price trends
--   future deal intelligence
--   migration of legacy price_snapshots
-- ============================================================

create table if not exists public.listing_observations (
    id bigint generated always as identity primary key,

    listing_id uuid not null
        references public.merchant_listings(id)
        on delete cascade,

    checked_at timestamptz not null default now(),

    mrp numeric(12, 2)
        check (
            mrp is null
            or mrp >= 0
        ),

    selling_price numeric(12, 2)
        check (
            selling_price is null
            or selling_price >= 0
        ),

    currency text not null default 'INR',

    in_stock boolean,

    stock_remaining integer
        check (
            stock_remaining is null
            or stock_remaining >= 0
        ),

    delivery_fee numeric(12, 2)
        check (
            delivery_fee is null
            or delivery_fee >= 0
        ),

    effective_price numeric(12, 2)
        check (
            effective_price is null
            or effective_price >= 0
        ),

    raw_data jsonb
);


create index if not exists idx_listing_observations_listing_id
    on public.listing_observations(listing_id);


create index if not exists idx_listing_observations_checked_at
    on public.listing_observations(checked_at desc);


create index if not exists idx_listing_observations_listing_checked
    on public.listing_observations(
        listing_id,
        checked_at desc
    );


create index if not exists idx_listing_observations_selling_price
    on public.listing_observations(
        listing_id,
        selling_price
    )
    where selling_price is not null;


-- ============================================================
-- Listing Variant Observations
--
-- Historical state for one merchant-specific variant.
--
-- Example:
--
-- Nike Pegasus / Nike listing / UK 9
--
-- 10:00  out of stock
-- 12:00  out of stock
-- 14:00  in stock
--
-- This is intentionally separate from overall listing stock.
-- ============================================================

create table if not exists public.listing_variant_observations (
    id bigint generated always as identity primary key,

    listing_variant_id uuid not null
        references public.listing_variants(id)
        on delete cascade,

    checked_at timestamptz not null default now(),

    mrp numeric(12, 2)
        check (
            mrp is null
            or mrp >= 0
        ),

    selling_price numeric(12, 2)
        check (
            selling_price is null
            or selling_price >= 0
        ),

    currency text not null default 'INR',

    in_stock boolean,

    stock_remaining integer
        check (
            stock_remaining is null
            or stock_remaining >= 0
        ),

    raw_data jsonb
);


create index if not exists idx_listing_variant_observations_variant_id
    on public.listing_variant_observations(
        listing_variant_id
    );


create index if not exists idx_listing_variant_observations_checked_at
    on public.listing_variant_observations(
        checked_at desc
    );


create index if not exists idx_listing_variant_observations_variant_checked
    on public.listing_variant_observations(
        listing_variant_id,
        checked_at desc
    );


create index if not exists idx_listing_variant_observations_price
    on public.listing_variant_observations(
        listing_variant_id,
        selling_price
    )
    where selling_price is not null;


-- ============================================================
-- RLS
--
-- No public/user policies are added yet.
--
-- With RLS enabled and no policies:
--
-- anon/authenticated clients:
--     denied
--
-- trusted service-role crawler/backend:
--     allowed
--
-- This matches the current Phase 1 migration posture.
-- ============================================================

alter table public.listing_observations
    enable row level security;


alter table public.listing_variant_observations
    enable row level security;

