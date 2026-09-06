\set ON_ERROR_STOP on

-- Migration 021 rollback-only PostgreSQL/Supabase verification.
--
-- Preconditions:
--   * migrations 001-020 are already installed
--   * migration 021 is NOT installed
--   * at least one disposable/test profile exists
--   * the Nike brand and nike-india merchant from migration 013 exist
--   * no pre-existing pending or processing tracking request exists
--
-- Run only against a disposable/local or explicitly approved test database.
-- Do not run this harness against production.
--
-- The exact migration file is loaded inside this transaction. Every schema
-- change, fixture, catalog row, watch, observation, and request is rolled back.

begin;


-- ============================================================
-- BASELINE / LEGACY PROCESSING FIXTURE
--
-- This row must exist before migration 021 adds lease_expires_at so the
-- migration's legacy-NULL behavior is exercised exactly.
-- ============================================================

do $$
begin
    if not exists (
        select 1
        from public.profiles
    ) then
        raise exception
            'Migration 021 harness requires at least one test profile';
    end if;

    if not exists (
        select 1
        from public.brands
        where slug = 'nike'
    ) then
        raise exception
            'Migration 021 harness requires the nike brand';
    end if;

    if not exists (
        select 1
        from public.merchants
        where slug = 'nike-india'
          and adapter_key = 'nike'
          and active = true
    ) then
        raise exception
            'Migration 021 harness requires the active nike-india merchant';
    end if;

    if exists (
        select 1
        from public.tracking_requests request
        where request.status in ('pending', 'processing')
    ) then
        raise exception
            'Migration 021 harness requires an idle tracking-request queue';
    end if;

    if to_regprocedure(
        'public.claim_tracking_requests(integer)'
    ) is null then
        raise exception
            'Expected migration 017 claim signature is missing';
    end if;

    if to_regprocedure(
        'public.claim_tracking_requests(integer,integer)'
    ) is not null then
        raise exception
            'Migration 021 already appears to be installed';
    end if;
end;
$$;


insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url,
    status,
    attempt_count,
    started_at,
    created_at
)
select
    '02100000-0000-4000-8000-000000000001'::uuid,
    profile.id,
    'https://www.nike.in/lease-harness-legacy/p/02100001',
    'https://www.nike.in/lease-harness-legacy/p/02100001',
    'processing',
    1,
    pg_catalog.now() - interval '10 minutes',
    pg_catalog.now() - interval '10 minutes'
from public.profiles profile
order by profile.id
limit 1;


\ir ../migrations/021_phase1_tracking_request_leases.sql


-- ============================================================
-- INSTALLED SHAPE, VERSIONING, AND PRIVILEGES
-- ============================================================

do $$
declare
    v_claim_oid oid;
    v_renew_oid oid;
begin
    if not exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'tracking_requests'
          and column_name = 'lease_expires_at'
          and data_type = 'timestamp with time zone'
          and is_nullable = 'YES'
    ) then
        raise exception
            'lease_expires_at column was not installed as timestamptz';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_constraint constraint_row
        where constraint_row.conrelid =
              'public.tracking_requests'::regclass
          and constraint_row.conname =
              'tracking_requests_processing_lease_required'
          and constraint_row.contype = 'c'
          and constraint_row.convalidated = true
    ) then
        raise exception
            'Processing lease check constraint is missing or unvalidated';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_class index_relation
        join pg_catalog.pg_index index_row
          on index_row.indexrelid = index_relation.oid
        where index_relation.relnamespace =
              'public'::regnamespace
          and index_relation.relname =
              'idx_tracking_requests_processing_lease_expiry'
          and index_row.indrelid =
              'public.tracking_requests'::regclass
          and index_row.indpred is not null
    ) then
        raise exception
            'Processing lease partial index is missing';
    end if;

    if to_regprocedure(
        'public.claim_tracking_requests(integer)'
    ) is not null then
        raise exception
            'Old one-argument claim signature remains installed';
    end if;

    v_claim_oid := to_regprocedure(
        'public.claim_tracking_requests(integer,integer)'
    );

    v_renew_oid := to_regprocedure(
        'public.renew_tracking_request_lease(uuid,integer,integer)'
    );

    if v_claim_oid is null or v_renew_oid is null then
        raise exception
            'Migration 021 RPC signatures are missing';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_proc procedure_row
        where procedure_row.oid in (v_claim_oid, v_renew_oid)
          and procedure_row.prosecdef = true
    ) then
        raise exception
            'Lease RPCs must be SECURITY INVOKER';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_proc procedure_row
        where procedure_row.oid in (v_claim_oid, v_renew_oid)
          and not exists (
              select 1
              from unnest(
                  coalesce(
                      procedure_row.proconfig,
                      array[]::text[]
                  )
              ) configuration(setting)
              where configuration.setting like 'search_path=%'
          )
    ) then
        raise exception
            'Lease RPCs must set an explicit empty search_path';
    end if;

    if not has_function_privilege(
        'service_role',
        v_claim_oid,
        'EXECUTE'
    ) or not has_function_privilege(
        'service_role',
        v_renew_oid,
        'EXECUTE'
    ) then
        raise exception
            'service_role cannot execute both lease RPCs';
    end if;

    if has_function_privilege(
        'anon',
        v_claim_oid,
        'EXECUTE'
    ) or has_function_privilege(
        'authenticated',
        v_claim_oid,
        'EXECUTE'
    ) or has_function_privilege(
        'anon',
        v_renew_oid,
        'EXECUTE'
    ) or has_function_privilege(
        'authenticated',
        v_renew_oid,
        'EXECUTE'
    ) then
        raise exception
            'Browser roles must not execute lease RPCs';
    end if;

    if has_column_privilege(
        'authenticated',
        'public.tracking_requests',
        'lease_expires_at',
        'INSERT'
    ) or has_column_privilege(
        'authenticated',
        'public.tracking_requests',
        'lease_expires_at',
        'UPDATE'
    ) then
        raise exception
            'authenticated may mutate lease_expires_at';
    end if;
end;
$$;


-- ============================================================
-- LEGACY NULL LEASE -> IMMEDIATE RECLAIM
-- ============================================================

do $$
declare
    v_claim public.tracking_requests%rowtype;
