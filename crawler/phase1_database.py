import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from crawler.models import ProductData, ProductVariant
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

    normalized = normalize_size(size)

    slug = re.sub(
        r"[^a-z0-9.]+",
        "-",
        normalized.lower(),
    )

    return f"size:{slug}"


@dataclass(frozen=True)
class ResolvedSizeVariantIdentity:
    merchant_size_label: str
    canonical_size: str
    variant_key: str
    eu_size: str | None = None


def _explicit_eu_size(
    merchant_size_label: str,
) -> str | None:
    normalized_label = merchant_size_label.upper()
    eu_markers = list(
        re.finditer(
            r"(?<![A-Z0-9])EU(?![A-Z])",
            normalized_label,
        )
    )

    if not eu_markers:
        return None

    matches = list(
        re.finditer(
            r"(?<![A-Z0-9])EU\s*"
            r"([0-9]+(?:\.[0-9]+)?)(?![0-9.])",
            normalized_label,
        )
    )

    if len(matches) != len(eu_markers):
        raise ValueError(
            "Colliding size label contains malformed explicit "
            f"EU-size information: {merchant_size_label!r}."
        )

    if len(matches) != 1:
        raise ValueError(
            "Colliding size label contains ambiguous explicit "
            f"EU-size information: {merchant_size_label!r}."
        )

    match = matches[0]

    if re.match(
        r"\s*(?:/|-|&|OR\b|TO\b)\s*[0-9]",
        normalized_label[match.end():],
    ):
        raise ValueError(
            "Colliding size label contains ambiguous explicit "
            f"EU-size information: {merchant_size_label!r}."
        )

    try:
        value = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueError(
            "Colliding size label contains an invalid explicit "
            f"EU size: {merchant_size_label!r}."
        ) from exc

    if value <= 0:
        raise ValueError(
            "Colliding size label contains an invalid explicit "
            f"EU size: {merchant_size_label!r}."
        )

    normalized_value = format(
        value.normalize(),
        "f",
    )

    return f"EU {normalized_value}"


def resolve_size_variant_identities(
    size_labels: list[str],
) -> list[ResolvedSizeVariantIdentity]:
    """
    Resolve size identity using the complete scraped collection.

    Existing base keys remain unchanged unless two or more variants
    collide. A collision is resolved only when every member has a
    distinct explicit EU size in its merchant label.
    """

    identities: list[ResolvedSizeVariantIdentity] = []
    indexes_by_base_key: dict[str, list[int]] = {}

    for size_label in size_labels:
        if not isinstance(size_label, str):
            raise ValueError(
                "Size variant label must be a string."
            )

        merchant_size_label = size_label.strip()

        if not merchant_size_label:
            raise ValueError(
                "Size variant label must not be empty."
            )

        canonical_size = normalize_size(
            merchant_size_label
        )
        base_variant_key = size_variant_key(
            merchant_size_label
        )
        index = len(identities)

        identities.append(
            ResolvedSizeVariantIdentity(
                merchant_size_label=(
                    merchant_size_label
                ),
                canonical_size=canonical_size,
                variant_key=base_variant_key,
            )
        )
        indexes_by_base_key.setdefault(
            base_variant_key,
            [],
        ).append(index)

    for base_variant_key, indexes in (
        indexes_by_base_key.items()
    ):
        if len(indexes) == 1:
            continue

        resolved_keys: set[str] = set()

        for index in indexes:
            identity = identities[index]
            eu_size = _explicit_eu_size(
                identity.merchant_size_label
            )

            if eu_size is None:
                raise ValueError(
                    "Multiple size variants normalize to "
                    f"{base_variant_key!r}, but distinct explicit "
                    "EU sizes are not available for every label."
                )

            eu_slug = re.sub(
                r"[^a-z0-9.]+",
                "-",
                eu_size.lower(),
            )
            resolved_key = (
                f"{base_variant_key}-{eu_slug}"
            )

            if resolved_key in resolved_keys:
                raise ValueError(
                    "Multiple size variants still normalize to "
                    f"the same resolved variant_key {resolved_key!r}."
                )

            resolved_keys.add(resolved_key)
            identities[index] = (
                ResolvedSizeVariantIdentity(
                    merchant_size_label=(
                        identity.merchant_size_label
                    ),
                    canonical_size=(
                        identity.canonical_size
                    ),
                    variant_key=resolved_key,
                    eu_size=eu_size,
                )
            )

    seen_variant_keys: set[str] = set()

    for identity in identities:
        if identity.variant_key in seen_variant_keys:
            raise ValueError(
                "Multiple size variants normalize to the same "
                f"resolved variant_key {identity.variant_key!r}."
            )

        seen_variant_keys.add(identity.variant_key)

    return identities


