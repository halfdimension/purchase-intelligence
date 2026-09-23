from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from crawler.database import get_supabase
from crawler.phase1_ingestion_contract import (
    CATALOG_BOOTSTRAP_RPC,
    WATCH_MATERIALIZATION_RPC,
    CatalogBootstrapRequest,
    CatalogBootstrapResult,
    WatchMaterializationRequest,
    WatchMaterializationResult,
    parse_catalog_bootstrap_result,
    parse_watch_materialization_result,
)
from crawler.phase1_ingestion_policy import (
    validate_phase1_ingestion_lease_seconds,
)


MIN_CLAIM_LIMIT = 1
MAX_CLAIM_LIMIT = 50


@dataclass(frozen=True)
class ExistingCatalogVariant:
    canonical_variant_id: str | None
    variant_key: str
    active: bool


@dataclass(frozen=True)
class ExistingCatalogListing:
    product_id: str
    listing_id: str
    active: bool
    merchant_active: bool
    variants: tuple[
        ExistingCatalogVariant,
        ...
    ]


class TrackingRequestOwnershipLostError(
    RuntimeError
):
    """
    The worker's processing generation no longer owns the request.

    This is an internal concurrency outcome, not a user/product
    failure.
    """

    pass


def _existing_catalog_uuid(
    value: object,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned an invalid "
            f"{field_name}."
        )

    try:
        UUID(value)
    except ValueError as exc:
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned an invalid "
            f"{field_name}."
        ) from exc

    return value


def get_existing_phase1_catalog_listing(
    normalized_url: str,
    *,
    merchant_slug: str,
    adapter_key: str,
) -> ExistingCatalogListing | None:
    """
    Read authoritative catalog identity for one normalized URL.

    Inactive listings are deliberately returned rather than treated as
    absent. The materialization RPC remains authoritative for product,
    merchant, and listing activity, while this read prevents an existing
    URL from being scraped and bootstrapped as if it were new.
    """

    for value, field_name in (
        (normalized_url, "normalized_url"),
        (merchant_slug, "merchant_slug"),
        (adapter_key, "adapter_key"),
    ):
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                f"{field_name} must be a nonempty trimmed string."
            )

    supabase = get_supabase()

    response = (
        supabase
        .table("merchant_listings")
        .select(
            "id,"
            "product_id,"
            "merchant_id,"
            "url,"
            "active,"
            "merchant:merchants("
            "slug,"
            "adapter_key,"
            "active"
            "),"
            "variants:listing_variants("
            "canonical_variant_id,"
            "variant_key,"
            "active"
            ")"
        )
        .eq(
            "url",
            normalized_url,
        )
        .limit(2)
        .execute()
    )

    rows = response.data

    if rows is None:
        rows = []

    if not isinstance(rows, list):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned an "
            "unexpected response."
        )

    if not rows:
        return None

    if len(rows) != 1 or not isinstance(
        rows[0],
        dict,
    ):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup did not resolve "
            "exactly one listing."
        )

    listing = rows[0]

    _existing_catalog_uuid(
        listing.get("merchant_id"),
        "merchant_id",
    )

    if listing.get("url") != normalized_url:
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned a different URL."
        )

    listing_active = listing.get("active")

    if not isinstance(listing_active, bool):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned an invalid "
            "listing active state."
        )

    merchant = listing.get("merchant")

    if not isinstance(merchant, dict):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned an invalid "
            "merchant relationship."
        )

    if (
        merchant.get("slug") != merchant_slug
        or merchant.get("adapter_key") != adapter_key
    ):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned a different "
            "merchant identity."
        )

    merchant_active = merchant.get("active")

    if not isinstance(merchant_active, bool):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned an invalid "
            "merchant active state."
        )

    raw_variants = listing.get("variants")

    if not isinstance(raw_variants, list):
        raise RuntimeError(
            "Existing Phase 1 catalog lookup returned invalid variants."
        )

    variants: list[ExistingCatalogVariant] = []
    seen_variant_keys: set[str] = set()

    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise RuntimeError(
                "Existing Phase 1 catalog lookup returned an invalid "
                "variant."
            )

        variant_key = raw_variant.get(
            "variant_key"
        )

        if (
            not isinstance(variant_key, str)
            or not variant_key
            or variant_key != variant_key.strip()
        ):
            raise RuntimeError(
                "Existing Phase 1 catalog lookup returned an invalid "
                "variant_key."
            )

        if variant_key in seen_variant_keys:
            raise RuntimeError(
                "Existing Phase 1 catalog lookup returned duplicate "
                "variant keys."
            )

        seen_variant_keys.add(variant_key)
        variant_active = raw_variant.get(
            "active"
        )

        if not isinstance(variant_active, bool):
            raise RuntimeError(
                "Existing Phase 1 catalog lookup returned an invalid "
                "variant active state."
            )

        canonical_variant_id = raw_variant.get(
            "canonical_variant_id"
        )

        if canonical_variant_id is not None:
            canonical_variant_id = (
                _existing_catalog_uuid(
                    canonical_variant_id,
                    "canonical_variant_id",
                )
            )

        variants.append(
            ExistingCatalogVariant(
                canonical_variant_id=(
                    canonical_variant_id
                ),
                variant_key=variant_key,
                active=variant_active,
            )
        )

    return ExistingCatalogListing(
        product_id=_existing_catalog_uuid(
            listing.get("product_id"),
            "product_id",
        ),
        listing_id=_existing_catalog_uuid(
            listing.get("id"),
            "listing_id",
        ),
        active=listing_active,
        merchant_active=merchant_active,
        variants=tuple(variants),
    )