begin
    if not exists (
        select 1
        from public.tracking_requests request
        where request.id =
              '02100000-0000-4000-8000-000000000001'::uuid
          and request.status = 'processing'
          and request.attempt_count = 1
          and request.lease_expires_at is not null
          and request.lease_expires_at <= pg_catalog.now()
    ) then
        raise exception
            'Legacy processing row was not made immediately reclaimable';
    end if;

    select claimed.*
    into v_claim
    from public.claim_tracking_requests(
        1,
        300
    ) claimed;

    if not found
       or v_claim.id <>
          '02100000-0000-4000-8000-000000000001'::uuid
       or v_claim.status <> 'processing'
       or v_claim.attempt_count <> 2
       or v_claim.started_at <> pg_catalog.now()
       or v_claim.lease_expires_at <>
          pg_catalog.now() + interval '300 seconds' then
        raise exception
            'Legacy processing row was not reclaimed as generation 2';
    end if;

    update public.tracking_requests
    set status = 'cancelled'
    where id = v_claim.id;
end;
$$;


-- ============================================================
-- ORDINARY PENDING CLAIM
-- ============================================================

insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url,
    error_code,
    error_message,
    completed_at
)
select
    '02100000-0000-4000-8000-000000000002'::uuid,
    profile.id,
    'https://www.nike.in/lease-harness-pending/p/02100002',
    'https://www.nike.in/lease-harness-pending/p/02100002',
    'stale_error',
    'stale message',
    pg_catalog.now() - interval '1 day'
from public.profiles profile
order by profile.id
limit 1;


do $$
declare
    v_claim public.tracking_requests%rowtype;
begin
    select claimed.*
    into v_claim
    from public.claim_tracking_requests(
        1,
        300
    ) claimed;

    if not found
       or v_claim.id <>
          '02100000-0000-4000-8000-000000000002'::uuid
       or v_claim.status <> 'processing'
       or v_claim.attempt_count <> 1
       or v_claim.started_at <> pg_catalog.now()
       or v_claim.lease_expires_at <>
          pg_catalog.now() + interval '300 seconds'
       or v_claim.error_code is not null
       or v_claim.error_message is not null
       or v_claim.completed_at is not null then
        raise exception
            'Pending request claim did not establish clean generation 1';
    end if;

    update public.tracking_requests
    set
        status = 'completed',
        completed_at = pg_catalog.now()
    where id = v_claim.id;
end;
$$;


-- ============================================================
-- UNEXPIRED EXCLUSION, RENEWAL, RECLAIM, AND OLD-GENERATION FENCE
-- ============================================================

insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url,
    status,
    attempt_count,
    started_at,
    lease_expires_at
)
select
    '02100000-0000-4000-8000-000000000003'::uuid,
    profile.id,
    'https://www.nike.in/lease-harness-renew/p/02100003',
    'https://www.nike.in/lease-harness-renew/p/02100003',
    'processing',
    4,
    pg_catalog.now(),
    pg_catalog.now() + interval '300 seconds'
from public.profiles profile
order by profile.id
limit 1;


do $$
declare
    v_count integer;
    v_renewed public.tracking_requests%rowtype;
    v_renewed_replay public.tracking_requests%rowtype;
    v_claim public.tracking_requests%rowtype;
    v_row_count integer;
begin
    select count(*)
    into v_count
    from public.claim_tracking_requests(
        1,
        300
    );

    if v_count <> 0 then
        raise exception
            'Unexpired processing request was reclaimed';
    end if;

    select renewed.*
    into v_renewed
    from public.renew_tracking_request_lease(
        '02100000-0000-4000-8000-000000000003'::uuid,
        4,
        600
    ) renewed;

    if not found
       or v_renewed.attempt_count <> 4
       or v_renewed.lease_expires_at <>
          pg_catalog.now() + interval '600 seconds' then
        raise exception
            'Current processing generation could not renew its lease';
    end if;

    -- Model a committed renewal whose response was lost. Retrying the same
    -- exact generation remains safe and does not issue a new generation.
    select renewed.*
    into v_renewed_replay
    from public.renew_tracking_request_lease(
        '02100000-0000-4000-8000-000000000003'::uuid,
        4,
        600
    ) renewed;

    if not found
       or v_renewed_replay.attempt_count <> 4
       or v_renewed_replay.lease_expires_at <>
          pg_catalog.now() + interval '600 seconds' then
        raise exception
            'Lost-response renewal retry was not safe';
    end if;

    update public.tracking_requests
    set lease_expires_at = pg_catalog.now() - interval '1 second'
    where id =
          '02100000-0000-4000-8000-000000000003'::uuid;

    select count(*)
    into v_count
    from public.renew_tracking_request_lease(
        '02100000-0000-4000-8000-000000000003'::uuid,
        4,
        300
    );

    if v_count <> 0 then
        raise exception
            'Expired processing lease was resurrected by renewal';
    end if;

    select claimed.*
    into v_claim
    from public.claim_tracking_requests(
        1,
        300
    ) claimed;

    if not found
       or v_claim.id <>
          '02100000-0000-4000-8000-000000000003'::uuid
       or v_claim.attempt_count <> 5
       or v_claim.lease_expires_at <>
          pg_catalog.now() + interval '300 seconds' then
        raise exception
            'Expired request was not reclaimed as a new generation';
    end if;

    select count(*)
    into v_count
    from public.renew_tracking_request_lease(
        '02100000-0000-4000-8000-000000000003'::uuid,
        4,
        300
    );

    if v_count <> 0 then
        raise exception
            'Old generation renewed the newer generation lease';
    end if;

    update public.tracking_requests
    set
        status = 'failed',
        error_code = 'old_worker',
        error_message = 'must not persist'
    where id =
          '02100000-0000-4000-8000-000000000003'::uuid
      and status = 'processing'
      and attempt_count = 4;

    get diagnostics v_row_count = row_count;

    if v_row_count <> 0 then
        raise exception
            'Old generation marked the newer generation failed';
    end if;

    begin
        perform public.materialize_phase1_tracking_request(
            '02100000-0000-4000-8000-000000000003'::uuid,
            4,
            '02100000-0000-4000-8000-00000000f001'::uuid,
            '02100000-0000-4000-8000-00000000f002'::uuid,
            'https://www.nike.in/lease-harness-renew/p/02100003',
            null,
            null
        );

        raise exception
            'Old generation unexpectedly materialized a watch';
    exception
        when others then
            if sqlerrm not like '%attempt is stale%' then
                raise;
            end if;
    end;

    update public.tracking_requests
    set status = 'cancelled'
    where id = v_claim.id;
