-- Phase 1 new-product ingestion, Milestone D.
--
-- Transactional catalog bootstrap for one normalized crawl result.
--
-- Called only by the trusted service-role worker.
--
-- Merchant-specific parsing and variant normalization MUST happen
-- before this RPC. PostgreSQL receives normalized catalog data.
--
-- This migration is being built incrementally.
-- Do not apply to production until the complete function has passed
-- rollback-only integration tests.


create or replace function public.bootstrap_phase1_catalog(
    p_merchant_slug text,
    p_adapter_key text,
    p_brand_slug text,
    p_normalized_url text,
    p_crawl_event_id uuid,
    p_checked_at timestamptz,
    p_product jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_merchant_id uuid;
    v_brand_id uuid;

    v_candidate_product_id uuid;
    v_product_id uuid;

    v_listing_id uuid;
    v_listing_merchant_id uuid;
    v_listing_external_id text;
    v_incoming_external_id text;

    v_existing_brand_id uuid;

    v_listing_created boolean := false;

    v_variant jsonb;
    v_variant_key text;

    v_canonical_variant_id uuid;

    v_listing_variant_id uuid;
    v_listing_variant_canonical_id uuid;
    v_listing_variant_external_sku text;
    v_incoming_external_sku text;

    v_variant_results jsonb := '[]'::jsonb;

    v_listing_observation_id bigint;
    v_existing_observation_listing_id uuid;
    v_existing_observation_checked_at timestamptz;
    v_existing_observation_mrp numeric;
    v_existing_observation_price numeric;
    v_existing_observation_currency text;
    v_existing_observation_in_stock boolean;
    v_observation_created boolean := false;

    v_variant_observation_id bigint;
    v_existing_variant_observation_checked_at timestamptz;
    v_existing_variant_observation_mrp numeric;
    v_existing_variant_observation_price numeric;
    v_existing_variant_observation_currency text;
    v_existing_variant_observation_in_stock boolean;
    v_existing_variant_observation_stock_remaining integer;

    v_existing_event_variant_count bigint;
    v_incoming_variant_count bigint;
begin
    -- ========================================================
    -- Required RPC inputs
    -- ========================================================

    if p_merchant_slug is null
       or btrim(p_merchant_slug) = '' then
        raise exception
            'merchant_slug is required';
    end if;

    if p_adapter_key is null
       or btrim(p_adapter_key) = '' then
        raise exception
            'adapter_key is required';
    end if;

    if p_brand_slug is null
       or btrim(p_brand_slug) = '' then
        raise exception
            'brand_slug is required';
    end if;

    if p_normalized_url is null
       or btrim(p_normalized_url) = '' then
        raise exception
            'normalized_url is required';
    end if;

    if p_crawl_event_id is null then
        raise exception
            'crawl_event_id is required';
    end if;

    if p_checked_at is null then
        raise exception
            'checked_at is required';
    end if;

    if p_product is null
       or jsonb_typeof(p_product) <> 'object' then
        raise exception
            'product must be a JSON object';
    end if;

    if nullif(
        btrim(p_product ->> 'name'),
        ''
    ) is null then
        raise exception
            'product.name is required';
    end if;


    -- ========================================================
    -- Trusted merchant resolution
    --
    -- Both slug and adapter_key must agree with the active
    -- merchant row. The worker cannot accidentally claim one
    -- merchant while using another adapter.
    -- ========================================================

    select merchant.id
    into v_merchant_id
    from public.merchants merchant
    where merchant.slug = btrim(
        p_merchant_slug
    )
      and merchant.adapter_key = btrim(
        p_adapter_key
    )
      and merchant.active = true;

    if v_merchant_id is null then
        raise exception
            'Active merchant/adaptor pair not found: merchant=%, adapter=%',
            p_merchant_slug,
            p_adapter_key;
    end if;


    -- ========================================================
    -- Brand resolution
    --
    -- Brand identity is supplied by trusted Python normalization.
    -- SQL does not infer brand from merchant or product title.
    -- ========================================================

    select brand.id
    into v_brand_id
    from public.brands brand
    where brand.slug = btrim(
        p_brand_slug
    );

    if v_brand_id is null then
        raise exception
            'Brand not found: %',
            p_brand_slug;
    end if;


    -- ========================================================
    -- Existing merchant-listing fast path
    --
    -- The normalized merchant URL is the primary bootstrap
    -- identity for the current ingestion architecture.
    -- ========================================================

    select
        listing.id,
        listing.product_id,
        listing.merchant_id,
        listing.external_id
    into
        v_listing_id,
        v_product_id,
        v_listing_merchant_id,
        v_listing_external_id
    from public.merchant_listings listing
    where listing.url = btrim(
        p_normalized_url
    );


    -- ========================================================
    -- New catalog identity
    --
    -- If the URL does not yet exist, create a candidate
    -- canonical product inside this SAME transaction.
    --
    -- The unique merchant_listings.url constraint then decides
    -- which concurrent worker wins first creation.
    -- ========================================================

    if v_listing_id is null then
        insert into public.canonical_products (
            brand_id,
            category_id,
            name,
            model_name,
            model_number,
            description,
            image_url,
            identifiers,
            attributes,
            status
        )
        values (
            v_brand_id,
            null,
            btrim(
                p_product ->> 'name'
            ),
            null,
            null,
            null,
            nullif(
                btrim(
                    p_product ->> 'image_url'
                ),
                ''
            ),
            '{}'::jsonb,
            '{}'::jsonb,
            'active'
        )
        returning id
        into v_candidate_product_id;


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
            active
        )
        values (
            v_candidate_product_id,
            v_merchant_id,
            nullif(
                btrim(
                    p_product ->> 'external_id'
                ),
                ''
            ),
            btrim(
                p_normalized_url
            ),
            btrim(
                p_product ->> 'name'
            ),
            nullif(
                btrim(
                    p_product ->> 'image_url'
                ),
                ''
            ),
            null,
            (
                p_product ->> 'mrp'
            )::numeric,
            (
                p_product ->> 'current_price'
            )::numeric,
            coalesce(
                nullif(
                    upper(
                        btrim(
                            p_product ->> 'currency'
                        )
                    ),
                    ''
                ),
                'INR'
            ),
            (
                p_product ->> 'in_stock'
            )::boolean,
            p_checked_at,
            true
        )
        on conflict (url)
        do nothing
        returning
            id,
            product_id,
            merchant_id,
            external_id
        into
            v_listing_id,
            v_product_id,
            v_listing_merchant_id,
            v_listing_external_id;


        -- ====================================================
        -- Concurrent URL loser
        --
        -- Another transaction committed the same URL first.
        --
        -- Our candidate canonical product has no authoritative
        -- listing, so remove it inside this transaction and
        -- converge on the winner.
        --
        -- Because this cleanup is in the same transaction, the
        -- candidate can never become a committed orphan.
        -- ====================================================

        if v_listing_id is null then
            delete from public.canonical_products
            where id = v_candidate_product_id;


            select
                listing.id,
                listing.product_id,
                listing.merchant_id,
                listing.external_id
            into
                v_listing_id,
                v_product_id,
                v_listing_merchant_id,
                v_listing_external_id
            from public.merchant_listings listing
            where listing.url = btrim(
                p_normalized_url
            );


            if v_listing_id is null then
                raise exception
                    'Listing URL conflict resolved without a visible winner: %',
                    p_normalized_url;
            end if;
        else
            v_listing_created := true;
        end if;
    end if;


    -- ========================================================
    -- Normalize incoming merchant identity metadata
    -- ========================================================

    v_incoming_external_id := nullif(
        btrim(
            p_product ->> 'external_id'
        ),
        ''
    );


    -- ========================================================
    -- Resolved listing integrity checks
    -- ========================================================

    if v_listing_merchant_id <> v_merchant_id then
        raise exception
            'Listing URL belongs to a different merchant: %',
            p_normalized_url;
    end if;


    if (
        v_listing_external_id is not null
        and v_incoming_external_id is not null
        and v_listing_external_id
            <> v_incoming_external_id
    ) then
        raise exception
            'Listing external_id conflicts with existing catalog identity for URL %',
            p_normalized_url;
    end if;


    -- ========================================================
    -- Safe listing external_id enrichment
    --
    -- Identity metadata is independent of crawl recency.
    --
    -- If the existing row did not previously know its merchant
    -- external ID, enrich it now.
    --
    -- The existing unique (merchant_id, external_id) index
    -- remains authoritative. A conflicting external identity
    -- therefore raises instead of being silently reassigned.
    -- ========================================================

    if v_listing_external_id is null
       and v_incoming_external_id is not null then

        update public.merchant_listings
        set external_id = v_incoming_external_id
        where id = v_listing_id
          and external_id is null;


        select listing.external_id
        into v_listing_external_id
        from public.merchant_listings listing
        where listing.id = v_listing_id;


        if v_listing_external_id
            is distinct from
            v_incoming_external_id then
            raise exception
                'Could not safely enrich listing external_id for URL %',
                p_normalized_url;
        end if;
    end if;


    -- ========================================================
    -- Resolved canonical-product integrity
    --
    -- Existing products may have a NULL brand from older data,
    -- but an already-known non-NULL brand must not disagree
    -- with the trusted normalized brand supplied by the worker.
    -- ========================================================

    select product.brand_id
    into v_existing_brand_id
    from public.canonical_products product
    where product.id = v_product_id;


    if v_product_id is null
       or not found then
        raise exception
            'Resolved listing references no canonical product';
    end if;


    if v_existing_brand_id is not null
       and v_existing_brand_id <> v_brand_id then
        raise exception
            'Canonical product brand conflicts with trusted brand for URL %',
            p_normalized_url;
    end if;


    -- ========================================================
    -- Safe canonical-product brand enrichment
    --
    -- Older catalog rows may legitimately have unresolved
    -- brand_id.
    --
    -- Once the trusted worker supplies a resolved brand, fill
    -- the missing identity link. Existing non-NULL disagreement
    -- was rejected above.
    -- ========================================================

    if v_existing_brand_id is null then
        update public.canonical_products
        set brand_id = v_brand_id
        where id = v_product_id
          and brand_id is null;


        select product.brand_id
        into v_existing_brand_id
        from public.canonical_products product
        where product.id = v_product_id;


        if v_existing_brand_id
            is distinct from
            v_brand_id then
            raise exception
                'Could not safely enrich canonical product brand for URL %',
                p_normalized_url;
        end if;
    end if;


    -- ========================================================
    -- Normalized variant payload validation
    --
    -- Variant normalization belongs to trusted Python.
    -- PostgreSQL only consumes generic normalized identities.
    -- ========================================================

    if not (p_product ? 'variants')
       or jsonb_typeof(
            p_product -> 'variants'
       ) <> 'array' then
        raise exception
            'product.variants must be a JSON array';
    end if;


    -- ========================================================
    -- Duplicate normalized variant identity guard
    --
    -- Trusted Python already rejects duplicate variant_key
    -- values, but the database boundary independently enforces
    -- the same invariant.
    --
    -- This keeps the RPC safe if it is called by another
    -- trusted worker implementation in the future.
    -- ========================================================

    if exists (
        select 1
        from jsonb_array_elements(
            p_product -> 'variants'
        ) as item(value)
        where jsonb_typeof(item.value) = 'object'
          and nullif(
                btrim(
                    item.value ->> 'variant_key'
                ),
                ''
              ) is not null
        group by nullif(
            btrim(
                item.value ->> 'variant_key'
            ),
            ''
        )
        having count(*) > 1
    ) then
        raise exception
            'product.variants contains duplicate variant_key values';
    end if;


    -- ========================================================
    -- Canonical + listing variant identity resolution
    --
    -- Process variant keys deterministically to reduce lock-order
    -- differences when concurrent workers touch the same listing.
    -- ========================================================

    for v_variant in
        select item.value
        from jsonb_array_elements(
            p_product -> 'variants'
        ) as item(value)
        order by item.value ->> 'variant_key'
    loop
        if jsonb_typeof(v_variant) <> 'object' then
            raise exception
                'Each product variant must be a JSON object';
        end if;


        v_variant_key := nullif(
            btrim(
                v_variant ->> 'variant_key'
            ),
            ''
        );


        if v_variant_key is null then
            raise exception
                'variant_key is required';
        end if;


        if jsonb_typeof(
            coalesce(
                v_variant -> 'canonical_attributes',
                '{}'::jsonb
            )
        ) <> 'object' then
            raise exception
                'canonical_attributes must be a JSON object for variant %',
                v_variant_key;
        end if;


        if jsonb_typeof(
            coalesce(
                v_variant -> 'listing_attributes',
                '{}'::jsonb
            )
        ) <> 'object' then
            raise exception
                'listing_attributes must be a JSON object for variant %',
                v_variant_key;
        end if;


        -- ====================================================
        -- Canonical variant identity
        --
        -- Expected race:
        --     same product_id + same normalized variant_key
        --
        -- Other uniqueness problems are not swallowed.
        -- ====================================================

        v_canonical_variant_id := null;


        insert into public.canonical_variants (
            product_id,
            title,
            canonical_sku,
            attributes,
            variant_key,
            image_url
        )
        values (
            v_product_id,
            nullif(
                btrim(
                    v_variant
                    ->> 'canonical_title'
                ),
                ''
            ),
            null,
            coalesce(
                v_variant
                -> 'canonical_attributes',
                '{}'::jsonb
            ),
            v_variant_key,
            null
        )
        on conflict (
            product_id,
            variant_key
        )
        do nothing
        returning id
        into v_canonical_variant_id;


        if v_canonical_variant_id is null then
            select variant.id
            into v_canonical_variant_id
            from public.canonical_variants variant
            where variant.product_id = v_product_id
              and variant.variant_key = v_variant_key;


            if v_canonical_variant_id is null then
                raise exception
                    'Canonical variant conflict resolved without a visible winner: product=%, variant=%',
                    v_product_id,
                    v_variant_key;
            end if;
        end if;


        -- ====================================================
        -- Merchant listing variant identity
        --
        -- Expected race:
        --     same listing_id + same normalized variant_key
        --
        -- A conflicting external_sku under a DIFFERENT
        -- variant_key is intentionally not caught here.
        -- The existing unique index must raise that integrity
        -- error instead of silently merging identities.
        -- ====================================================

        v_listing_variant_id := null;
        v_listing_variant_canonical_id := null;
        v_listing_variant_external_sku := null;

        v_incoming_external_sku := nullif(
            btrim(
                v_variant ->> 'external_sku'
            ),
            ''
        );


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
        values (
            v_listing_id,
            v_canonical_variant_id,
            nullif(
                btrim(
                    v_variant ->> 'external_sku'
                ),
                ''
            ),
            nullif(
                btrim(
                    v_variant ->> 'listing_title'
                ),
                ''
            ),
            coalesce(
                v_variant -> 'listing_attributes',
                '{}'::jsonb
            ),
            v_variant_key,
            (
                v_variant ->> 'mrp'
            )::numeric,
            (
                v_variant ->> 'current_price'
            )::numeric,
            coalesce(
                nullif(
                    upper(
                        btrim(
                            p_product ->> 'currency'
                        )
                    ),
                    ''
                ),
                'INR'
            ),
            (
                v_variant ->> 'in_stock'
            )::boolean,
            (
                v_variant ->> 'stock_remaining'
            )::integer,
            p_checked_at,
            true
        )
        on conflict (
            listing_id,
            variant_key
        )
        do nothing
        returning
            id,
            canonical_variant_id,
            external_sku
        into
            v_listing_variant_id,
            v_listing_variant_canonical_id,
            v_listing_variant_external_sku;


        if v_listing_variant_id is null then
            select
                variant.id,
                variant.canonical_variant_id,
                variant.external_sku
            into
                v_listing_variant_id,
                v_listing_variant_canonical_id,
                v_listing_variant_external_sku
            from public.listing_variants variant
            where variant.listing_id = v_listing_id
              and variant.variant_key = v_variant_key;


            if v_listing_variant_id is null then
                raise exception
                    'Listing variant conflict resolved without a visible winner: listing=%, variant=%',
                    v_listing_id,
                    v_variant_key;
            end if;
        end if;


        -- ====================================================
        -- Existing variant integrity checks
        -- ====================================================

        if (
            v_listing_variant_canonical_id is not null
            and v_listing_variant_canonical_id
                <> v_canonical_variant_id
        ) then
            raise exception
                'Listing variant references conflicting canonical variant: listing=%, variant=%',
                v_listing_id,
                v_variant_key;
        end if;


        -- ====================================================
        -- Safe canonical-variant relationship enrichment
        --
        -- listing_variants.canonical_variant_id is nullable by
        -- design while merchant variant matching is unresolved.
        --
        -- At this point the normalized identity is known, so a
        -- previously NULL relationship can be established.
        -- ====================================================

        if v_listing_variant_canonical_id is null then
            update public.listing_variants
            set canonical_variant_id =
                v_canonical_variant_id
            where id = v_listing_variant_id
              and canonical_variant_id is null;


            select variant.canonical_variant_id
            into v_listing_variant_canonical_id
            from public.listing_variants variant
            where variant.id =
                v_listing_variant_id;


            if v_listing_variant_canonical_id
                is distinct from
                v_canonical_variant_id then
                raise exception
                    'Could not safely resolve listing variant canonical identity: listing=%, variant=%',
                    v_listing_id,
                    v_variant_key;
            end if;
        end if;


        if (
            v_listing_variant_external_sku is not null
            and v_incoming_external_sku is not null
            and v_listing_variant_external_sku
                <> v_incoming_external_sku
        ) then
            raise exception
                'Listing variant external_sku conflicts with existing identity: listing=%, variant=%',
                v_listing_id,
                v_variant_key;
        end if;


        -- ====================================================
        -- Safe listing-variant external_sku enrichment
        --
        -- As with listing external_id, merchant SKU identity is
        -- not latest-state price/stock data and therefore does
        -- not use the checked_at monotonic guard.
        --
        -- The partial unique external_sku index remains
        -- authoritative and will raise on a conflicting SKU.
        -- ====================================================

        if v_listing_variant_external_sku is null
           and v_incoming_external_sku is not null then

            update public.listing_variants
            set external_sku = v_incoming_external_sku
            where id = v_listing_variant_id
              and external_sku is null;


            select variant.external_sku
            into v_listing_variant_external_sku
            from public.listing_variants variant
            where variant.id = v_listing_variant_id;


            if v_listing_variant_external_sku
                is distinct from
                v_incoming_external_sku then
                raise exception
                    'Could not safely enrich listing variant external_sku: listing=%, variant=%',
                    v_listing_id,
                    v_variant_key;
            end if;
        end if;


        -- ====================================================
        -- Accumulate resolved identity for the final RPC result.
        -- Final JSON is returned later in D6.
        -- ====================================================

        v_variant_results := (
            v_variant_results
            ||
            jsonb_build_array(
                jsonb_build_object(
                    'variant_key',
                    v_variant_key,
                    'canonical_variant_id',
                    v_canonical_variant_id,
                    'listing_variant_id',
                    v_listing_variant_id
                )
            )
        );
    end loop;


    -- ========================================================
    -- Latest merchant-listing state
    --
    -- Historical observations are the time-series truth.
    --
    -- merchant_listings.current_* is only the latest-state
    -- cache, so an older crawl must never overwrite a newer
    -- crawl.
    --
    -- Strictly older last_checked_at is required. Equal
    -- timestamps are treated as the same logical observation
    -- time and do not mutate the cache again.
    -- ========================================================

    update public.merchant_listings
    set
        title = btrim(
            p_product ->> 'name'
        ),

        image_url = nullif(
            btrim(
                p_product ->> 'image_url'
            ),
            ''
        ),

        current_mrp = (
            p_product ->> 'mrp'
        )::numeric,

        current_price = (
            p_product ->> 'current_price'
        )::numeric,

        currency = coalesce(
            nullif(
                upper(
                    btrim(
                        p_product ->> 'currency'
                    )
                ),
                ''
            ),
            'INR'
        ),

        in_stock = (
            p_product ->> 'in_stock'
        )::boolean,

        last_checked_at = p_checked_at,

        active = true

    where id = v_listing_id
      and (
          last_checked_at is null
          or last_checked_at < p_checked_at
      );


    -- ========================================================
    -- Latest merchant-listing variant state
    --
    -- Apply the same monotonic-time rule to each resolved
    -- listing variant.
    --
    -- Variant identity has already been validated in D3.
    -- This section updates only mutable merchant state.
    -- ========================================================

    for v_variant in
        select item.value
        from jsonb_array_elements(
            p_product -> 'variants'
        ) as item(value)
        order by item.value ->> 'variant_key'
    loop
        v_variant_key := nullif(
            btrim(
                v_variant ->> 'variant_key'
            ),
            ''
        );


        if v_variant_key is null then
            raise exception
                'variant_key is required during latest-state update';
        end if;


        update public.listing_variants
        set
            title = nullif(
                btrim(
                    v_variant ->> 'listing_title'
                ),
                ''
            ),

            attributes = coalesce(
                v_variant -> 'listing_attributes',
                '{}'::jsonb
            ),

            current_mrp = (
                v_variant ->> 'mrp'
            )::numeric,

            current_price = (
                v_variant ->> 'current_price'
            )::numeric,

            currency = coalesce(
                nullif(
                    upper(
                        btrim(
                            p_product ->> 'currency'
                        )
                    ),
                    ''
                ),
                'INR'
            ),

            in_stock = (
                v_variant ->> 'in_stock'
            )::boolean,

            stock_remaining = (
                v_variant ->> 'stock_remaining'
            )::integer,

            last_checked_at = p_checked_at,

            active = true

        where listing_id = v_listing_id
          and variant_key = v_variant_key
          and (
              last_checked_at is null
              or last_checked_at < p_checked_at
          );


        if not exists (
            select 1
            from public.listing_variants variant
            where variant.listing_id = v_listing_id
              and variant.variant_key = v_variant_key
        ) then
            raise exception
                'Resolved listing variant disappeared during latest-state update: listing=%, variant=%',
                v_listing_id,
                v_variant_key;
        end if;
    end loop;


    -- ========================================================
    -- Listing historical observation
    --
    -- crawl_event_id is persistence identity, not event time.
    --
    -- Retrying the exact same crawl event must reuse the same
    -- historical fact rather than append a duplicate row.
    -- ========================================================

    v_listing_observation_id := null;
    v_existing_observation_listing_id := null;
    v_existing_observation_checked_at := null;
    v_observation_created := false;


    insert into public.listing_observations (
        listing_id,
        crawl_event_id,
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
    values (
        v_listing_id,
        p_crawl_event_id,
        p_checked_at,
        (
            p_product ->> 'mrp'
        )::numeric,
        (
            p_product ->> 'current_price'
        )::numeric,
        coalesce(
            nullif(
                upper(
                    btrim(
                        p_product ->> 'currency'
                    )
                ),
                ''
            ),
            'INR'
        ),
        (
            p_product ->> 'in_stock'
        )::boolean,
        null,
        null,
        null,
        jsonb_build_object(
            'source',
            'phase1_ingestion',
            'crawl_event_id',
            p_crawl_event_id::text
        )
    )
    on conflict (crawl_event_id)
    where crawl_event_id is not null
    do nothing
    returning id
    into v_listing_observation_id;


    if v_listing_observation_id is null then
        select
            observation.id,
            observation.listing_id,
            observation.checked_at,
            observation.mrp,
            observation.selling_price,
            observation.currency,
            observation.in_stock
        into
            v_listing_observation_id,
            v_existing_observation_listing_id,
            v_existing_observation_checked_at,
            v_existing_observation_mrp,
            v_existing_observation_price,
            v_existing_observation_currency,
            v_existing_observation_in_stock
        from public.listing_observations observation
        where observation.crawl_event_id
            = p_crawl_event_id;


        if v_listing_observation_id is null then
            raise exception
                'Listing observation conflict resolved without a visible winner: event=%',
                p_crawl_event_id;
        end if;


        if v_existing_observation_listing_id
            <> v_listing_id then
            raise exception
                'crawl_event_id is already assigned to a different listing: event=%',
                p_crawl_event_id;
        end if;


        if v_existing_observation_checked_at
            <> p_checked_at then
            raise exception
                'crawl_event_id was retried with a different checked_at: event=%',
                p_crawl_event_id;
        end if;


        if (
            v_existing_observation_mrp
                is distinct from
                (
                    p_product ->> 'mrp'
                )::numeric

            or v_existing_observation_price
                is distinct from
                (
                    p_product ->> 'current_price'
                )::numeric

            or v_existing_observation_currency
                is distinct from
                coalesce(
                    nullif(
                        upper(
                            btrim(
                                p_product ->> 'currency'
                            )
                        ),
                        ''
                    ),
                    'INR'
                )

            or v_existing_observation_in_stock
                is distinct from
                (
                    p_product ->> 'in_stock'
                )::boolean
        ) then
            raise exception
                'crawl_event_id was retried with a different listing observation payload: event=%',
                p_crawl_event_id;
        end if;


        -- ====================================================
        -- Existing event must contain exactly the same variant
        -- identity set as the retry.
        --
        -- This check happens BEFORE variant inserts so a retry
        -- cannot mutate an already-committed crawl event by
        -- adding or removing variants.
        -- ====================================================

        select count(*)
        into v_existing_event_variant_count
        from public.listing_variant_observations observation
        join public.listing_variants variant
          on variant.id =
             observation.listing_variant_id
        where observation.crawl_event_id =
              p_crawl_event_id
          and variant.listing_id =
              v_listing_id;


        v_incoming_variant_count :=
            jsonb_array_length(
                p_product -> 'variants'
            );


        if v_existing_event_variant_count
            <> v_incoming_variant_count then
            raise exception
                'crawl_event_id was retried with a different variant set: event=%',
                p_crawl_event_id;
        end if;


        if exists (
            select 1
            from public.listing_variant_observations observation
            join public.listing_variants variant
              on variant.id =
                 observation.listing_variant_id
            where observation.crawl_event_id =
                  p_crawl_event_id
              and variant.listing_id =
                  v_listing_id
              and not exists (
                  select 1
                  from jsonb_array_elements(
                      p_product -> 'variants'
                  ) as item(value)
                  where nullif(
                      btrim(
                          item.value
                          ->> 'variant_key'
                      ),
                      ''
                  ) = variant.variant_key
              )
        ) then
            raise exception
                'crawl_event_id was retried with different variant identities: event=%',
                p_crawl_event_id;
        end if;

    else
        v_observation_created := true;
    end if;


    -- ========================================================
    -- Listing-variant historical observations
    --
    -- One crawl event may legitimately contain many variants.
    --
    -- Identity is therefore:
    --
    --     crawl_event_id + listing_variant_id
    --
    -- Retrying the same event does not append duplicates.
    -- ========================================================

    for v_variant in
        select item.value
        from jsonb_array_elements(
            p_product -> 'variants'
        ) as item(value)
        order by item.value ->> 'variant_key'
    loop
        v_variant_key := nullif(
            btrim(
                v_variant ->> 'variant_key'
            ),
            ''
        );


        if v_variant_key is null then
            raise exception
                'variant_key is required during observation persistence';
        end if;


        v_listing_variant_id := null;


        select variant.id
        into v_listing_variant_id
        from public.listing_variants variant
        where variant.listing_id = v_listing_id
          and variant.variant_key = v_variant_key;


        if v_listing_variant_id is null then
            raise exception
                'Listing variant missing during observation persistence: listing=%, variant=%',
                v_listing_id,
                v_variant_key;
        end if;


        v_variant_observation_id := null;
        v_existing_variant_observation_checked_at := null;


        insert into public.listing_variant_observations (
            listing_variant_id,
            crawl_event_id,
            checked_at,
            mrp,
            selling_price,
            currency,
            in_stock,
            stock_remaining,
            raw_data
        )
        values (
            v_listing_variant_id,
            p_crawl_event_id,
            p_checked_at,
            (
                v_variant ->> 'mrp'
            )::numeric,
            (
                v_variant ->> 'current_price'
            )::numeric,
            coalesce(
                nullif(
                    upper(
                        btrim(
                            p_product ->> 'currency'
                        )
                    ),
                    ''
                ),
                'INR'
            ),
            (
                v_variant ->> 'in_stock'
            )::boolean,
            (
                v_variant ->> 'stock_remaining'
            )::integer,
            jsonb_build_object(
                'source',
                'phase1_ingestion',
                'crawl_event_id',
                p_crawl_event_id::text,
                'variant_key',
                v_variant_key
            )
        )
        on conflict (
            crawl_event_id,
            listing_variant_id
        )
        where crawl_event_id is not null
        do nothing
        returning id
        into v_variant_observation_id;


        if v_variant_observation_id is null then
            select
                observation.id,
                observation.checked_at,
                observation.mrp,
                observation.selling_price,
                observation.currency,
                observation.in_stock,
                observation.stock_remaining
            into
                v_variant_observation_id,
                v_existing_variant_observation_checked_at,
                v_existing_variant_observation_mrp,
                v_existing_variant_observation_price,
                v_existing_variant_observation_currency,
                v_existing_variant_observation_in_stock,
                v_existing_variant_observation_stock_remaining
            from public.listing_variant_observations observation
            where observation.crawl_event_id
                    = p_crawl_event_id
              and observation.listing_variant_id
                    = v_listing_variant_id;


            if v_variant_observation_id is null then
                raise exception
                    'Variant observation conflict resolved without a visible winner: event=%, variant=%',
                    p_crawl_event_id,
                    v_variant_key;
            end if;


            if v_existing_variant_observation_checked_at
                <> p_checked_at then
                raise exception
                    'Variant crawl event was retried with a different checked_at: event=%, variant=%',
                    p_crawl_event_id,
                    v_variant_key;
            end if;


            if (
                v_existing_variant_observation_mrp
                    is distinct from
                    (
                        v_variant ->> 'mrp'
                    )::numeric

                or v_existing_variant_observation_price
                    is distinct from
                    (
                        v_variant
                        ->> 'current_price'
                    )::numeric

                or v_existing_variant_observation_currency
                    is distinct from
                    coalesce(
                        nullif(
                            upper(
                                btrim(
                                    p_product
                                    ->> 'currency'
                                )
                            ),
                            ''
                        ),
                        'INR'
                    )

                or v_existing_variant_observation_in_stock
                    is distinct from
                    (
                        v_variant
                        ->> 'in_stock'
                    )::boolean

                or v_existing_variant_observation_stock_remaining
                    is distinct from
                    (
                        v_variant
                        ->> 'stock_remaining'
                    )::integer
            ) then
                raise exception
                    'Variant crawl event was retried with a different observation payload: event=%, variant=%',
                    p_crawl_event_id,
                    v_variant_key;
            end if;
        end if;
    end loop;


    -- ========================================================
    -- Final RPC result
    --
    -- This contract is consumed by
    -- crawler.phase1_ingestion_contract.
    --
    -- listing_created describes this invocation only.
    --
    -- observation_created is false when an identical
    -- crawl_event_id was safely retried and the existing
    -- listing observation was reused.
    -- ========================================================

    return jsonb_build_object(
        'product_id',
        v_product_id,

        'listing_id',
        v_listing_id,

        'listing_created',
        v_listing_created,

        'crawl_event_id',
        p_crawl_event_id,

        'listing_observation_id',
        v_listing_observation_id,

        'observation_created',
        v_observation_created,

        'variants',
        v_variant_results
    );
end;
$$;


revoke all
on function public.bootstrap_phase1_catalog(
    text,
    text,
    text,
    text,
    uuid,
    timestamptz,
    jsonb
)
from public;

revoke all
on function public.bootstrap_phase1_catalog(
    text,
    text,
    text,
    text,
    uuid,
    timestamptz,
    jsonb
)
from anon;

revoke all
on function public.bootstrap_phase1_catalog(
    text,
    text,
    text,
    text,
    uuid,
    timestamptz,
    jsonb
)
from authenticated;

grant execute
on function public.bootstrap_phase1_catalog(
    text,
    text,
    text,
    text,
    uuid,
    timestamptz,
    jsonb
)
to service_role;