def claim_phase1_tracking_requests(
    limit: int = 1,
    *,
    lease_duration_seconds: int,
) -> list[dict]:
    """
    Atomically claim pending Phase 1 tracking requests.

    The PostgreSQL claim function owns concurrency control through
    FOR UPDATE SKIP LOCKED.

    This Python wrapper intentionally does not:
      - scrape URLs
      - validate merchant adapters
      - create catalog rows
      - create watch intents
      - modify crawler execution flow
    """

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
    ):
        raise ValueError(
            "Tracking request claim limit must be an integer."
        )

    if (
        limit < MIN_CLAIM_LIMIT
        or limit > MAX_CLAIM_LIMIT
    ):
        raise ValueError(
            "Tracking request claim limit must be "
            "between 1 and 50."
        )

    lease_duration_seconds = (
        validate_phase1_ingestion_lease_seconds(
            lease_duration_seconds
        )
    )
    supabase = get_supabase()

    response = (
        supabase
        .rpc(
            "claim_tracking_requests",
            {
                "p_limit": limit,
                "p_lease_duration_seconds": (
                    lease_duration_seconds
                ),
            },
        )
        .execute()
    )

    rows = response.data or []

    if not isinstance(rows, list):
        raise RuntimeError(
            "Tracking request claim RPC returned "
            "an unexpected response."
        )

    if len(rows) > limit:
        raise RuntimeError(
            "Tracking request claim RPC returned "
            "more rows than requested."
        )

    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError(
                "Tracking request claim RPC returned "
                "an invalid row."
            )

        if not row.get("id"):
            raise RuntimeError(
                "Claimed tracking request is missing its id."
            )

        if row.get("status") != "processing":
            raise RuntimeError(
                "Claimed tracking request is not "
                "in processing state."
            )

        attempt_count = row.get(
            "attempt_count"
        )

        if (
            isinstance(attempt_count, bool)
            or not isinstance(
                attempt_count,
                int,
            )
            or attempt_count < 1
        ):
            raise RuntimeError(
                "Claimed tracking request has an "
                "invalid attempt_count."
            )

        lease_expires_at = row.get(
            "lease_expires_at"
        )

        if (
            not isinstance(
                lease_expires_at,
                str,
            )
            or not lease_expires_at.strip()
        ):
            raise RuntimeError(
                "Claimed tracking request is missing "
                "lease_expires_at."
            )

        try:
            parsed_lease_expires_at = (
                datetime.fromisoformat(
                    lease_expires_at.strip().replace(
                        "Z",
                        "+00:00",
                    )
                )
            )
        except ValueError as exc:
            raise RuntimeError(
                "Claimed tracking request has an invalid "
                "lease_expires_at."
            ) from exc

        if parsed_lease_expires_at.tzinfo is None:
            raise RuntimeError(
                "Claimed tracking request lease_expires_at "
                "must be timezone-aware."
            )

    return rows