end;
$$;


-- ============================================================
-- FAIR ELIGIBILITY: OLDER EXPIRED LEASE, THEN PENDING ROTATION
--
-- Pending rows are eligible from created_at. Expired processing rows are
-- eligible from lease_expires_at. The stale row below became eligible first,
-- so it must be reclaimed before the newer pending row. Its new future lease
-- then makes it ineligible, allowing the pending row to rotate in on the next
-- claim. Attempt 3 -> 4 also proves that no attempt ceiling was introduced.
-- ============================================================

insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url,
    status,
    attempt_count,
    started_at,
    lease_expires_at,
    error_code,
    error_message,
    created_at
)
select
    fixture.id,
    profile.id,
    fixture.url,
    fixture.url,
    fixture.status,
    fixture.attempt_count,
    fixture.started_at,
    fixture.lease_expires_at,
    fixture.error_code,
    fixture.error_message,
    fixture.created_at
from (
    values
        (
            '02100000-0000-4000-8000-000000000004'::uuid,
            'https://www.nike.in/lease-harness-repeated/p/02100004'::text,
            'processing'::text,
            3,
            pg_catalog.now() - interval '20 minutes',
            pg_catalog.now() - interval '10 minutes',
            'stale_error'::text,
            'stale message'::text,
            pg_catalog.now() - interval '20 minutes'
        ),
        (
            '02100000-0000-4000-8000-000000000005'::uuid,
            'https://www.nike.in/lease-harness-fair-newer-pending/p/02100005'::text,
            'pending'::text,
            0,
            null::timestamptz,
            null::timestamptz,
            null::text,
            null::text,
            pg_catalog.now() - interval '5 minutes'
        )
) fixture(
    id,
    url,
    status,
    attempt_count,
    started_at,
    lease_expires_at,
    error_code,
    error_message,
    created_at
)
cross join lateral (
    select id
    from public.profiles
    order by id
    limit 1
) profile;


do $$
declare
    v_reclaimed public.tracking_requests%rowtype;
    v_pending_claim public.tracking_requests%rowtype;
begin
    select claimed.*
    into v_reclaimed
    from public.claim_tracking_requests(
        1,
        300
    ) claimed;

    if not found
       or v_reclaimed.id <>
          '02100000-0000-4000-8000-000000000004'::uuid
       or v_reclaimed.status <> 'processing'
       or v_reclaimed.attempt_count <> 4
       or v_reclaimed.lease_expires_at <= pg_catalog.now()
       or v_reclaimed.error_code is not null
       or v_reclaimed.error_message is not null then
        raise exception
            'Oldest expired eligibility was not reclaimed as attempt 4';
    end if;

    if not exists (
        select 1
        from public.tracking_requests request
        where request.id =
              '02100000-0000-4000-8000-000000000005'::uuid
          and request.status = 'pending'
          and request.attempt_count = 0
    ) then
        raise exception
            'Expired-first fairness claim mutated newer pending work';
    end if;

    select claimed.*
    into v_pending_claim
    from public.claim_tracking_requests(
        1,
        300
    ) claimed;

    if not found
       or v_pending_claim.id <>
          '02100000-0000-4000-8000-000000000005'::uuid
       or v_pending_claim.status <> 'processing'
       or v_pending_claim.attempt_count <> 1 then
        raise exception
            'Fresh reclaim lease did not rotate service to pending work';
    end if;

    if not exists (
        select 1
        from public.tracking_requests request
        where request.id = v_reclaimed.id
          and request.status = 'processing'
          and request.attempt_count = 4
          and request.lease_expires_at > pg_catalog.now()
    ) then
        raise exception
            'Reclaimed request did not retain its fresh unexpired lease';
    end if;

    update public.tracking_requests
    set status = 'cancelled'
    where id = v_reclaimed.id;

    update public.tracking_requests
    set
        status = 'completed',
        completed_at = pg_catalog.now()
    where id = v_pending_claim.id;
end;
$$;


-- ============================================================
-- FAIR ELIGIBILITY: OLDER PENDING BEFORE LATER EXPIRY
--
-- The processing row was created first, but its lease expired after the
-- pending row was created. eligible_since, not original request age or status
-- class, must therefore select the pending row.
-- ============================================================

insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url,
    status,
    attempt_count,
    started_at,
    lease_expires_at,
    created_at
)
select
    fixture.id,
    profile.id,
    fixture.url,
    fixture.url,
    fixture.status,
    fixture.attempt_count,
    fixture.started_at,
    fixture.lease_expires_at,
    fixture.created_at
from (
    values
        (
            '02100000-0000-4000-8000-000000000014'::uuid,
            'https://www.nike.in/lease-harness-fair-pending/p/02100014'::text,
            'pending'::text,
            0,
            null::timestamptz,
            null::timestamptz,
            pg_catalog.now() - interval '20 minutes'
        ),
        (
            '02100000-0000-4000-8000-000000000015'::uuid,
            'https://www.nike.in/lease-harness-fair-expired/p/02100015'::text,
            'processing'::text,
            6,
            pg_catalog.now() - interval '30 minutes',
            pg_catalog.now() - interval '10 minutes',
            pg_catalog.now() - interval '1 day'
        )
) fixture(
    id,
    url,
    status,
    attempt_count,
    started_at,
    lease_expires_at,
    created_at
)
cross join lateral (
    select id
    from public.profiles
    order by id
    limit 1
) profile;


do $$
declare
    v_pending_claim public.tracking_requests%rowtype;
begin
    select claimed.*
    into v_pending_claim
    from public.claim_tracking_requests(
        1,
        300
    ) claimed;

    if not found
       or v_pending_claim.id <>
          '02100000-0000-4000-8000-000000000014'::uuid
       or v_pending_claim.status <> 'processing'
       or v_pending_claim.attempt_count <> 1 then
        raise exception
            'Older pending eligibility was not selected before later expiry';
    end if;

    if not exists (
        select 1
        from public.tracking_requests request
        where request.id =
              '02100000-0000-4000-8000-000000000015'::uuid
          and request.status = 'processing'
          and request.attempt_count = 6
          and request.lease_expires_at =
              pg_catalog.now() - interval '10 minutes'
    ) then
        raise exception
            'Pending eligibility claim mutated later expired work';
    end if;

    update public.tracking_requests
    set
        status = 'completed',
        completed_at = pg_catalog.now()
    where id = v_pending_claim.id;

    update public.tracking_requests
    set status = 'cancelled'
    where id =
          '02100000-0000-4000-8000-000000000015'::uuid;
