-- Phase 1 new-product ingestion
--
-- Durable staging requests for products/listings that may need
-- trusted crawler ingestion before a real watch_intent can exist.
--
-- Browser/user path:
--   authenticated user -> tracking_requests -> RLS
--
-- Trusted worker path:
--   service role -> catalog bootstrap -> watch materialization
--
-- See:
--   docs/phase-1-new-product-ingestion.md


-- ============================================================
-- TRACKING REQUESTS
-- ============================================================

create table public.tracking_requests (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    requested_url text not null,

    -- Normalized by application logic before insertion.
    --
    -- The trusted worker MUST still validate and normalize the URL
    -- again before performing network access or catalog writes.
    normalized_url text not null,

    variant_requirements jsonb not null
        default '{}'::jsonb,

    target_price numeric(12, 2)
        check (
            target_price is null
            or target_price >= 0
        ),

    target_currency text not null
        default 'INR',

    conditions jsonb not null
        default '{}'::jsonb,

    status text not null
        default 'pending'
        check (
            status in (
                'pending',
                'processing',
                'completed',
                'failed',
                'cancelled'
            )
        ),

    attempt_count integer not null
        default 0
        check (
            attempt_count >= 0
        ),

    result_product_id uuid
        references public.canonical_products(id)
        on delete set null,

    result_listing_id uuid
        references public.merchant_listings(id)
        on delete set null,

    result_watch_id uuid
        references public.watch_intents(id)
        on delete set null,

    error_code text,
    error_message text,

    created_at timestamptz not null
        default now(),

    updated_at timestamptz not null
        default now(),

    started_at timestamptz,
    completed_at timestamptz
);


-- ============================================================
-- INDEXES
-- ============================================================

create index idx_tracking_requests_user_id
    on public.tracking_requests(user_id);

create index idx_tracking_requests_user_status
    on public.tracking_requests(
        user_id,
        status
    );

create index idx_tracking_requests_status_created_at
    on public.tracking_requests(
        status,
        created_at
    );

create index idx_tracking_requests_normalized_url
    on public.tracking_requests(normalized_url);


-- ============================================================
-- UPDATED_AT
-- ============================================================

create trigger trg_tracking_requests_set_updated_at
before update on public.tracking_requests
for each row
execute function public.set_updated_at();


-- ============================================================
-- PRIVILEGES
--
-- Normal users may:
--   - read their own requests
--   - create requests using only user-controlled input fields
--
-- Normal users must NOT manufacture worker state such as:
--   - completed/failed status
--   - attempt counts
--   - result IDs
--   - processing timestamps
--   - worker errors
-- ============================================================

revoke all
on table public.tracking_requests
from public, anon, authenticated;


grant select
on table public.tracking_requests
to authenticated;


grant insert (
    user_id,
    requested_url,
    normalized_url,
    variant_requirements,
    target_price,
    target_currency,
    conditions
)
on table public.tracking_requests
to authenticated;


-- ============================================================
-- RLS
-- ============================================================

alter table public.tracking_requests
enable row level security;


-- ------------------------------------------------------------
-- SELECT OWN
-- ------------------------------------------------------------

create policy tracking_requests_select_own
on public.tracking_requests
for select
to authenticated
using (
    user_id = (select auth.uid())
);


-- ------------------------------------------------------------
-- INSERT OWN
--
-- status and all worker-owned fields are omitted from the
-- authenticated INSERT privilege above, so their database defaults
-- are authoritative when a user creates a request.
-- ------------------------------------------------------------

create policy tracking_requests_insert_own
on public.tracking_requests
for insert
to authenticated
with check (
    user_id = (select auth.uid())
);
