-- Phase 1, Milestone 3D
-- Per-user ownership and access control for watch data.
--
-- Ownership source:
--
--   watch_intents.user_id = auth.uid()
--
-- Child tables inherit ownership through watch_id.
--
-- Normal authenticated users:
--
-- watch_intents:
--   SELECT own
--   INSERT own
--   UPDATE safe watch fields on own rows
--   DELETE own
--
-- watch_listing_targets:
--   SELECT targets belonging to own watches
--   INSERT targets for own watches
--   DELETE targets belonging to own watches
--
-- watch_evaluation_state:
--   SELECT state for own watches
--   NO client writes
--
-- The evaluator/crawler service role remains responsible for
-- writing watch_evaluation_state.


-- ============================================================
-- WATCH INTENTS — PRIVILEGES
-- ============================================================

revoke all
on table public.watch_intents
from public, anon, authenticated;


grant select
on table public.watch_intents
to authenticated;


-- id is generated automatically.
-- timestamps are managed by the database.
--
-- user_id must be supplied and must equal auth.uid(), enforced
-- again by the INSERT RLS policy below.

grant insert (
    user_id,
    product_id,
    canonical_variant_id,
    tracking_scope,
    target_price,
    currency,
    variant_requirements,
    conditions,
    status
)
on table public.watch_intents
to authenticated;


-- Users may modify purchase intent, but cannot change:
--
--   id
--   user_id
--   product_id
--   created_at
--   updated_at
--
-- product_id is immutable because existing watch_listing_targets
-- must always remain associated with the watch's canonical product.

grant update (
    canonical_variant_id,
    tracking_scope,
    target_price,
    currency,
    variant_requirements,
    conditions,
    status
)
on table public.watch_intents
to authenticated;


grant delete
on table public.watch_intents
to authenticated;


-- ============================================================
-- WATCH INTENTS — SELECT
-- ============================================================

drop policy if exists watch_intents_select_own
on public.watch_intents;


create policy watch_intents_select_own
on public.watch_intents
for select
to authenticated
using (
    (select auth.uid()) = user_id
);


-- ============================================================
-- WATCH INTENTS — INSERT
--
-- Requirements:
--
-- 1. watch belongs to authenticated user
-- 2. canonical product is visible to authenticated user
-- 3. optional canonical variant belongs to that product
--
-- Existing catalog RLS automatically filters hidden products
-- and variants from these subqueries.
-- ============================================================

drop policy if exists watch_intents_insert_own
on public.watch_intents;


create policy watch_intents_insert_own
on public.watch_intents
for insert
to authenticated
with check (
    (select auth.uid()) = user_id

    and exists (
        select 1
        from public.canonical_products product
        where product.id = watch_intents.product_id
    )

    and (
        canonical_variant_id is null

        or exists (
            select 1
            from public.canonical_variants variant
            where variant.id = watch_intents.canonical_variant_id
              and variant.product_id = watch_intents.product_id
        )
    )
);


-- ============================================================
-- WATCH INTENTS — UPDATE
--
-- Row must already belong to current user.
--
-- The resulting row must still:
--   - belong to the same authenticated user
--   - reference a visible product
--   - use a variant belonging to that product
--
-- Column privileges prevent changing user_id itself.
-- ============================================================

drop policy if exists watch_intents_update_own
on public.watch_intents;


create policy watch_intents_update_own
on public.watch_intents
for update
to authenticated
using (
    (select auth.uid()) = user_id
)
with check (
    (select auth.uid()) = user_id

    and exists (
        select 1
        from public.canonical_products product
        where product.id = watch_intents.product_id
    )

    and (
        canonical_variant_id is null

        or exists (
            select 1
            from public.canonical_variants variant
            where variant.id = watch_intents.canonical_variant_id
              and variant.product_id = watch_intents.product_id
        )
    )
);


-- ============================================================
-- WATCH INTENTS — DELETE
-- ============================================================

drop policy if exists watch_intents_delete_own
on public.watch_intents;


create policy watch_intents_delete_own
on public.watch_intents
for delete
to authenticated
using (
    (select auth.uid()) = user_id
);


-- ============================================================
-- WATCH LISTING TARGETS — PRIVILEGES
--
-- Association rows are immutable.
--
-- Changing a target means:
--
--   DELETE old target
--   INSERT new target
--
-- Therefore authenticated users receive no UPDATE privilege.
-- ============================================================

revoke all
on table public.watch_listing_targets
from public, anon, authenticated;


grant select
on table public.watch_listing_targets
to authenticated;


grant insert (
    watch_id,
    listing_id
)
on table public.watch_listing_targets
to authenticated;


grant delete
on table public.watch_listing_targets
to authenticated;


-- ============================================================
-- WATCH LISTING TARGETS — SELECT
--
-- Child row is visible only when its watch belongs to the user.
-- ============================================================

drop policy if exists watch_listing_targets_select_own
on public.watch_listing_targets;


create policy watch_listing_targets_select_own
on public.watch_listing_targets
for select
to authenticated
using (
    exists (
        select 1
        from public.watch_intents watch
        where watch.id = watch_listing_targets.watch_id
          and watch.user_id = (select auth.uid())
    )
);


-- ============================================================
-- WATCH LISTING TARGETS — INSERT
--
-- Requirements:
--
-- 1. watch belongs to authenticated user
-- 2. listing is visible to authenticated user
-- 3. listing's canonical product matches watch product
--
-- This prevents, for example:
--
-- watch = Nike Pegasus
-- target listing = Soundcore Q20i
-- ============================================================

drop policy if exists watch_listing_targets_insert_own
on public.watch_listing_targets;


create policy watch_listing_targets_insert_own
on public.watch_listing_targets
for insert
to authenticated
with check (
    exists (
        select 1
        from public.watch_intents watch
        join public.merchant_listings listing
          on listing.id = watch_listing_targets.listing_id
         and listing.product_id = watch.product_id
        where watch.id = watch_listing_targets.watch_id
          and watch.user_id = (select auth.uid())
    )
);


-- ============================================================
-- WATCH LISTING TARGETS — DELETE
-- ============================================================

drop policy if exists watch_listing_targets_delete_own
on public.watch_listing_targets;


create policy watch_listing_targets_delete_own
on public.watch_listing_targets
for delete
to authenticated
using (
    exists (
        select 1
        from public.watch_intents watch
        where watch.id = watch_listing_targets.watch_id
          and watch.user_id = (select auth.uid())
    )
);


-- ============================================================
-- WATCH EVALUATION STATE — PRIVILEGES
--
-- Users need to read their current watch state.
--
-- They must NOT be allowed to manufacture evaluator results,
-- notification state, reasons, or prices.
-- ============================================================

revoke all
on table public.watch_evaluation_state
from public, anon, authenticated;


grant select
on table public.watch_evaluation_state
to authenticated;


-- ============================================================
-- WATCH EVALUATION STATE — SELECT
-- ============================================================

drop policy if exists watch_evaluation_state_select_own
on public.watch_evaluation_state;


create policy watch_evaluation_state_select_own
on public.watch_evaluation_state
for select
to authenticated
using (
    exists (
        select 1
        from public.watch_intents watch
        where watch.id = watch_evaluation_state.watch_id
          and watch.user_id = (select auth.uid())
    )
);