end;
$$;


-- ============================================================
-- TERMINAL STATES ARE NEVER RECLAIMED
-- ============================================================

insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url,
    status,
    attempt_count,
    started_at,
    completed_at,
    lease_expires_at
)
select
    fixture.id,
    profile.id,
    fixture.url,
    fixture.url,
    fixture.status,
    7,
    pg_catalog.now() - interval '1 day',
    pg_catalog.now() - interval '1 day',
    pg_catalog.now() - interval '1 day'
from (
    values
        (
            '02100000-0000-4000-8000-000000000006'::uuid,
            'https://www.nike.in/lease-harness-completed/p/02100006'::text,
            'completed'::text
        ),
        (
            '02100000-0000-4000-8000-000000000007'::uuid,
            'https://www.nike.in/lease-harness-failed/p/02100007'::text,
            'failed'::text
        ),
        (
            '02100000-0000-4000-8000-000000000008'::uuid,
            'https://www.nike.in/lease-harness-cancelled/p/02100008'::text,
            'cancelled'::text
        )
) fixture(id, url, status)
cross join lateral (
    select id
    from public.profiles
    order by id
    limit 1
) profile;


do $$
declare
    v_count integer;
begin
    select count(*)
    into v_count
    from public.claim_tracking_requests(
        10,
        300
    );

    if v_count <> 0 then
        raise exception
            'A terminal request was reclaimed';
    end if;

    if exists (
        select 1
        from public.tracking_requests request
        where request.id in (
            '02100000-0000-4000-8000-000000000006'::uuid,
            '02100000-0000-4000-8000-000000000007'::uuid,
            '02100000-0000-4000-8000-000000000008'::uuid
        )
          and request.attempt_count <> 7
    ) then
        raise exception
            'A terminal request generation changed';
    end if;

    select count(*)
    into v_count
    from (
        select renewed.id
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000006'::uuid,
            7,
            300
        ) renewed

        union all

        select renewed.id
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000007'::uuid,
            7,
            300
        ) renewed

        union all

        select renewed.id
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000008'::uuid,
            7,
            300
        ) renewed
    ) terminal_renewals;

    if v_count <> 0 then
        raise exception
            'A terminal request renewed a processing lease';
    end if;
end;
$$;


-- ============================================================
-- CONDITIONAL LEASE CONSTRAINT
-- ============================================================

do $$
begin
    begin
        insert into public.tracking_requests (
            id,
            user_id,
            requested_url,
            normalized_url,
            status,
            attempt_count,
            started_at
        )
        select
            '02100000-0000-4000-8000-000000000009'::uuid,
            profile.id,
            'https://www.nike.in/lease-harness-no-deadline/p/02100009',
            'https://www.nike.in/lease-harness-no-deadline/p/02100009',
            'processing',
            1,
            pg_catalog.now()
        from public.profiles profile
        order by profile.id
        limit 1;

        raise exception
            'Processing row without a lease passed its constraint';
    exception
        when check_violation then
            null;
    end;
end;
$$;


-- ============================================================
-- MALFORMED POLICY / RENEWAL INPUTS
-- ============================================================

do $$
begin
    begin
        perform 1
        from public.claim_tracking_requests(null, 300);
        raise exception 'NULL claim limit was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.claim_tracking_requests(0, 300);
        raise exception 'Zero claim limit was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.claim_tracking_requests(51, 300);
        raise exception 'Oversized claim limit was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.claim_tracking_requests(1, null);
        raise exception 'NULL claim lease duration was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.claim_tracking_requests(1, 299);
        raise exception 'Short claim lease duration was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.claim_tracking_requests(1, 1201);
        raise exception 'Long claim lease duration was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.renew_tracking_request_lease(null, 1, 300);
        raise exception 'NULL renewal request id was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000003'::uuid,
            null,
            300
        );
        raise exception 'NULL renewal attempt was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000003'::uuid,
            0,
            300
        );
        raise exception 'Zero renewal attempt was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000003'::uuid,
            1,
            null
        );
        raise exception 'NULL renewal duration was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000003'::uuid,
            1,
            299
        );
        raise exception 'Short renewal duration was accepted';
    exception when sqlstate '22023' then null;
    end;

    begin
        perform 1
        from public.renew_tracking_request_lease(
            '02100000-0000-4000-8000-000000000003'::uuid,
            1,
            1201
        );
        raise exception 'Long renewal duration was accepted';
    exception when sqlstate '22023' then null;
    end;
end;
$$;


-- ============================================================
-- MIGRATION 019 IDEMPOTENCY + MIGRATION 020 TERMINAL REPLAY
--
-- This models a materialization response that is lost after commit: retrying
-- the exact call must return the completed result and must not add a watch.
-- It also verifies duplicate-watch terminal replay after a lost response.
-- ============================================================

do $$
declare
    v_user_id uuid;
    v_claim public.tracking_requests%rowtype;
    v_duplicate_claim public.tracking_requests%rowtype;
    v_bootstrap jsonb;
    v_bootstrap_replay jsonb;
    v_materialized jsonb;
    v_materialized_replay jsonb;
    v_duplicate jsonb;
    v_duplicate_replay jsonb;
    v_product_id uuid;
    v_listing_id uuid;
    v_variant_id uuid;
    v_watch_id uuid;
    v_watch_count integer;
    v_product jsonb;