def _identity_for_existing_variant_key(
    size_label: str,
    variant_key: str,
) -> ResolvedSizeVariantIdentity:
    if not isinstance(size_label, str):
        raise ValueError(
            "Size variant label must be a string."
        )

    merchant_size_label = size_label.strip()

    if not merchant_size_label:
        raise ValueError(
            "Size variant label must not be empty."
        )

    if (
        not isinstance(variant_key, str)
        or not variant_key
        or variant_key != variant_key.strip()
    ):
        raise RuntimeError(
            "Existing Phase 1 listing variant has an invalid "
            "variant_key."
        )

    canonical_size = normalize_size(
        merchant_size_label
    )
    base_variant_key = size_variant_key(
        merchant_size_label
    )

    if variant_key == base_variant_key:
        return ResolvedSizeVariantIdentity(
            merchant_size_label=merchant_size_label,
            canonical_size=canonical_size,
            variant_key=variant_key,
        )

    collision_prefix = (
        f"{base_variant_key}-eu-"
    )

    if not variant_key.startswith(
        collision_prefix
    ):
        raise RuntimeError(
            "Existing Phase 1 listing variant key is incompatible "
            f"with scraped size label {merchant_size_label!r}."
        )

    stored_eu_token = variant_key[
        len(collision_prefix):
    ]

    if re.fullmatch(
        r"[0-9]+(?:\.[0-9]+)?",
        stored_eu_token,
    ) is None:
        raise RuntimeError(
            "Existing Phase 1 listing variant has an invalid "
            "collision-disambiguated variant_key."
        )

    try:
        stored_eu_value = Decimal(
            stored_eu_token
        )
    except InvalidOperation as exc:
        raise RuntimeError(
            "Existing Phase 1 listing variant has an invalid "
            "collision-disambiguated variant_key."
        ) from exc

    if stored_eu_value <= 0:
        raise RuntimeError(
            "Existing Phase 1 listing variant has an invalid "
            "collision-disambiguated variant_key."
        )

    normalized_stored_eu = format(
        stored_eu_value.normalize(),
        "f",
    )

    if (
        variant_key
        != f"{collision_prefix}{normalized_stored_eu}"
    ):
        raise RuntimeError(
            "Existing Phase 1 listing variant has a non-canonical "
            "collision-disambiguated variant_key."
        )

    eu_size = f"EU {normalized_stored_eu}"
    try:
        explicit_eu_size = _explicit_eu_size(
            merchant_size_label
        )
    except ValueError as exc:
        raise RuntimeError(
            "Scraped size label has ambiguous explicit EU identity "
            "for its existing Phase 1 listing variant."
        ) from exc

    if (
        explicit_eu_size is not None
        and explicit_eu_size != eu_size
    ):
        raise RuntimeError(
            "Existing Phase 1 listing variant EU identity is "
            f"incompatible with scraped size label "
            f"{merchant_size_label!r}."
        )

    return ResolvedSizeVariantIdentity(
        merchant_size_label=merchant_size_label,
        canonical_size=canonical_size,
        variant_key=variant_key,
        eu_size=eu_size,
    )


def _select_phase1_listing_variants(
    supabase,
    *,
    listing_id: str,
    identity_column: str,
    identity_value: str,
) -> list[dict]:
    response = (
        supabase
        .table("listing_variants")
        .select(
            "id,"
            "canonical_variant_id,"
            "external_sku,"
            "variant_key"
        )
        .eq(
            "listing_id",
            listing_id,
        )
        .eq(
            identity_column,
            identity_value,
        )
        .limit(2)
        .execute()
    )

    return response.data or []


