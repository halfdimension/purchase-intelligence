from datetime import datetime, timezone

from crawler.models import ProductData
from crawler.database import get_supabase


def get_phase1_listing_for_url(
    url: str,
) -> dict:
    """
    Resolve the existing Phase 1 merchant listing for a crawled URL.

    During the controlled Phase 1 cutover we require the listing
    to already exist. The initial Nike listing was created by the
    Phase 0 -> Phase 1 backfill.
    """

    supabase = get_supabase()

    response = (
        supabase
        .table("merchant_listings")
        .select(
            "id,"
            "product_id,"
            "merchant_id,"
            "url,"
            "title,"
            "current_price,"
            "current_mrp,"
            "currency,"
            "in_stock,"
            "last_checked_at"
        )
        .eq(
            "url",
            url,
        )
        .limit(2)
        .execute()
    )

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one Phase 1 merchant listing "
            f"for URL {url!r}, found {len(rows)}."
        )

    return rows[0]


def update_phase1_listing_state(
    product: ProductData,
    listing: dict,
    checked_at: str | None = None,
) -> dict:
    """
    Update the latest-state cache for an existing Phase 1
    merchant listing.

    Historical observations are written separately.
    """

    listing_id = listing.get("id")

    if not listing_id:
        raise RuntimeError(
            "Phase 1 merchant listing is missing its id."
        )

    listing_url = listing.get("url")

    if listing_url != product.url:
        raise RuntimeError(
            "Refusing to update a Phase 1 listing with data "
            f"from a different URL: {product.url!r}"
        )

    if checked_at is None:
        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

    payload = {
        "title": product.name,
        "image_url": product.image_url,
        "current_mrp": product.mrp,
        "current_price": product.current_price,
        "currency": product.currency or "INR",
        "in_stock": product.in_stock,
        "last_checked_at": checked_at,
    }

    supabase = get_supabase()

    response = (
        supabase
        .table("merchant_listings")
        .update(payload)
        .eq(
            "id",
            listing_id,
        )
        .execute()
    )

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one updated Phase 1 merchant "
            f"listing, received {len(rows)}."
        )

    return rows[0]


def insert_phase1_listing_observation(
    product: ProductData,
    listing: dict,
    checked_at: str | None = None,
) -> dict:
    """
    Persist one immutable historical observation for a Phase 1
    merchant listing.
    """

    listing_id = listing.get("id")

    if not listing_id:
        raise RuntimeError(
            "Phase 1 merchant listing is missing its id."
        )

    if listing.get("url") != product.url:
        raise RuntimeError(
            "Refusing to create a Phase 1 observation for a "
            f"different URL: {product.url!r}"
        )

    if checked_at is None:
        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

    payload = {
        "listing_id": listing_id,
        "checked_at": checked_at,
        "mrp": product.mrp,
        "selling_price": product.current_price,
        "currency": product.currency or "INR",
        "in_stock": product.in_stock,
        "stock_remaining": None,
        "delivery_fee": None,
        "effective_price": None,
        "raw_data": {
            "source": "phase1_crawler",
        },
    }

    supabase = get_supabase()

    response = (
        supabase
        .table("listing_observations")
        .insert(payload)
        .execute()
    )

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one Phase 1 listing observation, "
            f"received {len(rows)}."
        )

    return rows[0]


def normalize_size(size: str) -> str:
    """
    Normalize merchant shoe-size labels into the Phase 1
    canonical size format used by the Nike backfill.

    Examples:
        UK 7 -> UK 7
        UK 6 (EU 40) -> UK 6
    """

    import re

    value = size.strip().upper()

    match = re.search(
        r"UK\s*([0-9]+(?:\.[0-9]+)?)",
        value,
    )

    if not match:
        return value

    return f"UK {match.group(1)}"


def size_variant_key(size: str) -> str:
    """
    Produce the stable Phase 1 variant key used by the backfill.

    Example:
        UK 9 -> size:uk-9
    """

    import re

    normalized = normalize_size(size)

    slug = re.sub(
        r"[^a-z0-9.]+",
        "-",
        normalized.lower(),
    )

    return f"size:{slug}"