begin
    select profile.id
    into strict v_user_id
    from public.profiles profile
    order by profile.id
    limit 1;

    insert into public.tracking_requests (
        id,
        user_id,
        requested_url,
        normalized_url,
        variant_requirements,
        target_price,
        target_currency,
        conditions
    )
    values (
        '02100000-0000-4000-8000-000000000010'::uuid,
        v_user_id,
        'https://www.nike.in/lease-harness-materialize/p/02100010',
        'https://www.nike.in/lease-harness-materialize/p/02100010',
        '{"size":"UK 9"}'::jsonb,
        12500,
        'INR',
        '{"require_in_stock":true}'::jsonb
    );

    select claimed.*
    into strict v_claim
    from public.claim_tracking_requests(1, 300) claimed;

    if v_claim.id <>
       '02100000-0000-4000-8000-000000000010'::uuid
       or v_claim.attempt_count <> 1 then
        raise exception
            'Materialization fixture was not claimed as generation 1';
    end if;

    v_product := pg_catalog.jsonb_build_object(
        'name', 'Migration 021 Materialization Harness',
        'image_url', 'https://static.example.test/02100010.png',
        'external_id', '02100010',
        'mrp', 15000,
        'current_price', 14000,
        'currency', 'INR',
        'in_stock', true,
        'variants', pg_catalog.jsonb_build_array(
            pg_catalog.jsonb_build_object(
                'variant_key', 'size:uk-9',
                'canonical_title', 'UK 9',
                'canonical_attributes', '{"size":"UK 9"}'::jsonb,
                'external_sku', '02100010-UK9',
                'listing_title', 'UK 9',
                'listing_attributes', '{"size":"UK 9"}'::jsonb,
                'mrp', 15000,
                'current_price', 14000,
                'in_stock', true,
                'stock_remaining', 2
            )
        )
    );

    v_bootstrap := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_claim.normalized_url,
        '02110000-0000-4000-8000-000000000010'::uuid,
        v_claim.started_at,
        v_product
    );

    v_bootstrap_replay := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_claim.normalized_url,
        '02110000-0000-4000-8000-000000000010'::uuid,
        v_claim.started_at,
        v_product
    );

    if v_bootstrap_replay ->> 'product_id' <>
       v_bootstrap ->> 'product_id'
       or v_bootstrap_replay ->> 'listing_id' <>
          v_bootstrap ->> 'listing_id'
       or (v_bootstrap_replay ->> 'observation_created')::boolean then
        raise exception
            'Migration 019 exact-event bootstrap replay was not idempotent';
    end if;

    v_product_id := (v_bootstrap ->> 'product_id')::uuid;
    v_listing_id := (v_bootstrap ->> 'listing_id')::uuid;
    v_variant_id := (
        v_bootstrap #>> '{variants,0,canonical_variant_id}'
    )::uuid;

    if (
        select count(*)
        from public.listing_observations observation
        where observation.crawl_event_id =
              '02110000-0000-4000-8000-000000000010'::uuid
    ) <> 1 or (
        select count(*)
        from public.listing_variant_observations observation
        where observation.crawl_event_id =
              '02110000-0000-4000-8000-000000000010'::uuid
    ) <> 1 then
        raise exception
            'Migration 019 replay duplicated historical observations';
    end if;

    v_materialized := public.materialize_phase1_tracking_request(
        v_claim.id,
        v_claim.attempt_count,
        v_product_id,
        v_listing_id,
        v_claim.normalized_url,
        v_variant_id,
        'size:uk-9'
    );

    v_watch_id := (v_materialized ->> 'watch_id')::uuid;

    select count(*)
    into v_watch_count
    from public.watch_intents watch
    join public.watch_listing_targets target
      on target.watch_id = watch.id
    where watch.user_id = v_user_id
      and target.listing_id = v_listing_id
      and watch.canonical_variant_id = v_variant_id
      and watch.status <> 'archived';

    if v_materialized ->> 'outcome' <> 'completed'
       or (v_materialized ->> 'already_completed')::boolean
       or v_watch_count <> 1 then
        raise exception
            'Migration 020 initial materialization was not atomic';
    end if;

    v_materialized_replay :=
        public.materialize_phase1_tracking_request(
            v_claim.id,
            v_claim.attempt_count,
            v_product_id,
            v_listing_id,
            v_claim.normalized_url,
            v_variant_id,
            'size:uk-9'
        );

    select count(*)
    into v_watch_count
    from public.watch_intents watch
    join public.watch_listing_targets target
      on target.watch_id = watch.id
    where watch.user_id = v_user_id
      and target.listing_id = v_listing_id
      and watch.canonical_variant_id = v_variant_id
      and watch.status <> 'archived';

    if v_materialized_replay ->> 'outcome' <> 'completed'
       or not (
            v_materialized_replay ->> 'already_completed'
          )::boolean
       or (v_materialized_replay ->> 'watch_id')::uuid <>
          v_watch_id
       or v_watch_count <> 1 then
        raise exception
            'Lost-response completed replay created another watch';
    end if;

    insert into public.tracking_requests (
        id,
        user_id,
        requested_url,
        normalized_url,
        variant_requirements,
        target_price,
        target_currency,
        conditions
    )
    values (
        '02100000-0000-4000-8000-000000000011'::uuid,
        v_user_id,
        v_claim.normalized_url,
        v_claim.normalized_url,
        '{"size":"UK 9"}'::jsonb,
        12000,
        'INR',
        '{"require_in_stock":true}'::jsonb
    );

    select claimed.*
    into strict v_duplicate_claim
    from public.claim_tracking_requests(1, 300) claimed;

    if v_duplicate_claim.id <>
       '02100000-0000-4000-8000-000000000011'::uuid then
        raise exception
            'Duplicate-watch fixture was not claimed';
    end if;

    v_duplicate := public.materialize_phase1_tracking_request(
        v_duplicate_claim.id,
        v_duplicate_claim.attempt_count,
        v_product_id,
        v_listing_id,
        v_duplicate_claim.normalized_url,
        v_variant_id,
        'size:uk-9'
    );

    v_duplicate_replay :=
        public.materialize_phase1_tracking_request(
            v_duplicate_claim.id,
            v_duplicate_claim.attempt_count,
            v_product_id,
            v_listing_id,
            v_duplicate_claim.normalized_url,
            v_variant_id,
            'size:uk-9'
        );

    select count(*)
    into v_watch_count
    from public.watch_intents watch
    join public.watch_listing_targets target
      on target.watch_id = watch.id
    where watch.user_id = v_user_id
      and target.listing_id = v_listing_id
      and watch.canonical_variant_id = v_variant_id
      and watch.status <> 'archived';

    if v_duplicate ->> 'outcome' <> 'duplicate_watch'
       or v_duplicate_replay ->> 'outcome' <> 'duplicate_watch'
       or (v_duplicate ->> 'watch_id')::uuid <> v_watch_id
       or (v_duplicate_replay ->> 'watch_id')::uuid <> v_watch_id
       or v_watch_count <> 1
       or not exists (
            select 1
            from public.tracking_requests request
            where request.id = v_duplicate_claim.id
              and request.status = 'failed'
              and request.error_code = 'duplicate_watch'
          ) then
        raise exception
            'Lost-response duplicate-watch replay was not stable';
    end if;
