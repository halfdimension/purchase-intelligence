from dataclasses import dataclass
from uuid import UUID


CATALOG_BOOTSTRAP_RPC = (
    "bootstrap_phase1_catalog"
)

WATCH_MATERIALIZATION_RPC = (
    "materialize_phase1_tracking_request"
)


def _require_nonempty_string(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string."
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name} must not be empty."
        )

    return normalized


def _require_uuid_string(
    value: object,
    field_name: str,
) -> str:
    value = _require_nonempty_string(
        value,
        field_name,
    )

    try:
        UUID(value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be a valid UUID."
        ) from exc

    return value


@dataclass(frozen=True)
class CatalogBootstrapRequest:
    """
    Trusted Python -> PostgreSQL RPC contract.

    `product` must already contain normalized persistence
    data. SQL must not contain merchant-specific parsing or
    shoe-size normalization logic.
    """

    merchant_slug: str
    adapter_key: str
    brand_slug: str
    normalized_url: str
    crawl_event_id: str
    checked_at: str
    product: dict

    def to_rpc_params(self) -> dict:
        merchant_slug = _require_nonempty_string(
            self.merchant_slug,
            "merchant_slug",
        )

        adapter_key = _require_nonempty_string(
            self.adapter_key,
            "adapter_key",
        )

        brand_slug = _require_nonempty_string(
            self.brand_slug,
            "brand_slug",
        )

        normalized_url = _require_nonempty_string(
            self.normalized_url,
            "normalized_url",
        )

        crawl_event_id = _require_uuid_string(
            self.crawl_event_id,
            "crawl_event_id",
        )

        checked_at = _require_nonempty_string(
            self.checked_at,
            "checked_at",
        )

        if not isinstance(self.product, dict):
            raise ValueError(
                "product must be a dictionary."
            )

        return {
            "p_merchant_slug": merchant_slug,
            "p_adapter_key": adapter_key,
            "p_brand_slug": brand_slug,
            "p_normalized_url": normalized_url,
            "p_crawl_event_id": crawl_event_id,
            "p_checked_at": checked_at,
            "p_product": self.product,
        }


@dataclass(frozen=True)
class CatalogBootstrapVariantResult:
    variant_key: str
    canonical_variant_id: str
    listing_variant_id: str


@dataclass(frozen=True)
class CatalogBootstrapResult:
    product_id: str
    listing_id: str
    listing_created: bool
    crawl_event_id: str
    listing_observation_id: int
    observation_created: bool
    variants: tuple[
        CatalogBootstrapVariantResult,
        ...
    ]


@dataclass(frozen=True)
class WatchMaterializationRequest:
    tracking_request_id: str
    attempt_count: int
    product_id: str
    listing_id: str
    normalized_url: str
    canonical_variant_id: str | None
    variant_key: str | None

    def to_rpc_params(self) -> dict:
        tracking_request_id = (
            _require_uuid_string(
                self.tracking_request_id,
                "tracking_request_id",
            )
        )

        if (
            isinstance(self.attempt_count, bool)
            or not isinstance(
                self.attempt_count,
                int,
            )
            or self.attempt_count < 1
        ):
            raise ValueError(
                "attempt_count must be a positive integer."
            )

        product_id = _require_uuid_string(
            self.product_id,
            "product_id",
        )

        listing_id = _require_uuid_string(
            self.listing_id,
            "listing_id",
        )

        normalized_url = _require_nonempty_string(
            self.normalized_url,
            "normalized_url",
        )

        canonical_variant_id = (
            _require_uuid_string(
                self.canonical_variant_id,
                "canonical_variant_id",
            )
            if self.canonical_variant_id
            is not None
            else None
        )

        variant_key = (
            _require_nonempty_string(
                self.variant_key,
                "variant_key",
            )
            if self.variant_key is not None
            else None
        )

        if (
            canonical_variant_id is None
        ) != (variant_key is None):
            raise ValueError(
                "canonical_variant_id and variant_key must "
                "both be supplied or both be null."
            )

        return {
            "p_tracking_request_id": (
                tracking_request_id
            ),
            "p_attempt_count": self.attempt_count,
            "p_product_id": product_id,
            "p_listing_id": listing_id,
            "p_normalized_url": normalized_url,
            "p_canonical_variant_id": (
                canonical_variant_id
            ),
            "p_variant_key": variant_key,
        }