def upsert_phase1_listing_variants(
    product: ProductData,
    listing: dict,
    checked_at: str | None = None,
) -> list[dict]:
    """
    Update latest merchant-specific variant state for an
    existing Phase 1 listing.

    A known merchant SKU anchors the already-persisted listing
    variant. The SKU is never incorporated into canonical identity.
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
    existing_by_index: list[dict | None] = []
    seen_external_skus: set[str] = set()
    needs_normalized_fallback = False

    for variant in product.variants:
        external_sku = (
            variant.sku.strip()
            if isinstance(variant.sku, str)
            and variant.sku.strip()
            else None
        )

        if external_sku is None:
            existing_by_index.append(None)
            needs_normalized_fallback = True
            continue

        if external_sku in seen_external_skus:
            raise RuntimeError(
                "Scraped Phase 1 variants contain duplicate "
                f"external SKU {external_sku!r}."
            )

        seen_external_skus.add(external_sku)
        existing_rows = _select_phase1_listing_variants(
            supabase,
            listing_id=listing_id,
            identity_column="external_sku",
            identity_value=external_sku,
        )

        if len(existing_rows) > 1:
            raise RuntimeError(
                "Expected at most one existing Phase 1 "
                f"listing variant for external SKU {external_sku!r}, "
                f"found {len(existing_rows)}."
            )

        existing = (
            existing_rows[0]
            if existing_rows
            else None
        )
        existing_by_index.append(existing)

        if existing is None:
            needs_normalized_fallback = True

    fallback_identities = (
        resolve_size_variant_identities(
            [variant.size for variant in product.variants]
        )
        if needs_normalized_fallback
        else None
    )
    resolved_variants: list[
        tuple[
            ProductVariant,
            ResolvedSizeVariantIdentity,
            dict,
        ]
    ] = []
    matched_listing_variant_ids: set[str] = set()

    for index, (variant, existing) in enumerate(
        zip(
            product.variants,
            existing_by_index,
            strict=True,
        )
    ):
        if existing is None:
            if fallback_identities is None:
                raise RuntimeError(
                    "Phase 1 variant fallback identity is missing."
                )

            identity = fallback_identities[index]
            existing_rows = _select_phase1_listing_variants(
                supabase,
                listing_id=listing_id,
                identity_column="variant_key",
                identity_value=identity.variant_key,
            )

            if len(existing_rows) != 1:
                raise RuntimeError(
                    "Expected exactly one existing Phase 1 "
                    "listing variant for "
                    f"{identity.variant_key!r}, found "
                    f"{len(existing_rows)}."
                )

            existing = existing_rows[0]
        else:
            existing_variant_key = existing.get(
                "variant_key"
            )

            if (
                not isinstance(existing_variant_key, str)
                or not existing_variant_key.strip()
            ):
                raise RuntimeError(
                    "Existing Phase 1 listing variant is missing "
                    "its variant_key."
                )

            identity = _identity_for_existing_variant_key(
                variant.size,
                existing_variant_key,
            )

        existing_id = existing.get("id")

        if (
            not isinstance(existing_id, str)
            or not existing_id.strip()
        ):
            raise RuntimeError(
                "Existing Phase 1 listing variant is missing its id."
            )

        if existing_id in matched_listing_variant_ids:
            raise RuntimeError(
                "Multiple scraped variants resolved to the same "
                "existing Phase 1 listing variant."
            )

        matched_listing_variant_ids.add(existing_id)
        resolved_variants.append(
            (
                variant,
                identity,
                existing,
            )
        )

    for variant, identity, existing in resolved_variants:
        variant_key = identity.variant_key
        external_sku = (
            variant.sku.strip()
            if isinstance(variant.sku, str)
            and variant.sku.strip()
            else None
        )

        attributes = {
            "size": identity.canonical_size,
            "merchant_size_label": (
                identity.merchant_size_label
            ),
        }

        if identity.eu_size is not None:
            attributes["eu_size"] = identity.eu_size

        payload = {
            "external_sku": external_sku,
            "title": identity.merchant_size_label,
            "attributes": attributes,
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

    Saved listing variants supply authoritative variant keys;
    external SKU or exact merchant label only associates source data.
    """

    if checked_at is None:
        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

    variants_by_sku: dict[str, list[ProductVariant]] = {}
    variants_by_label: dict[
        str,
        list[ProductVariant],
    ] = {}

    for variant in product.variants:
        external_sku = (
            variant.sku.strip()
            if isinstance(variant.sku, str)
            and variant.sku.strip()
            else None
        )
        if not isinstance(variant.size, str):
            raise RuntimeError(
                "Scraped Phase 1 variant size must be a string."
            )

        merchant_size_label = variant.size.strip()

        if not merchant_size_label:
            raise RuntimeError(
                "Scraped Phase 1 variant size must not be empty."
            )

        if external_sku is not None:
            variants_by_sku.setdefault(
                external_sku,
                [],
            ).append(variant)

        variants_by_label.setdefault(
            merchant_size_label,
            [],
        ).append(variant)

    matched_source_ids: set[int] = set()
    variant_pairs: list[
        tuple[dict, ProductVariant]
    ] = []

    for saved_variant in saved_variants:
        external_sku = saved_variant.get(
            "external_sku"
        )
        normalized_external_sku = (
            external_sku.strip()
            if isinstance(external_sku, str)
            and external_sku.strip()
            else None
        )

        if normalized_external_sku is not None:
            candidates = variants_by_sku.get(
                normalized_external_sku,
                [],
            )
            identity_description = (
                "external SKU "
                f"{normalized_external_sku!r}"
            )
        else:
            attributes = saved_variant.get(
                "attributes"
            )
            attribute_label = (
                attributes.get(
                    "merchant_size_label"
                )
                if isinstance(attributes, dict)
                else None
            )
            raw_label = (
                attribute_label
                if isinstance(attribute_label, str)
                and attribute_label.strip()
                else saved_variant.get("title")
            )
            merchant_size_label = (
                raw_label.strip()
                if isinstance(raw_label, str)
                and raw_label.strip()
                else None
            )

            if merchant_size_label is None:
                raise RuntimeError(
                    "Phase 1 listing variant without an external "
                    "SKU is missing its merchant size label."
                )

            candidates = variants_by_label.get(
                merchant_size_label,
                [],
            )
            identity_description = (
                "merchant size label "
                f"{merchant_size_label!r}"
            )

        if len(candidates) != 1:
            raise RuntimeError(
                "Expected exactly one scraped variant for saved "
                f"{identity_description}, found {len(candidates)}."
            )

        source_variant = candidates[0]
        source_id = id(source_variant)

        if source_id in matched_source_ids:
            raise RuntimeError(
                "Multiple saved Phase 1 listing variants resolved "
                "to the same scraped variant."
            )

        matched_source_ids.add(source_id)
        variant_pairs.append(
            (
                saved_variant,
                source_variant,
            )
        )

    if (
        len(variant_pairs) != len(product.variants)
        or len(matched_source_ids) != len(product.variants)
    ):
        raise RuntimeError(
            "Saved and scraped Phase 1 variants do not form a "
            "complete one-to-one association."
        )

    supabase = get_supabase()

    observations: list[dict] = []

    for saved_variant, source_variant in variant_pairs:
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