end;
$$;


-- ============================================================
-- CATALOG COMMIT BEFORE MATERIALIZATION -> RECLAIM / REPROCESS
--
-- The first attempt's event commits, its request lease is then expired, and a
-- newer attempt persists a later event. Replaying the old catalog event after
-- reclaim must not regress latest state. The old generation cannot
-- materialize; the new generation can.
-- ============================================================

do $$
declare
    v_user_id uuid;
    v_attempt_one public.tracking_requests%rowtype;
    v_attempt_two public.tracking_requests%rowtype;
    v_old_bootstrap jsonb;
    v_old_bootstrap_replay jsonb;
    v_new_bootstrap jsonb;
    v_old_product jsonb;
    v_new_product jsonb;
    v_product_id uuid;
    v_listing_id uuid;
    v_variant_id uuid;
    v_materialized jsonb;
    v_watch_count integer;
begin
    select profile.id
    into strict v_user_id
    from public.profiles profile
    order by profile.id
    limit 1;

    insert into public.tracking_requests (
        id,
        user_id,
        requested_url,
        normalized_url,
        variant_requirements,
        target_price,
        target_currency,
        conditions
    )
    values (
        '02100000-0000-4000-8000-000000000012'::uuid,
        v_user_id,
        'https://www.nike.in/lease-harness-reclaim/p/02100012',
        'https://www.nike.in/lease-harness-reclaim/p/02100012',
        '{"size":"UK 10"}'::jsonb,
        13000,
        'INR',
        '{"require_in_stock":true}'::jsonb
    );

    select claimed.*
    into strict v_attempt_one
    from public.claim_tracking_requests(1, 300) claimed;

    -- now() is transaction-stable in this rollback harness. Move the logical
    -- first-attempt timestamp backward to model two real RPC transactions.
    update public.tracking_requests
    set started_at = pg_catalog.now() - interval '2 minutes'
    where id = v_attempt_one.id
    returning *
    into v_attempt_one;

    v_old_product := pg_catalog.jsonb_build_object(
        'name', 'Migration 021 Reclaim Harness',
        'image_url', 'https://static.example.test/02100012.png',
        'external_id', '02100012',
        'mrp', 15000,
        'current_price', 14000,
        'currency', 'INR',
        'in_stock', true,
        'variants', pg_catalog.jsonb_build_array(
            pg_catalog.jsonb_build_object(
                'variant_key', 'size:uk-10',
                'canonical_title', 'UK 10',
                'canonical_attributes', '{"size":"UK 10"}'::jsonb,
                'external_sku', '02100012-UK10',
                'listing_title', 'UK 10',
                'listing_attributes', '{"size":"UK 10"}'::jsonb,
                'mrp', 15000,
                'current_price', 14000,
                'in_stock', true,
                'stock_remaining', 1
            )
        )
    );

    v_old_bootstrap := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_attempt_one.normalized_url,
        '02110000-0000-4000-8000-000000000012'::uuid,
        v_attempt_one.started_at,
        v_old_product
    );

    update public.tracking_requests
    set lease_expires_at = pg_catalog.now() - interval '1 second'
    where id = v_attempt_one.id;

    select claimed.*
    into strict v_attempt_two
    from public.claim_tracking_requests(1, 300) claimed;

    if v_attempt_two.id <> v_attempt_one.id
       or v_attempt_two.attempt_count <> 2
       or v_attempt_two.started_at <= v_attempt_one.started_at then
        raise exception
            'Catalog-committed request was not reclaimed as a later generation';
    end if;

    v_new_product := pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
            v_old_product,
            '{current_price}',
            '13500'::jsonb
        ),
        '{variants,0,current_price}',
        '13500'::jsonb
    );

    v_new_bootstrap := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_attempt_two.normalized_url,
        '02120000-0000-4000-8000-000000000012'::uuid,
        v_attempt_two.started_at,
        v_new_product
    );

    if v_new_bootstrap ->> 'product_id' <>
       v_old_bootstrap ->> 'product_id'
       or v_new_bootstrap ->> 'listing_id' <>
          v_old_bootstrap ->> 'listing_id' then
        raise exception
            'Reclaimed bootstrap did not converge on catalog identity';
    end if;

    -- Model attempt N resuming its exact bootstrap call after N+1 persisted.
    v_old_bootstrap_replay := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_attempt_one.normalized_url,
        '02110000-0000-4000-8000-000000000012'::uuid,
        v_attempt_one.started_at,
        v_old_product
    );

    v_product_id := (v_new_bootstrap ->> 'product_id')::uuid;
    v_listing_id := (v_new_bootstrap ->> 'listing_id')::uuid;
    v_variant_id := (
        v_new_bootstrap #>> '{variants,0,canonical_variant_id}'
    )::uuid;

    if (v_old_bootstrap_replay ->> 'observation_created')::boolean
       or not exists (
            select 1
            from public.merchant_listings listing
            where listing.id = v_listing_id
              and listing.current_price = 13500
              and listing.last_checked_at = v_attempt_two.started_at
          )
       or (
            select count(*)
            from public.listing_observations observation
            where observation.listing_id = v_listing_id
              and observation.crawl_event_id in (
                  '02110000-0000-4000-8000-000000000012'::uuid,
                  '02120000-0000-4000-8000-000000000012'::uuid
              )
          ) <> 2 then
        raise exception
            'Old catalog retry regressed or duplicated latest catalog state';
    end if;

    begin
        perform public.materialize_phase1_tracking_request(
            v_attempt_one.id,
            v_attempt_one.attempt_count,
            v_product_id,
            v_listing_id,
            v_attempt_one.normalized_url,
            v_variant_id,
            'size:uk-10'
        );

        raise exception
            'Old catalog generation unexpectedly materialized a watch';
    exception
        when others then
            if sqlerrm not like '%attempt is stale%' then
                raise;
            end if;
    end;

    select count(*)
    into v_watch_count
    from public.watch_listing_targets target
    where target.listing_id = v_listing_id;

    if v_watch_count <> 0 then
        raise exception
            'Stale materialization left a watch side effect';
    end if;

    v_materialized := public.materialize_phase1_tracking_request(
        v_attempt_two.id,
        v_attempt_two.attempt_count,
        v_product_id,
        v_listing_id,
        v_attempt_two.normalized_url,
        v_variant_id,
        'size:uk-10'
    );

    if v_materialized ->> 'outcome' <> 'completed'
       or not exists (
            select 1
            from public.tracking_requests request
            where request.id = v_attempt_two.id
              and request.status = 'completed'
              and request.attempt_count = 2
              and request.result_product_id = v_product_id
              and request.result_listing_id = v_listing_id
              and request.result_watch_id =
                  (v_materialized ->> 'watch_id')::uuid
          ) then
        raise exception
            'Current reclaimed generation did not materialize atomically';
    end if;
