-- Phase 1, Milestone 1
-- Identity + catalog foundation.
--
-- IMPORTANT:
-- This migration is additive.
-- It does not modify or remove the working Phase 0 tables:
--
--   products
--   product_variants
--   price_snapshots
--   watchlists
--   watch_alert_state
--
-- See:
--   PROJECT_CONTEXT.md
--   docs/phase-1-domain-architecture.md


create extension if not exists pgcrypto;


-- ============================================================
-- updated_at helper
-- ============================================================

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;


-- ============================================================
-- Profiles
--
-- Authentication identity remains owned by Supabase auth.users.
-- public.profiles stores application-specific user information.
--
-- Profile creation trigger and RLS policies will be added in a
-- later Phase 1 milestone.
-- ============================================================

create table if not exists public.profiles (
    id uuid primary key
        references auth.users(id)
        on delete cascade,

    email text,

    display_name text,
    avatar_url text,

    role text not null default 'user'
        check (role in ('user', 'admin', 'super_admin')),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

drop trigger if exists trg_profiles_set_updated_at
    on public.profiles;

create trigger trg_profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();


-- ============================================================
-- Categories
-- ============================================================

create table if not exists public.categories (
    id uuid primary key default gen_random_uuid(),

    slug text not null unique,
    name text not null,

    parent_id uuid
        references public.categories(id)
        on delete set null,

    attributes_schema jsonb,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_categories_parent_id
    on public.categories(parent_id);

drop trigger if exists trg_categories_set_updated_at
    on public.categories;

create trigger trg_categories_set_updated_at
before update on public.categories
for each row
execute function public.set_updated_at();


-- ============================================================
-- Brands
-- ============================================================

create table if not exists public.brands (
    id uuid primary key default gen_random_uuid(),

    slug text not null unique,
    name text not null,

    official_url text,
    logo_url text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

drop trigger if exists trg_brands_set_updated_at
    on public.brands;

create trigger trg_brands_set_updated_at
before update on public.brands
for each row
execute function public.set_updated_at();


-- ============================================================
-- Merchants
--
-- adapter_key identifies the discovery/crawler implementation
-- responsible for this merchant.
-- ============================================================

create table if not exists public.merchants (
    id uuid primary key default gen_random_uuid(),

    slug text not null unique,
    name text not null,

    base_url text not null,

    adapter_key text not null,

    active boolean not null default true,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_merchants_active
    on public.merchants(active);

create index if not exists idx_merchants_adapter_key
    on public.merchants(adapter_key);

drop trigger if exists trg_merchants_set_updated_at
    on public.merchants;

create trigger trg_merchants_set_updated_at
before update on public.merchants
for each row
execute function public.set_updated_at();


-- ============================================================
-- Canonical Products
--
-- Represents the real-world product independent of where it is
-- sold.
--
-- Merchant URLs MUST NOT live in this table.
-- ============================================================

create table if not exists public.canonical_products (
    id uuid primary key default gen_random_uuid(),

    brand_id uuid
        references public.brands(id)
        on delete set null,

    category_id uuid
        references public.categories(id)
        on delete set null,

    name text not null,

    model_name text,
    model_number text,

    description text,
    image_url text,

    identifiers jsonb not null default '{}'::jsonb,
    attributes jsonb not null default '{}'::jsonb,

    status text not null default 'active'
        check (status in ('active', 'hidden', 'merged')),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_canonical_products_brand_id
    on public.canonical_products(brand_id);

create index if not exists idx_canonical_products_category_id
    on public.canonical_products(category_id);

create index if not exists idx_canonical_products_status
    on public.canonical_products(status);

create index if not exists idx_canonical_products_attributes_gin
    on public.canonical_products
    using gin(attributes);

create index if not exists idx_canonical_products_identifiers_gin
    on public.canonical_products
    using gin(identifiers);

drop trigger if exists trg_canonical_products_set_updated_at
    on public.canonical_products;

create trigger trg_canonical_products_set_updated_at
before update on public.canonical_products
for each row
execute function public.set_updated_at();


-- ============================================================
-- Canonical Variants
--
-- Represents meaningful product variants independent of any
-- merchant.
--
-- Examples:
--   {"size":"UK 9","color":"Black"}
--   {"storage_gb":256,"color":"Black"}
--
-- variant_key is produced by application normalization logic.
-- ============================================================

create table if not exists public.canonical_variants (
    id uuid primary key default gen_random_uuid(),

    product_id uuid not null
        references public.canonical_products(id)
        on delete cascade,

    title text,

    canonical_sku text,

    attributes jsonb not null default '{}'::jsonb,

    variant_key text not null,

    image_url text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique(product_id, variant_key)
);

create index if not exists idx_canonical_variants_product_id
    on public.canonical_variants(product_id);

create index if not exists idx_canonical_variants_canonical_sku
    on public.canonical_variants(canonical_sku);

create index if not exists idx_canonical_variants_attributes_gin
    on public.canonical_variants
    using gin(attributes);

drop trigger if exists trg_canonical_variants_set_updated_at
    on public.canonical_variants;

create trigger trg_canonical_variants_set_updated_at
before update on public.canonical_variants
for each row
execute function public.set_updated_at();


-- ============================================================
-- Merchant Listings
--
-- Represents one merchant's listing/page for a canonical
-- product.
--
-- current_* columns are only latest-state cache fields.
-- Historical truth will live in listing_observations.
-- ============================================================

create table if not exists public.merchant_listings (
    id uuid primary key default gen_random_uuid(),

    product_id uuid not null
        references public.canonical_products(id)
        on delete cascade,

    merchant_id uuid not null
        references public.merchants(id),

    external_id text,

    url text not null unique,

    title text,
    image_url text,

    seller_name text,

    current_mrp numeric(12, 2)
        check (current_mrp is null or current_mrp >= 0),

    current_price numeric(12, 2)
        check (current_price is null or current_price >= 0),

    currency text not null default 'INR',

    in_stock boolean,

    last_checked_at timestamptz,

    active boolean not null default true,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_merchant_listings_product_id
    on public.merchant_listings(product_id);

create index if not exists idx_merchant_listings_merchant_id
    on public.merchant_listings(merchant_id);

create index if not exists idx_merchant_listings_product_merchant
    on public.merchant_listings(product_id, merchant_id);

create index if not exists idx_merchant_listings_active
    on public.merchant_listings(active);

create unique index if not exists uq_merchant_listings_external_id
    on public.merchant_listings(merchant_id, external_id)
    where external_id is not null;

drop trigger if exists trg_merchant_listings_set_updated_at
    on public.merchant_listings;

create trigger trg_merchant_listings_set_updated_at
before update on public.merchant_listings
for each row
execute function public.set_updated_at();


-- ============================================================
-- Listing Variants
--
-- Represents merchant-specific purchasable variants.
--
-- canonical_variant_id may temporarily remain null when merchant
-- variant matching has not yet been resolved.
-- ============================================================

create table if not exists public.listing_variants (
    id uuid primary key default gen_random_uuid(),

    listing_id uuid not null
        references public.merchant_listings(id)
        on delete cascade,

    canonical_variant_id uuid
        references public.canonical_variants(id)
        on delete set null,

    external_sku text,

    title text,

    attributes jsonb not null default '{}'::jsonb,

    variant_key text not null,

    current_mrp numeric(12, 2)
        check (current_mrp is null or current_mrp >= 0),

    current_price numeric(12, 2)
        check (current_price is null or current_price >= 0),

    currency text not null default 'INR',

    in_stock boolean,

    stock_remaining integer
        check (
            stock_remaining is null
            or stock_remaining >= 0
        ),

    last_checked_at timestamptz,

    active boolean not null default true,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique(listing_id, variant_key)
);

create index if not exists idx_listing_variants_listing_id
    on public.listing_variants(listing_id);

create index if not exists idx_listing_variants_canonical_variant_id
    on public.listing_variants(canonical_variant_id);

create index if not exists idx_listing_variants_external_sku
    on public.listing_variants(external_sku);

create index if not exists idx_listing_variants_active
    on public.listing_variants(active);

create index if not exists idx_listing_variants_attributes_gin
    on public.listing_variants
    using gin(attributes);

create unique index if not exists uq_listing_variants_external_sku
    on public.listing_variants(listing_id, external_sku)
    where external_sku is not null;

drop trigger if exists trg_listing_variants_set_updated_at
    on public.listing_variants;

create trigger trg_listing_variants_set_updated_at
before update on public.listing_variants
for each row
execute function public.set_updated_at();


-- ============================================================
-- Initial RLS posture
--
-- Phase 1 RLS policies will be introduced separately.
--
-- Enabling RLS now means these tables are deny-by-default for
-- normal anon/authenticated Supabase clients until explicit
-- policies are added.
--
-- The service role used by trusted background jobs can continue
-- to bypass RLS.
-- ============================================================

alter table public.profiles
    enable row level security;

alter table public.categories
    enable row level security;

alter table public.brands
    enable row level security;

alter table public.merchants
    enable row level security;

alter table public.canonical_products
    enable row level security;

alter table public.canonical_variants
    enable row level security;

alter table public.merchant_listings
    enable row level security;

alter table public.listing_variants
    enable row level security;