def renew_phase1_tracking_request_lease(
    request: dict,
    *,
    lease_duration_seconds: int,
) -> dict:
    """
    Extend one unexpired processing lease for its exact generation.

    PostgreSQL returns no row if the request is terminal, expired,
    missing, or owned by a newer attempt. All of those outcomes mean
    this worker must stop processing the request.
    """

    if not isinstance(request, dict):
        raise ValueError(
            "Tracking request must be a dictionary."
        )

    request_id = request.get("id")

    if (
        not isinstance(request_id, str)
        or not request_id.strip()
    ):
        raise ValueError(
            "Tracking request is missing its id."
        )

    attempt_count = request.get(
        "attempt_count"
    )

    if (
        isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_count < 1
    ):
        raise ValueError(
            "Tracking request has an invalid attempt_count."
        )

    lease_duration_seconds = (
        validate_phase1_ingestion_lease_seconds(
            lease_duration_seconds
        )
    )

    supabase = get_supabase()

    response = (
        supabase
        .rpc(
            "renew_tracking_request_lease",
            {
                "p_tracking_request_id": request_id,
                "p_attempt_count": attempt_count,
                "p_lease_duration_seconds": (
                    lease_duration_seconds
                ),
            },
        )
        .execute()
    )

    rows = response.data or []

    if not isinstance(rows, list):
        raise RuntimeError(
            "Tracking request lease renewal RPC returned "
            "an unexpected response."
        )

    if not rows:
        raise TrackingRequestOwnershipLostError(
            "Tracking request processing ownership was lost."
        )

    if len(rows) != 1:
        raise RuntimeError(
            "Tracking request lease renewal RPC returned "
            "an unexpected number of rows."
        )

    renewed = rows[0]

    if not isinstance(renewed, dict):
        raise RuntimeError(
            "Tracking request lease renewal RPC returned "
            "an invalid row."
        )

    if (
        renewed.get("id") != request_id
        or renewed.get("status") != "processing"
        or renewed.get("attempt_count")
        != attempt_count
    ):
        raise RuntimeError(
            "Tracking request lease renewal RPC returned "
            "different processing ownership."
        )

    lease_expires_at = renewed.get(
        "lease_expires_at"
    )

    if (
        not isinstance(lease_expires_at, str)
        or not lease_expires_at.strip()
    ):
        raise RuntimeError(
            "Renewed tracking request is missing "
            "lease_expires_at."
        )

    try:
        parsed_lease_expires_at = datetime.fromisoformat(
            lease_expires_at.strip().replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise RuntimeError(
            "Renewed tracking request has an invalid "
            "lease_expires_at."
        ) from exc

    if parsed_lease_expires_at.tzinfo is None:
        raise RuntimeError(
            "Renewed tracking request lease_expires_at "
            "must be timezone-aware."
        )

    return renewed


MAX_ERROR_CODE_LENGTH = 64
MAX_ERROR_MESSAGE_LENGTH = 2000


def mark_phase1_tracking_request_failed(
    request: dict,
    *,
    error_code: str,
    error_message: str,
) -> dict:
    """
    Mark one claimed tracking request as failed.

    The update is guarded by:
      - request id
      - processing status
      - claimed attempt_count

    This prevents a stale worker attempt from overwriting state
    belonging to a newer processing attempt.
    """

    if not isinstance(request, dict):
        raise ValueError(
            "Tracking request must be a dictionary."
        )

    request_id = request.get("id")

    if (
        not isinstance(request_id, str)
        or not request_id.strip()
    ):
        raise ValueError(
            "Tracking request is missing its id."
        )

    if request.get("status") != "processing":
        raise ValueError(
            "Tracking request must be in processing state."
        )

    attempt_count = request.get(
        "attempt_count"
    )

    if (
        isinstance(attempt_count, bool)
        or not isinstance(
            attempt_count,
            int,
        )
        or attempt_count < 1
    ):
        raise ValueError(
            "Tracking request has an invalid attempt_count."
        )

    if (
        not isinstance(error_code, str)
        or not error_code.strip()
    ):
        raise ValueError(
            "Tracking request failure requires an error code."
        )

    error_code = error_code.strip()

    if len(error_code) > MAX_ERROR_CODE_LENGTH:
        raise ValueError(
            "Tracking request error code is too long."
        )

    if (
        not isinstance(error_message, str)
        or not error_message.strip()
    ):
        raise ValueError(
            "Tracking request failure requires an error message."
        )

    error_message = (
        error_message
        .strip()[:MAX_ERROR_MESSAGE_LENGTH]
    )

    completed_at = datetime.now(
        timezone.utc
    ).isoformat()

    supabase = get_supabase()

    response = (
        supabase
        .table("tracking_requests")
        .update(
            {
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message,
                "completed_at": completed_at,
            }
        )
        .eq(
            "id",
            request_id,
        )
        .eq(
            "status",
            "processing",
        )
        .eq(
            "attempt_count",
            attempt_count,
        )
        .execute()
    )

    rows = response.data or []

    if not isinstance(rows, list):
        raise RuntimeError(
            "Tracking request failure update returned "
            "an unexpected response."
        )

    if not rows:
        raise TrackingRequestOwnershipLostError(
            "Tracking request processing ownership was lost."
        )

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one processing tracking "
            "request to be marked failed."
        )

    failed = rows[0]

    if failed.get("status") != "failed":
        raise RuntimeError(
            "Tracking request failure state was not persisted."
        )

    if failed.get("error_code") != error_code:
        raise RuntimeError(
            "Tracking request failure code was not persisted."
        )

    if not failed.get("completed_at"):
        raise RuntimeError(
            "Tracking request failure completed_at "
            "was not persisted."
        )

    return failed


