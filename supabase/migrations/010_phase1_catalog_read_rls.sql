-- Phase 1, Milestone 3C
-- Authenticated read-only access to shared catalog data.
--
-- Normal authenticated users may browse:
--
--   categories
--   brands
--   active merchants
--   active canonical products
--   variants belonging to active canonical products
--   active merchant listings
--   active listing variants
--
-- Normal users may NOT create, update or delete catalog data.
--
-- Catalog writes remain trusted backend/crawler responsibilities.
--
-- Historical observation visibility is intentionally NOT handled
-- in this migration.


-- ============================================================
-- Remove broad client privileges.
--
-- Explicit grants below make authenticated catalog access
-- read-only.
-- ============================================================

revoke all
on table
    public.categories,
    public.brands,
    public.merchants,
    public.canonical_products,
    public.canonical_variants,
    public.merchant_listings,
    public.listing_variants
from public, anon, authenticated;


-- ============================================================
-- Authenticated users receive SELECT only.
-- ============================================================

grant select
on table
    public.categories,
    public.brands,
    public.merchants,
    public.canonical_products,
    public.canonical_variants,
    public.merchant_listings,
    public.listing_variants
to authenticated;


-- ============================================================
-- Categories
--
-- Categories are shared catalog metadata.
-- ============================================================

drop policy if exists categories_authenticated_read
on public.categories;


create policy categories_authenticated_read
on public.categories
for select
to authenticated
using (true);


-- ============================================================
-- Brands
--
-- Brands are shared catalog metadata.
-- ============================================================

drop policy if exists brands_authenticated_read
on public.brands;


create policy brands_authenticated_read
on public.brands
for select
to authenticated
using (true);


-- ============================================================
-- Merchants
--
-- Only active merchants are exposed to normal users.
-- ============================================================

drop policy if exists merchants_authenticated_read
on public.merchants;


create policy merchants_authenticated_read
on public.merchants
for select
to authenticated
using (
    active = true
);


-- ============================================================
-- Canonical Products
--
-- Hidden/merged products remain internal.
-- ============================================================

drop policy if exists canonical_products_authenticated_read
on public.canonical_products;


create policy canonical_products_authenticated_read
on public.canonical_products
for select
to authenticated
using (
    status = 'active'
);


-- ============================================================
-- Canonical Variants
--
-- A variant is visible only when its canonical product is
-- visible.
-- ============================================================

drop policy if exists canonical_variants_authenticated_read
on public.canonical_variants;


create policy canonical_variants_authenticated_read
on public.canonical_variants
for select
to authenticated
using (
    exists (
        select 1
        from public.canonical_products product
        where product.id = canonical_variants.product_id
          and product.status = 'active'
    )
);


-- ============================================================
-- Merchant Listings
--
-- Listing must itself be active.
--
-- Its merchant and canonical product must also be visible.
-- ============================================================

drop policy if exists merchant_listings_authenticated_read
on public.merchant_listings;


create policy merchant_listings_authenticated_read
on public.merchant_listings
for select
to authenticated
using (
    active = true

    and exists (
        select 1
        from public.merchants merchant
        where merchant.id = merchant_listings.merchant_id
          and merchant.active = true
    )

    and exists (
        select 1
        from public.canonical_products product
        where product.id = merchant_listings.product_id
          and product.status = 'active'
    )
);


-- ============================================================
-- Listing Variants
--
-- Variant must be active and belong to a listing visible to the
-- authenticated user.
-- ============================================================

drop policy if exists listing_variants_authenticated_read
on public.listing_variants;


create policy listing_variants_authenticated_read
on public.listing_variants
for select
to authenticated
using (
    active = true

    and exists (
        select 1
        from public.merchant_listings listing
        where listing.id = listing_variants.listing_id
          and listing.active = true
    )
);