@dataclass(frozen=True)
class WatchMaterializationResult:
    outcome: str
    tracking_request_id: str
    product_id: str
    listing_id: str
    watch_id: str
    already_completed: bool


def parse_catalog_bootstrap_result(
    value: object,
) -> CatalogBootstrapResult:
    if not isinstance(value, dict):
        raise ValueError(
            "Bootstrap RPC result must be an object."
        )

    product_id = _require_uuid_string(
        value.get("product_id"),
        "product_id",
    )

    listing_id = _require_uuid_string(
        value.get("listing_id"),
        "listing_id",
    )

    crawl_event_id = _require_uuid_string(
        value.get("crawl_event_id"),
        "crawl_event_id",
    )

    listing_created = value.get(
        "listing_created"
    )

    if not isinstance(listing_created, bool):
        raise ValueError(
            "listing_created must be boolean."
        )

    observation_created = value.get(
        "observation_created"
    )

    if not isinstance(
        observation_created,
        bool,
    ):
        raise ValueError(
            "observation_created must be boolean."
        )

    listing_observation_id = value.get(
        "listing_observation_id"
    )

    if (
        isinstance(
            listing_observation_id,
            bool,
        )
        or not isinstance(
            listing_observation_id,
            int,
        )
        or listing_observation_id <= 0
    ):
        raise ValueError(
            "listing_observation_id must be "
            "a positive integer."
        )

    raw_variants = value.get("variants")

    if not isinstance(raw_variants, list):
        raise ValueError(
            "variants must be a list."
        )

    variants: list[
        CatalogBootstrapVariantResult
    ] = []

    seen_variant_keys: set[str] = set()

    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise ValueError(
                "Each bootstrap variant result "
                "must be an object."
            )

        variant_key = _require_nonempty_string(
            raw_variant.get("variant_key"),
            "variant_key",
        )

        if variant_key in seen_variant_keys:
            raise ValueError(
                "Duplicate variant_key in "
                f"bootstrap result: {variant_key!r}"
            )

        seen_variant_keys.add(
            variant_key
        )

        variants.append(
            CatalogBootstrapVariantResult(
                variant_key=variant_key,
                canonical_variant_id=(
                    _require_uuid_string(
                        raw_variant.get(
                            "canonical_variant_id"
                        ),
                        "canonical_variant_id",
                    )
                ),
                listing_variant_id=(
                    _require_uuid_string(
                        raw_variant.get(
                            "listing_variant_id"
                        ),
                        "listing_variant_id",
                    )
                ),
            )
        )

    return CatalogBootstrapResult(
        product_id=product_id,
        listing_id=listing_id,
        listing_created=listing_created,
        crawl_event_id=crawl_event_id,
        listing_observation_id=(
            listing_observation_id
        ),
        observation_created=(
            observation_created
        ),
        variants=tuple(variants),
    )


def parse_watch_materialization_result(
    value: object,
) -> WatchMaterializationResult:
    if not isinstance(value, dict):
        raise ValueError(
            "Watch materialization RPC result must be an object."
        )

    outcome = _require_nonempty_string(
        value.get("outcome"),
        "outcome",
    )

    if outcome not in (
        "completed",
        "duplicate_watch",
    ):
        raise ValueError(
            "Watch materialization outcome is invalid."
        )

    already_completed = value.get(
        "already_completed"
    )

    if not isinstance(
        already_completed,
        bool,
    ):
        raise ValueError(
            "already_completed must be boolean."
        )

    return WatchMaterializationResult(
        outcome=outcome,
        tracking_request_id=(
            _require_uuid_string(
                value.get(
                    "tracking_request_id"
                ),
                "tracking_request_id",
            )
        ),
        product_id=_require_uuid_string(
            value.get("product_id"),
            "product_id",
        ),
        listing_id=_require_uuid_string(
            value.get("listing_id"),
            "listing_id",
        ),
        watch_id=_require_uuid_string(
            value.get("watch_id"),
            "watch_id",
        ),
        already_completed=already_completed,
    )