end;
$$;


-- ============================================================
-- FIRST STALE CATALOG WRITE AFTER RECLAIM
--
-- Attempt N is reclaimed before it ever calls migration 019. N+1 writes a
-- newer catalog event first. Attempt N then makes its first bootstrap call
-- with its original event id and older checked_at. The old immutable event
-- must be recorded without regressing either listing latest-state cache, and
-- only N+1 may materialize the watch.
-- ============================================================

do $$
declare
    v_user_id uuid;
    v_attempt_one public.tracking_requests%rowtype;
    v_attempt_two public.tracking_requests%rowtype;
    v_old_bootstrap jsonb;
    v_new_bootstrap jsonb;
    v_old_product jsonb;
    v_new_product jsonb;
    v_product_id uuid;
    v_listing_id uuid;
    v_variant_id uuid;
    v_listing_variant_id uuid;
    v_materialized jsonb;
    v_watch_count integer;
begin
    select profile.id
    into strict v_user_id
    from public.profiles profile
    order by profile.id
    limit 1;

    insert into public.tracking_requests (
        id,
        user_id,
        requested_url,
        normalized_url,
        variant_requirements,
        target_price,
        target_currency,
        conditions
    )
    values (
        '02100000-0000-4000-8000-000000000016'::uuid,
        v_user_id,
        'https://www.nike.in/lease-harness-late-stale/p/02100016',
        'https://www.nike.in/lease-harness-late-stale/p/02100016',
        '{"size":"UK 11"}'::jsonb,
        12500,
        'INR',
        '{"require_in_stock":true}'::jsonb
    );

    select claimed.*
    into strict v_attempt_one
    from public.claim_tracking_requests(1, 300) claimed;

    if v_attempt_one.id <>
       '02100000-0000-4000-8000-000000000016'::uuid
       or v_attempt_one.attempt_count <> 1 then
        raise exception
            'Late-stale fixture was not claimed as attempt 1';
    end if;

    -- now() is transaction-stable in this rollback harness. Move attempt N's
    -- logical timestamp backward before reclaiming it so N+1 is strictly newer.
    update public.tracking_requests
    set
        started_at = pg_catalog.now() - interval '2 minutes',
        lease_expires_at = pg_catalog.now() - interval '1 second'
    where id = v_attempt_one.id
    returning *
    into v_attempt_one;

    select claimed.*
    into strict v_attempt_two
    from public.claim_tracking_requests(1, 300) claimed;

    if v_attempt_two.id <> v_attempt_one.id
       or v_attempt_two.attempt_count <> 2
       or v_attempt_two.started_at <= v_attempt_one.started_at then
        raise exception
            'Late-stale fixture was not reclaimed as newer attempt 2';
    end if;

    v_new_product := pg_catalog.jsonb_build_object(
        'name', 'Migration 021 Late Stale Bootstrap Harness',
        'image_url', 'https://static.example.test/02100016.png',
        'external_id', '02100016',
        'mrp', 15000,
        'current_price', 13200,
        'currency', 'INR',
        'in_stock', true,
        'variants', pg_catalog.jsonb_build_array(
            pg_catalog.jsonb_build_object(
                'variant_key', 'size:uk-11',
                'canonical_title', 'UK 11',
                'canonical_attributes', '{"size":"UK 11"}'::jsonb,
                'external_sku', '02100016-UK11',
                'listing_title', 'UK 11',
                'listing_attributes', '{"size":"UK 11"}'::jsonb,
                'mrp', 15000,
                'current_price', 13200,
                'in_stock', true,
                'stock_remaining', 4
            )
        )
    );

    v_old_product := pg_catalog.jsonb_build_object(
        'name', 'Migration 021 Late Stale Bootstrap Harness',
        'image_url', 'https://static.example.test/02100016.png',
        'external_id', '02100016',
        'mrp', 15000,
        'current_price', 14500,
        'currency', 'INR',
        'in_stock', false,
        'variants', pg_catalog.jsonb_build_array(
            pg_catalog.jsonb_build_object(
                'variant_key', 'size:uk-11',
                'canonical_title', 'UK 11',
                'canonical_attributes', '{"size":"UK 11"}'::jsonb,
                'external_sku', '02100016-UK11',
                'listing_title', 'UK 11',
                'listing_attributes', '{"size":"UK 11"}'::jsonb,
                'mrp', 15000,
                'current_price', 14500,
                'in_stock', false,
                'stock_remaining', 0
            )
        )
    );

    -- N+1 is deliberately the first catalog writer.
    v_new_bootstrap := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_attempt_two.normalized_url,
        '02120000-0000-4000-8000-000000000016'::uuid,
        v_attempt_two.started_at,
        v_new_product
    );

    -- N now makes its first (not replayed) migration-019 call after reclaim.
    v_old_bootstrap := public.bootstrap_phase1_catalog(
        'nike-india',
        'nike',
        'nike',
        v_attempt_one.normalized_url,
        '02110000-0000-4000-8000-000000000016'::uuid,
        v_attempt_one.started_at,
        v_old_product
    );

    if (v_old_bootstrap ->> 'product_id')
       is distinct from (v_new_bootstrap ->> 'product_id')
       or (v_old_bootstrap ->> 'listing_id')
          is distinct from (v_new_bootstrap ->> 'listing_id')
       or not coalesce(
            (v_old_bootstrap ->> 'observation_created')::boolean,
            false
          ) then
        raise exception
            'First stale bootstrap did not converge and create history';
    end if;

    v_product_id := (v_new_bootstrap ->> 'product_id')::uuid;
    v_listing_id := (v_new_bootstrap ->> 'listing_id')::uuid;
    v_variant_id := (
        v_new_bootstrap #>> '{variants,0,canonical_variant_id}'
    )::uuid;
    v_listing_variant_id := (
        v_new_bootstrap #>> '{variants,0,listing_variant_id}'
    )::uuid;

    if (
        select count(*)
        from public.listing_observations observation
        where observation.listing_id = v_listing_id
          and observation.crawl_event_id in (
              '02110000-0000-4000-8000-000000000016'::uuid,
              '02120000-0000-4000-8000-000000000016'::uuid
          )
    ) <> 2 then
        raise exception
            'Late stale listing write did not preserve exactly two events';
    end if;

    if (
        select count(*)
        from public.listing_variant_observations observation
        where observation.listing_variant_id = v_listing_variant_id
          and observation.crawl_event_id in (
              '02110000-0000-4000-8000-000000000016'::uuid,
              '02120000-0000-4000-8000-000000000016'::uuid
          )
    ) <> 2 then
        raise exception
            'Late stale variant write did not preserve exactly two events';
    end if;

    if not exists (
        select 1
        from public.listing_observations observation
        where observation.listing_id = v_listing_id
          and observation.crawl_event_id =
              '02110000-0000-4000-8000-000000000016'::uuid
          and observation.checked_at = v_attempt_one.started_at
          and observation.selling_price = 14500
          and observation.in_stock = false
    ) then
        raise exception
            'First stale listing event was not stored as immutable history';
    end if;

    if not exists (
        select 1
        from public.listing_variant_observations observation
        where observation.listing_variant_id = v_listing_variant_id
          and observation.crawl_event_id =
              '02110000-0000-4000-8000-000000000016'::uuid
          and observation.checked_at = v_attempt_one.started_at
          and observation.selling_price = 14500
          and observation.in_stock = false
          and observation.stock_remaining = 0
    ) then
        raise exception
            'First stale variant event was not stored as immutable history';
    end if;

    if not exists (
        select 1
        from public.merchant_listings listing
        where listing.id = v_listing_id
          and listing.current_price = 13200
          and listing.in_stock = true
          and listing.last_checked_at = v_attempt_two.started_at
    ) then
        raise exception
            'First stale bootstrap regressed newer listing state';
    end if;

    if not exists (
        select 1
        from public.listing_variants variant
        where variant.id = v_listing_variant_id
          and variant.listing_id = v_listing_id
          and variant.variant_key = 'size:uk-11'
          and variant.current_price = 13200
          and variant.in_stock = true
          and variant.stock_remaining = 4
          and variant.last_checked_at = v_attempt_two.started_at
    ) then
        raise exception
            'First stale bootstrap regressed newer variant state';
    end if;

    begin
        perform public.materialize_phase1_tracking_request(
            v_attempt_one.id,
            v_attempt_one.attempt_count,
            v_product_id,
            v_listing_id,
            v_attempt_one.normalized_url,
            v_variant_id,
            'size:uk-11'
        );

        raise exception
            'Late stale catalog generation unexpectedly materialized a watch';
    exception
        when others then
            if sqlerrm not like '%attempt is stale%' then
                raise;
            end if;
    end;

    select count(*)
    into v_watch_count
    from public.watch_listing_targets target
    where target.listing_id = v_listing_id;

    if v_watch_count <> 0 then
        raise exception
            'Late stale materialization left a watch side effect';
    end if;

    v_materialized := public.materialize_phase1_tracking_request(
        v_attempt_two.id,
        v_attempt_two.attempt_count,
        v_product_id,
        v_listing_id,
        v_attempt_two.normalized_url,
        v_variant_id,
        'size:uk-11'
    );

    select count(*)
    into v_watch_count
    from public.watch_listing_targets target
    where target.listing_id = v_listing_id;

    if v_materialized ->> 'outcome' <> 'completed'
       or v_watch_count <> 1
       or not exists (
            select 1
            from public.tracking_requests request
            where request.id = v_attempt_two.id
              and request.status = 'completed'
              and request.attempt_count = 2
              and request.result_product_id = v_product_id
              and request.result_listing_id = v_listing_id
              and request.result_watch_id =
                  (v_materialized ->> 'watch_id')::uuid
          ) then
        raise exception
            'Current generation did not materialize after first stale write';
    end if;
