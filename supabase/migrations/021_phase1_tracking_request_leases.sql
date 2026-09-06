-- Phase 1 new-product ingestion, Milestone G.
--
-- Add processing leases to tracking_requests.
--
-- attempt_count remains the fencing generation. A reclaim increments it,
-- so work from an older generation cannot renew the current lease or mutate
-- request/watch state guarded by the exact attempt count.
--
-- The lease-duration default lives in trusted worker configuration. The RPC
-- requires it explicitly and independently validates its safe database
-- boundary.
--
-- No attempt ceiling is enforced in this migration. There is not yet enough
-- operational evidence to choose a retry budget without risking permanent
-- failure of a request that remains safe to recover. Eligible work is ordered
-- by when it became eligible: pending.created_at or an expired processing
-- lease_expires_at. Reclaim issues a fresh future deadline, so neither an old
-- stale request nor a continuing stream of newer requests can monopolize the
-- queue.


-- ============================================================
-- LEASE STATE
-- ============================================================

alter table public.tracking_requests
    add column lease_expires_at timestamptz;


-- Migration 021 is deployed while ingestion scheduling is disabled. Any
-- processing row created by the pre-lease worker is therefore deliberately
-- made immediately reclaimable after this migration commits.

update public.tracking_requests
set lease_expires_at = pg_catalog.now()
where status = 'processing'
  and lease_expires_at is null;


-- A processing generation must always have a database deadline. A terminal
-- row may retain its final deadline as diagnostic history; status remains the
-- authoritative reclaim gate.

alter table public.tracking_requests
    add constraint tracking_requests_processing_lease_required
    check (
        status <> 'processing'
        or lease_expires_at is not null
    );


-- The existing status/created_at index continues to support ordinary pending
-- claims. This partial index supports expiry scans without indexing terminal
-- history.

create index idx_tracking_requests_processing_lease_expiry
    on public.tracking_requests (
        lease_expires_at,
        id
    )
    where status = 'processing';


-- ============================================================
-- CLAIM / RECLAIM
--
-- The old one-argument function must be dropped, not retained as an overload.
-- Keeping it would preserve a claim entry point that cannot establish a
-- lease. Adding compatibility defaults to the new overload would also create
-- ambiguous PostgreSQL call resolution. The migration therefore installs one
-- unambiguous trusted RPC signature.
-- ============================================================

drop function public.claim_tracking_requests(integer);


create function public.claim_tracking_requests(
    p_limit integer,
    p_lease_duration_seconds integer
)
returns setof public.tracking_requests
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_now timestamptz := pg_catalog.now();
    v_lease_duration interval;
begin
    if (
        p_limit is null
        or p_limit < 1
        or p_limit > 50
    ) then
        raise exception using
            errcode = '22023',
            message = 'p_limit must be between 1 and 50';
    end if;

    if (
        p_lease_duration_seconds is null
        or p_lease_duration_seconds < 300
        or p_lease_duration_seconds > 1200
    ) then
        raise exception using
            errcode = '22023',
            message = 'p_lease_duration_seconds must be between 300 and 1200';
    end if;

    v_lease_duration := pg_catalog.make_interval(
        secs => p_lease_duration_seconds
    );

    -- ========================================================
    -- Pending claim + expired-generation reclaim
    --
    -- Row locks and SKIP LOCKED allow concurrent queue consumers. Pending
    -- rows become eligible at created_at; stale generations become eligible
    -- at lease_expires_at. Ordering those timestamps together gives both
    -- classes eventual service without another queue-priority threshold.
    -- The increment, new started_at, and new lease deadline commit atomically
    -- as one new processing generation.
    -- ========================================================

    return query
    with candidates as (
        select request.id
        from public.tracking_requests request
        where (
                request.status = 'pending'
                or (
                    request.status = 'processing'
                    and request.lease_expires_at <= v_now
                )
              )
        order by
            case
                when request.status = 'pending'
                    then request.created_at
                else request.lease_expires_at
            end asc,
            request.id asc
        limit p_limit
        for update skip locked
    )
    update public.tracking_requests request
    set
        status = 'processing',
        attempt_count = request.attempt_count + 1,
        started_at = v_now,
        lease_expires_at = v_now + v_lease_duration,
        completed_at = null,
        error_code = null,
        error_message = null
    from candidates
    where request.id = candidates.id
      and (
            request.status = 'pending'
            or (
                request.status = 'processing'
                and request.lease_expires_at <= v_now
            )
          )
    returning request.*;
end;
$$;


-- ============================================================
-- LEASE RENEWAL
--
-- A renewal is allowed only while the exact generation still owns an
-- unexpired processing lease. Zero returned rows means ownership was lost
-- (including expiry, reclaim, completion, failure, cancellation, or a missing
-- request). A retry after an ambiguous response is safe because the deadline
-- is recomputed from database now(), rather than accumulated from the old
-- deadline.
-- ============================================================

create function public.renew_tracking_request_lease(
    p_tracking_request_id uuid,
    p_attempt_count integer,
    p_lease_duration_seconds integer
)
returns setof public.tracking_requests
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_now timestamptz := pg_catalog.now();
    v_lease_duration interval;
begin
    if p_tracking_request_id is null then
        raise exception using
            errcode = '22023',
            message = 'p_tracking_request_id is required';
    end if;

    if (
        p_attempt_count is null
        or p_attempt_count < 1
    ) then
        raise exception using
            errcode = '22023',
            message = 'p_attempt_count must be a positive integer';
    end if;

    if (
        p_lease_duration_seconds is null
        or p_lease_duration_seconds < 300
        or p_lease_duration_seconds > 1200
    ) then
        raise exception using
            errcode = '22023',
            message = 'p_lease_duration_seconds must be between 300 and 1200';
    end if;

    v_lease_duration := pg_catalog.make_interval(
        secs => p_lease_duration_seconds
    );

    return query
    update public.tracking_requests request
    set lease_expires_at = v_now + v_lease_duration
    where request.id = p_tracking_request_id
      and request.status = 'processing'
      and request.attempt_count = p_attempt_count
      and request.lease_expires_at > v_now
    returning request.*;
end;
$$;


-- ============================================================
-- TRUSTED-WORKER PRIVILEGES
-- ============================================================

grant select, update
on table public.tracking_requests
to service_role;


revoke all
on function public.claim_tracking_requests(
    integer,
    integer
)
from public, anon, authenticated;


grant execute
on function public.claim_tracking_requests(
    integer,
    integer
)
to service_role;


revoke all
on function public.renew_tracking_request_lease(
    uuid,
    integer,
    integer
)
from public, anon, authenticated;


grant execute
on function public.renew_tracking_request_lease(
    uuid,
    integer,
    integer
)
to service_role;


-- Function signatures changed in the exposed public schema.
notify pgrst, 'reload schema';
