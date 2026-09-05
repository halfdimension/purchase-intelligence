-- Phase 1 new-product ingestion, Milestone E.
--
-- Atomically materialize a claimed tracking request into a real
-- watch_intent + watch_listing_target and mark the request complete.
--
-- Variant normalization and selection happen in trusted Python.
-- This function only verifies generic catalog identities and domain
-- relationships. It contains no merchant- or category-specific logic.


create or replace function public.materialize_phase1_tracking_request(
    p_tracking_request_id uuid,
    p_attempt_count integer,
    p_product_id uuid,
    p_listing_id uuid,
    p_normalized_url text,
    p_canonical_variant_id uuid,
    p_variant_key text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_request public.tracking_requests%rowtype;

    v_listing_product_id uuid;
    v_listing_url text;
    v_listing_currency text;
    v_listing_active boolean;
    v_merchant_active boolean;
    v_product_active boolean;

    v_watch_id uuid;
    v_existing_watch_id uuid;
    v_completed_watch_variant_id uuid;

    v_has_variant_requirements boolean;
    v_duplicate_replay boolean := false;
begin
    -- ========================================================
    -- Required trusted-worker inputs
    -- ========================================================

    if p_tracking_request_id is null then
        raise exception
            'tracking_request_id is required';
    end if;

    if p_attempt_count is null
       or p_attempt_count < 1 then
        raise exception
            'attempt_count must be a positive integer';
    end if;

    if p_product_id is null then
        raise exception
            'product_id is required';
    end if;

    if p_listing_id is null then
        raise exception
            'listing_id is required';
    end if;

    if p_normalized_url is null
       or pg_catalog.btrim(p_normalized_url) = '' then
        raise exception
            'normalized_url is required';
    end if;

    if (
        p_canonical_variant_id is null
    ) <> (
        p_variant_key is null
        or pg_catalog.btrim(p_variant_key) = ''
    ) then
        raise exception
            'canonical_variant_id and variant_key must both be supplied or both be null';
    end if;


    -- ========================================================
    -- Claim ownership and stale-attempt guard
    --
    -- The row lock keeps result/status mutation serialized.
    -- A completed call may be replayed after an ambiguous client
    -- response, but a different attempt may not overwrite it.
    -- ========================================================

    select request.*
    into v_request
    from public.tracking_requests request
    where request.id = p_tracking_request_id
    for update;

    if not found then
        raise exception
            'Tracking request not found: %',
            p_tracking_request_id;
    end if;

    if v_request.attempt_count <> p_attempt_count then
        raise exception
            'Tracking request attempt is stale: request=%, expected=%, received=%',
            p_tracking_request_id,
            v_request.attempt_count,
            p_attempt_count;
    end if;

    if v_request.status = 'completed' then
        if v_request.result_product_id
                is distinct from p_product_id
           or v_request.result_listing_id
                is distinct from p_listing_id
           or v_request.result_watch_id is null then
            raise exception
                'Completed tracking request was retried with different result identities: %',
                p_tracking_request_id;
        end if;

        select watch.canonical_variant_id
        into v_completed_watch_variant_id
        from public.watch_intents watch
        join public.watch_listing_targets target
          on target.watch_id = watch.id
         and target.listing_id = p_listing_id
        join public.merchant_listings listing
          on listing.id = target.listing_id
         and listing.product_id = p_product_id
         and listing.url = pg_catalog.btrim(
                p_normalized_url
             )
        where watch.id = v_request.result_watch_id
          and watch.user_id = v_request.user_id
          and watch.product_id = p_product_id
          and watch.tracking_scope = 'specific_listing'
          and (
              p_canonical_variant_id is null
              or exists (
                  select 1
                  from public.listing_variants listing_variant
                  where listing_variant.listing_id = listing.id
                    and listing_variant.canonical_variant_id =
                        p_canonical_variant_id
                    and listing_variant.variant_key =
                        pg_catalog.btrim(p_variant_key)
              )
          );

        if not found
           or v_completed_watch_variant_id
                is distinct from p_canonical_variant_id then
            raise exception
                'Completed tracking request result no longer matches its watch: %',
                p_tracking_request_id;
        end if;

        return pg_catalog.jsonb_build_object(
            'outcome',
            'completed',
            'tracking_request_id',
            p_tracking_request_id,
            'product_id',
            p_product_id,
            'listing_id',
            p_listing_id,
            'watch_id',
            v_request.result_watch_id,
            'already_completed',
            true
        );
    end if;

    if v_request.status = 'failed'
       and v_request.error_code = 'duplicate_watch' then
        v_duplicate_replay := true;
    elsif v_request.status <> 'processing' then
        raise exception
            'Tracking request is not owned by this processing attempt: request=%, status=%',
            p_tracking_request_id,
            v_request.status;
    end if;


    -- ========================================================
    -- Request payload integrity
    -- ========================================================

    if pg_catalog.jsonb_typeof(
        v_request.variant_requirements
    ) <> 'object' then
        raise exception
            'Tracking request variant_requirements must be a JSON object';
    end if;

    if pg_catalog.jsonb_typeof(
        v_request.conditions
    ) <> 'object' then
        raise exception
            'Tracking request conditions must be a JSON object';
    end if;

    v_has_variant_requirements :=
        v_request.variant_requirements
        <> '{}'::jsonb;

    if v_has_variant_requirements
       <> (p_canonical_variant_id is not null) then
        raise exception
            'Resolved canonical variant does not match tracking request requirements';
    end if;


    -- ========================================================
    -- Catalog and URL relationship checks
    -- ========================================================

    select
        listing.product_id,
        listing.url,
        listing.currency,
        listing.active,
        merchant.active,
        product.status = 'active'
    into
        v_listing_product_id,
        v_listing_url,
        v_listing_currency,
        v_listing_active,
        v_merchant_active,
        v_product_active
    from public.merchant_listings listing
    join public.merchants merchant
      on merchant.id = listing.merchant_id
    join public.canonical_products product
      on product.id = listing.product_id
    where listing.id = p_listing_id;

    if not found then
        raise exception
            'Resolved merchant listing does not exist: %',
            p_listing_id;
    end if;

    if v_listing_product_id <> p_product_id then
        raise exception
            'Resolved merchant listing belongs to a different canonical product';
    end if;

    if v_listing_url is distinct from
       pg_catalog.btrim(p_normalized_url) then
        raise exception
            'Resolved merchant listing URL does not match authoritative target';
    end if;

    if not v_listing_active
       or not v_merchant_active
       or not v_product_active then
        raise exception
            'Resolved product, merchant, and listing must be active';
    end if;

    if pg_catalog.upper(
        pg_catalog.btrim(v_listing_currency)
    ) <> pg_catalog.upper(
        pg_catalog.btrim(v_request.target_currency)
    ) then
        raise exception
            'Tracking request currency does not match merchant listing currency';
    end if;


    -- ========================================================
    -- Generic resolved-variant checks
    --
    -- SQL deliberately does not infer variant_key from size or
    -- any other category-specific requirement.
    -- ========================================================

    if p_canonical_variant_id is not null then
        if not exists (
            select 1
            from public.canonical_variants variant
            join public.listing_variants listing_variant
              on listing_variant.canonical_variant_id = variant.id
             and listing_variant.listing_id = p_listing_id
             and listing_variant.variant_key = pg_catalog.btrim(
                    p_variant_key
                 )
             and listing_variant.active = true
            where variant.id = p_canonical_variant_id
              and variant.product_id = p_product_id
              and variant.variant_key = pg_catalog.btrim(
                    p_variant_key
                  )
        ) then
            raise exception
                'Resolved variant does not belong to the product and listing';
        end if;
    end if;


    -- ========================================================
    -- Duplicate-watch serialization
    --
    -- Advisory identity is user + listing + canonical variant.
    -- It serializes trusted worker materializations for the same
    -- logical specific-listing watch without adding retailer data
    -- to the schema.
    -- ========================================================

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            v_request.user_id::text
            || ':'
            || p_listing_id::text
            || ':'
            || coalesce(
                p_canonical_variant_id::text,
                'no-variant'
            ),
            0
        )
    );

    select watch.id
    into v_existing_watch_id
    from public.watch_intents watch
    join public.watch_listing_targets target
      on target.watch_id = watch.id
     and target.listing_id = p_listing_id
    where watch.user_id = v_request.user_id
      and watch.product_id = p_product_id
      and watch.tracking_scope = 'specific_listing'
      and watch.status <> 'archived'
      and watch.canonical_variant_id
            is not distinct from
            p_canonical_variant_id
    order by watch.created_at asc, watch.id asc
    limit 1;

    if v_existing_watch_id is not null then
        if not v_duplicate_replay then
            update public.tracking_requests
            set
                status = 'failed',
                error_code = 'duplicate_watch',
                error_message = 'This product and variant are already being tracked.',
                completed_at = pg_catalog.now()
            where id = p_tracking_request_id
              and status = 'processing'
              and attempt_count = p_attempt_count;

            if not found then
                raise exception
                    'Tracking request duplicate failure lost its processing ownership';
            end if;
        end if;

        return pg_catalog.jsonb_build_object(
            'outcome',
            'duplicate_watch',
            'tracking_request_id',
            p_tracking_request_id,
            'product_id',
            p_product_id,
            'listing_id',
            p_listing_id,
            'watch_id',
            v_existing_watch_id,
            'already_completed',
            false
        );
    end if;

    if v_duplicate_replay then
        raise exception
            'Duplicate-watch tracking request no longer has a matching watch';
    end if;


    -- ========================================================
    -- Atomic watch materialization and request completion
    -- ========================================================

    insert into public.watch_intents (
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
    values (
        v_request.user_id,
        p_product_id,
        p_canonical_variant_id,
        'specific_listing',
        v_request.target_price,
        pg_catalog.upper(
            pg_catalog.btrim(
                v_request.target_currency
            )
        ),
        v_request.variant_requirements,
        v_request.conditions,
        'active'
    )
    returning id
    into v_watch_id;

    insert into public.watch_listing_targets (
        watch_id,
        listing_id
    )
    values (
        v_watch_id,
        p_listing_id
    );

    update public.tracking_requests
    set
        status = 'completed',
        result_product_id = p_product_id,
        result_listing_id = p_listing_id,
        result_watch_id = v_watch_id,
        error_code = null,
        error_message = null,
        completed_at = pg_catalog.now()
    where id = p_tracking_request_id
      and status = 'processing'
      and attempt_count = p_attempt_count;

    if not found then
        raise exception
            'Tracking request completion lost its processing ownership';
    end if;

    return pg_catalog.jsonb_build_object(
        'outcome',
        'completed',
        'tracking_request_id',
        p_tracking_request_id,
        'product_id',
        p_product_id,
        'listing_id',
        p_listing_id,
        'watch_id',
        v_watch_id,
        'already_completed',
        false
    );
end;
$$;


revoke all
on function public.materialize_phase1_tracking_request(
    uuid,
    integer,
    uuid,
    uuid,
    text,
    uuid,
    text
)
from public, anon, authenticated;


grant execute
on function public.materialize_phase1_tracking_request(
    uuid,
    integer,
    uuid,
    uuid,
    text,
    uuid,
    text
)
to service_role;