def get_phase1_crawl_targets() -> list[dict]:
    """
    Resolve the unique active merchant listings that need to be
    crawled because at least one active Phase 1 watch requires
    them.

    specific_listing / selected_listings:
        use explicit watch_listing_targets.

    any_listing:
        use every active listing for the watched canonical
        product.

    Inactive listings and listings belonging to inactive
    merchants are excluded.
    """

    supabase = get_supabase()

    watch_response = (
        supabase
        .table("watch_intents")
        .select(
            "id,"
            "product_id,"
            "tracking_scope"
        )
        .eq(
            "status",
            "active",
        )
        .execute()
    )

    watches = watch_response.data or []

    if not watches:
        return []

    explicit_watch_ids: list[str] = []
    any_listing_product_ids: set[str] = set()

    for watch in watches:
        scope = watch.get("tracking_scope")

        if scope in (
            "specific_listing",
            "selected_listings",
        ):
            explicit_watch_ids.append(
                watch["id"]
            )

        elif scope == "any_listing":
            any_listing_product_ids.add(
                watch["product_id"]
            )

        else:
            raise RuntimeError(
                "Unsupported Phase 1 tracking scope: "
                f"{scope!r}"
            )

    listing_ids: set[str] = set()

    if explicit_watch_ids:
        target_response = (
            supabase
            .table("watch_listing_targets")
            .select(
                "watch_id,"
                "listing_id"
            )
            .in_(
                "watch_id",
                explicit_watch_ids,
            )
            .execute()
        )

        for target in target_response.data or []:
            listing_ids.add(
                target["listing_id"]
            )

    if any_listing_product_ids:
        any_listing_response = (
            supabase
            .table("merchant_listings")
            .select("id")
            .in_(
                "product_id",
                list(any_listing_product_ids),
            )
            .eq(
                "active",
                True,
            )
            .execute()
        )

        for listing in (
            any_listing_response.data or []
        ):
            listing_ids.add(
                listing["id"]
            )

    if not listing_ids:
        return []

    merchant_response = (
        supabase
        .table("merchants")
        .select(
            "id,"
            "slug,"
            "name,"
            "adapter_key"
        )
        .eq(
            "active",
            True,
        )
        .execute()
    )

    merchants = {
        row["id"]: row
        for row in merchant_response.data or []
    }

    if not merchants:
        return []

    listing_response = (
        supabase
        .table("merchant_listings")
        .select(
            "id,"
            "product_id,"
            "merchant_id,"
            "url,"
            "title,"
            "active"
        )
        .in_(
            "id",
            list(listing_ids),
        )
        .in_(
            "merchant_id",
            list(merchants),
        )
        .eq(
            "active",
            True,
        )
        .order("url")
        .execute()
    )

    crawl_targets: list[dict] = []

    seen_urls: set[str] = set()

    for listing in listing_response.data or []:
        url = listing.get("url")
        merchant_id = listing.get(
            "merchant_id"
        )

        if not url:
            raise RuntimeError(
                "Phase 1 crawl target is missing its URL."
            )

        if url in seen_urls:
            raise RuntimeError(
                "Duplicate Phase 1 crawl target URL: "
                f"{url!r}"
            )

        merchant = merchants.get(
            merchant_id
        )

        if merchant is None:
            raise RuntimeError(
                "Phase 1 crawl target has no active "
                f"merchant: {merchant_id!r}"
            )

        seen_urls.add(url)

        crawl_targets.append(
            {
                **listing,
                "merchant": merchant,
            }
        )

    return crawl_targets
