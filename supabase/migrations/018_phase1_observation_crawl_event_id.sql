-- Phase 1 new-product ingestion, Milestone D.
--
-- Add explicit crawl-event idempotency identity to Phase 1
-- historical observations.
--
-- Existing historical rows intentionally remain NULL.
--
-- New crawler persistence paths will provide a worker-generated
-- crawl_event_id so retrying the same persistence event cannot
-- create duplicate observations.


-- ============================================================
-- Listing observation crawl-event identity
-- ============================================================

alter table public.listing_observations
    add column if not exists crawl_event_id uuid;


create unique index if not exists
    uq_listing_observations_crawl_event
on public.listing_observations(crawl_event_id)
where crawl_event_id is not null;


-- ============================================================
-- Listing-variant observation crawl-event identity
-- ============================================================

alter table public.listing_variant_observations
    add column if not exists crawl_event_id uuid;


create unique index if not exists
    uq_listing_variant_observations_event_variant
on public.listing_variant_observations(
    crawl_event_id,
    listing_variant_id
)
where crawl_event_id is not null;