end;
$$;


-- ============================================================
-- SINGLE-SESSION CLAIM SERIALIZATION CHECK
--
-- A second claimer cannot receive the unexpired generation just issued by the
-- first call. True simultaneous SKIP LOCKED behavior requires two independent
-- database sessions. A fixture created inside this rollback-only transaction
-- is intentionally invisible to another session, so the harness does not
-- pretend this sequential check is a two-session proof. Perform the documented
-- two-session check separately only on a disposable database after review.
-- ============================================================

insert into public.tracking_requests (
    id,
    user_id,
    requested_url,
    normalized_url
)
select
    '02100000-0000-4000-8000-000000000013'::uuid,
    profile.id,
    'https://www.nike.in/lease-harness-serialization/p/02100013',
    'https://www.nike.in/lease-harness-serialization/p/02100013'
from public.profiles profile
order by profile.id
limit 1;


do $$
declare
    v_first public.tracking_requests%rowtype;
    v_second_count integer;
begin
    select claimed.*
    into strict v_first
    from public.claim_tracking_requests(1, 300) claimed;

    if v_first.id <>
       '02100000-0000-4000-8000-000000000013'::uuid
       or v_first.attempt_count <> 1 then
        raise exception
            'First serialization claim returned the wrong generation';
    end if;

    select count(*)
    into v_second_count
    from public.claim_tracking_requests(1, 300);

    if v_second_count <> 0 then
        raise exception
            'Second claimer received an already-owned generation';
    end if;
end;
$$;


-- Expected psql result: every block succeeds, then all work is rolled back.
rollback;


-- Two-session limitation and manual follow-up:
--
-- A strict concurrent SKIP LOCKED proof needs a committed disposable fixture
-- visible to both sessions. In a disposable database, Session A should BEGIN,
-- call claim_tracking_requests(...) and keep the transaction open; Session B
-- should call the same RPC and immediately receive a different eligible row or
-- zero rows rather than block or receive the same request. Roll back both
-- sessions and remove the committed fixture. This is deliberately not embedded
-- here because a shared committed fixture would violate this harness's
-- rollback-only guarantee.