def get_phase1_tracking_request_state(
    request: dict,
) -> dict:
    """
    Read authoritative request state after an ambiguous write.

    The query intentionally filters only by durable request id. The
    caller must compare attempt_count so a newer processing generation
    is observed as ownership loss rather than hidden as a missing row.
    """

    if not isinstance(request, dict):
        raise ValueError(
            "Tracking request must be a dictionary."
        )

    request_id = request.get("id")

    if (
        not isinstance(request_id, str)
        or not request_id.strip()
    ):
        raise ValueError(
            "Tracking request is missing its id."
        )

    attempt_count = request.get(
        "attempt_count"
    )

    if (
        isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_count < 1
    ):
        raise ValueError(
            "Tracking request has an invalid attempt_count."
        )

    supabase = get_supabase()

    response = (
        supabase
        .table("tracking_requests")
        .select(
            "id,"
            "status,"
            "attempt_count,"
            "lease_expires_at,"
            "result_product_id,"
            "result_listing_id,"
            "result_watch_id,"
            "error_code,"
            "completed_at"
        )
        .eq(
            "id",
            request_id,
        )
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not isinstance(rows, list):
        raise RuntimeError(
            "Tracking request reconciliation read returned "
            "an unexpected response."
        )

    if not rows:
        raise TrackingRequestOwnershipLostError(
            "Tracking request no longer exists."
        )

    if len(rows) != 1 or not isinstance(
        rows[0],
        dict,
    ):
        raise RuntimeError(
            "Tracking request reconciliation read returned "
            "an unexpected number of rows."
        )

    state = rows[0]

    if state.get("id") != request_id:
        raise RuntimeError(
            "Tracking request reconciliation read returned "
            "a different request."
        )

    state_attempt_count = state.get(
        "attempt_count"
    )

    if (
        isinstance(state_attempt_count, bool)
        or not isinstance(
            state_attempt_count,
            int,
        )
        or state_attempt_count < 1
    ):
        raise RuntimeError(
            "Tracking request reconciliation read returned "
            "an invalid attempt_count."
        )

    status = state.get("status")

    if status not in {
        "pending",
        "processing",
        "completed",
        "failed",
        "cancelled",
    }:
        raise RuntimeError(
            "Tracking request reconciliation read returned "
            "an invalid status."
        )

    return state

def persist_phase1_catalog_bootstrap(
    request: CatalogBootstrapRequest,
) -> CatalogBootstrapResult:
    """
    Persist one normalized Phase 1 crawl result through the
    transactional catalog-bootstrap RPC.

    All catalog identity, latest-state, observation, and
    idempotency writes are owned by PostgreSQL in one
    transaction.
    """

    if not isinstance(
        request,
        CatalogBootstrapRequest,
    ):
        raise ValueError(
            "Catalog bootstrap request has invalid type."
        )

    supabase = get_supabase()

    response = (
        supabase
        .rpc(
            CATALOG_BOOTSTRAP_RPC,
            request.to_rpc_params(),
        )
        .execute()
    )

    raw_result = response.data

    # A scalar jsonb RPC normally returns the JSON object
    # directly. Keep one narrow compatibility path for clients
    # that expose a single returned object as a one-item list.
    if isinstance(raw_result, list):
        if len(raw_result) != 1:
            raise RuntimeError(
                "Catalog bootstrap RPC returned an "
                "unexpected number of results."
            )

        raw_result = raw_result[0]

    try:
        result = parse_catalog_bootstrap_result(
            raw_result
        )
    except ValueError as exc:
        raise RuntimeError(
            "Catalog bootstrap RPC returned an "
            "invalid result."
        ) from exc

    if (
        result.crawl_event_id
        != request.crawl_event_id
    ):
        raise RuntimeError(
            "Catalog bootstrap RPC returned a different "
            "crawl_event_id."
        )

    return result


def persist_phase1_watch_materialization(
    request: WatchMaterializationRequest,
) -> WatchMaterializationResult:
    """
    Atomically create a Phase 1 watch and listing target, then
    complete its claimed tracking request.

    PostgreSQL owns ownership/domain validation, duplicate-watch
    protection, stale-attempt guarding, and transactionality.
    """

    if not isinstance(
        request,
        WatchMaterializationRequest,
    ):
        raise ValueError(
            "Watch materialization request has invalid type."
        )

    supabase = get_supabase()

    response = (
        supabase
        .rpc(
            WATCH_MATERIALIZATION_RPC,
            request.to_rpc_params(),
        )
        .execute()
    )

    raw_result = response.data

    if isinstance(raw_result, list):
        if len(raw_result) != 1:
            raise RuntimeError(
                "Watch materialization RPC returned an "
                "unexpected number of results."
            )

        raw_result = raw_result[0]

    try:
        result = parse_watch_materialization_result(
            raw_result
        )
    except ValueError as exc:
        raise RuntimeError(
            "Watch materialization RPC returned an "
            "invalid result."
        ) from exc

    if (
        result.tracking_request_id
        != request.tracking_request_id
        or result.product_id
        != request.product_id
        or result.listing_id
        != request.listing_id
    ):
        raise RuntimeError(
            "Watch materialization RPC returned "
            "different request or catalog identities."
        )

    return result