def upsert_phase1_listing_variants(
    product: ProductData,
    listing: dict,
    checked_at: str | None = None,
) -> list[dict]:
    """
    Update latest merchant-specific variant state for an
    existing Phase 1 listing.
    """

    listing_id = listing.get("id")

    if not listing_id:
        raise RuntimeError(
            "Phase 1 merchant listing is missing its id."
        )

    if listing.get("url") != product.url:
        raise RuntimeError(
            "Refusing to update Phase 1 variants using data "
            f"from a different URL: {product.url!r}"
        )

    if checked_at is None:
        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

    supabase = get_supabase()

    saved_variants: list[dict] = []

    for variant in product.variants:
        normalized_size = normalize_size(
            variant.size
        )

        variant_key = size_variant_key(
            variant.size
        )

        existing_response = (
            supabase
            .table("listing_variants")
            .select(
                "id,"
                "canonical_variant_id,"
                "variant_key"
            )
            .eq(
                "listing_id",
                listing_id,
            )
            .eq(
                "variant_key",
                variant_key,
            )
            .limit(2)
            .execute()
        )

        existing_rows = (
            existing_response.data or []
        )

        if len(existing_rows) != 1:
            raise RuntimeError(
                "Expected exactly one existing Phase 1 "
                f"listing variant for {variant_key!r}, "
                f"found {len(existing_rows)}."
            )

        existing = existing_rows[0]

        payload = {
            "external_sku": variant.sku,
            "title": variant.size,
            "attributes": {
                "size": normalized_size,
                "merchant_size_label": variant.size,
            },
            "current_mrp": variant.mrp,
            "current_price": variant.current_price,
            "currency": product.currency or "INR",
            "in_stock": variant.in_stock,
            "stock_remaining": variant.stock_remaining,
            "last_checked_at": checked_at,
            "active": True,
        }

        response = (
            supabase
            .table("listing_variants")
            .update(payload)
            .eq(
                "id",
                existing["id"],
            )
            .execute()
        )

        rows = response.data or []

        if len(rows) != 1:
            raise RuntimeError(
                "Expected exactly one updated Phase 1 "
                f"listing variant for {variant_key!r}, "
                f"received {len(rows)}."
            )

        saved_variants.append(
            rows[0]
        )

    return saved_variants


def insert_phase1_variant_observations(
    product: ProductData,
    saved_variants: list[dict],
    checked_at: str | None = None,
) -> list[dict]:
    """
    Persist one immutable historical observation for each
    merchant-specific Phase 1 listing variant.
    """

    if checked_at is None:
        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

    variants_by_key = {
        size_variant_key(variant.size): variant
        for variant in product.variants
    }

    supabase = get_supabase()

    observations: list[dict] = []

    for saved_variant in saved_variants:
        variant_key = saved_variant.get(
            "variant_key"
        )

        listing_variant_id = saved_variant.get(
            "id"
        )

        if not listing_variant_id:
            raise RuntimeError(
                "Phase 1 listing variant is missing its id."
            )

        if not variant_key:
            raise RuntimeError(
                "Phase 1 listing variant is missing its "
                "variant_key."
            )

        source_variant = variants_by_key.get(
            variant_key
        )

        if source_variant is None:
            raise RuntimeError(
                "Could not match scraped variant to saved "
                f"Phase 1 variant {variant_key!r}."
            )

        payload = {
            "listing_variant_id": listing_variant_id,
            "checked_at": checked_at,
            "mrp": source_variant.mrp,
            "selling_price": source_variant.current_price,
            "currency": product.currency or "INR",
            "in_stock": source_variant.in_stock,
            "stock_remaining": source_variant.stock_remaining,
            "raw_data": {
                "source": "phase1_crawler",
                "variant_key": variant_key,
                "merchant_size_label": source_variant.size,
            },
        }

        response = (
            supabase
            .table("listing_variant_observations")
            .insert(payload)
            .execute()
        )

        rows = response.data or []

        if len(rows) != 1:
            raise RuntimeError(
                "Expected exactly one Phase 1 variant "
                f"observation for {variant_key!r}, "
                f"received {len(rows)}."
            )

        observations.append(
            rows[0]
        )

    return observations


def save_product_phase1(
    product: ProductData,
) -> dict:
    """
    Persist one complete crawler result into the Phase 1 model.

    One crawl timestamp is shared across:
      - merchant listing latest state
      - listing historical observation
      - listing variant latest state
      - listing variant historical observations
    """

    checked_at = datetime.now(
        timezone.utc
    ).isoformat()

    listing = get_phase1_listing_for_url(
        product.url
    )

    updated_listing = update_phase1_listing_state(
        product,
        listing,
        checked_at=checked_at,
    )

    listing_observation = (
        insert_phase1_listing_observation(
            product,
            listing,
            checked_at=checked_at,
        )
    )

    saved_variants = upsert_phase1_listing_variants(
        product,
        listing,
        checked_at=checked_at,
    )

    variant_observations = (
        insert_phase1_variant_observations(
            product,
            saved_variants,
            checked_at=checked_at,
        )
    )

    return {
        "listing": updated_listing,
        "listing_observation": listing_observation,
        "variants": saved_variants,
        "variant_observations": variant_observations,
        "checked_at": checked_at,
    }
