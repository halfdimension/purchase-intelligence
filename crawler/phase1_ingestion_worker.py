from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Callable, TypeVar
from uuid import UUID, uuid5

import httpx
import requests
from playwright.sync_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from crawler.models import ProductData
from crawler.phase1_ingestion_adapters import (
    Phase1IngestionAdapter,
    get_phase1_ingestion_adapter,
)
from crawler.phase1_ingestion_contract import (
    CatalogBootstrapRequest,
    CatalogBootstrapResult,
    WatchMaterializationRequest,
)
from crawler.phase1_ingestion_database import (
    claim_phase1_tracking_requests,
    mark_phase1_tracking_request_failed,
    persist_phase1_catalog_bootstrap,
    persist_phase1_watch_materialization,
)
from crawler.phase1_ingestion_validation import (
    ValidatedIngestionTarget,
    validate_tracking_request_target,
)
from crawler.scrapers.browser_jsonld import (
    GuardedMainFrameHttpError,
    UnsafeMainFrameNavigationError,
)


logger = logging.getLogger(__name__)


class ProcessingStateError(RuntimeError):
    pass


class AmbiguousPersistenceError(RuntimeError):
    pass


INVALID_TARGET_ERROR_CODE = (
    "invalid_ingestion_target"
)

UNSUPPORTED_ADAPTER_ERROR_CODE = (
    "unsupported_ingestion_adapter"
)

SCRAPE_FAILED_ERROR_CODE = (
    "ingestion_scrape_failed"
)

INVALID_PRODUCT_ERROR_CODE = (
    "invalid_scraped_product"
)

CATALOG_BOOTSTRAP_FAILED_ERROR_CODE = (
    "catalog_bootstrap_failed"
)

INVALID_VARIANT_REQUIREMENTS_ERROR_CODE = (
    "invalid_variant_requirements"
)

REQUESTED_VARIANT_NOT_FOUND_ERROR_CODE = (
    "requested_variant_not_found"
)

WATCH_MATERIALIZATION_FAILED_ERROR_CODE = (
    "watch_materialization_failed"
)

CATALOG_BOOTSTRAP_OUTCOME_UNKNOWN_ERROR_CODE = (
    "catalog_bootstrap_outcome_unknown"
)

WATCH_MATERIALIZATION_OUTCOME_UNKNOWN_ERROR_CODE = (
    "watch_materialization_outcome_unknown"
)

DUPLICATE_WATCH_ERROR_CODE = (
    "duplicate_watch"
)

INGESTION_CRAWL_EVENT_NAMESPACE = UUID(
    "05dd841c-b7b5-5a28-8fc4-9fdb040c2cc2"
)

INTERNAL_CATALOG_FAILURE_MESSAGE = (
    "We could not save this product safely. An operator must review "
    "the request."
)

INTERNAL_WATCH_FAILURE_MESSAGE = (
    "We could not create this watch safely. An operator must review "
    "the request."
)

INTERNAL_SCRAPE_FAILURE_MESSAGE = (
    "The supported merchant page could not be retrieved safely."
)

INVALID_SCRAPED_PRODUCT_MESSAGE = (
    "The merchant returned product data that could not be validated "
    "safely."
)

SCRAPER_EXCEPTIONS = (
    requests.RequestException,
    PlaywrightError,
    GuardedMainFrameHttpError,
    UnsafeMainFrameNavigationError,
)

PersistenceRequest = TypeVar(
    "PersistenceRequest"
)
PersistenceResult = TypeVar(
    "PersistenceResult"
)


@dataclass(frozen=True)
class PreparedIngestionRequest:
    request: dict
    target: ValidatedIngestionTarget


@dataclass(frozen=True)
class Phase1IngestionResult:
    tracking_request_id: str
    status: str
    product_id: str | None = None
    listing_id: str | None = None
    watch_id: str | None = None
    error_code: str | None = None


def _request_identity(
    prepared: PreparedIngestionRequest,
) -> tuple[str, int]:
    request_id = prepared.request.get("id")
    attempt_count = prepared.request.get(
        "attempt_count"
    )

    if (
        not isinstance(request_id, str)
        or not request_id.strip()
    ):
        raise ProcessingStateError(
            "Prepared tracking request is missing its id."
        )

    try:
        UUID(request_id)
    except ValueError as exc:
        raise ProcessingStateError(
            "Prepared tracking request id is invalid."
        ) from exc

    if (
        isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_count < 1
    ):
        raise ProcessingStateError(
            "Prepared tracking request has an invalid attempt_count."
        )

    return request_id, attempt_count


def build_phase1_ingestion_event_identity(
    prepared: PreparedIngestionRequest,
) -> tuple[str, str]:
    """
    Build stable observation identity for one claimed attempt.

    Both values derive from durable claim data, so retrying an
    ambiguous catalog RPC uses the same crawl_event_id and
    checked_at rather than appending another historical event.
    """

    request_id, attempt_count = _request_identity(
        prepared
    )

    started_at = prepared.request.get(
        "started_at"
    )

    if (
        not isinstance(started_at, str)
        or not started_at.strip()
    ):
        raise ProcessingStateError(
            "Prepared tracking request is missing started_at."
        )

    try:
        parsed_started_at = datetime.fromisoformat(
            started_at.strip().replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise ProcessingStateError(
            "Prepared tracking request started_at is invalid."
        ) from exc

    if parsed_started_at.tzinfo is None:
        raise ProcessingStateError(
            "Prepared tracking request started_at must be timezone-aware."
        )

    checked_at = parsed_started_at.astimezone(
        timezone.utc
    ).isoformat()

    crawl_event_id = str(
        uuid5(
            INGESTION_CRAWL_EVENT_NAMESPACE,
            f"{request_id}:{attempt_count}",
        )
    )

    return crawl_event_id, checked_at


def build_phase1_catalog_bootstrap_request(
    prepared: PreparedIngestionRequest,
    product: ProductData,
    *,
    crawl_event_id: str,
    checked_at: str,
) -> CatalogBootstrapRequest:
    """
    Convert one validated ingestion target plus already-scraped
    product data into the normalized PostgreSQL bootstrap
    contract.

    This function performs no network access and no database
    writes.
    """

    if not isinstance(
        prepared,
        PreparedIngestionRequest,
    ):
        raise ValueError(
            "Prepared ingestion request has invalid type."
        )

    if not isinstance(
        product,
        ProductData,
    ):
        raise ValueError(
            "Scraped product has invalid type."
        )

    adapter = get_phase1_ingestion_adapter(
        prepared.target.adapter_key
    )

    product_payload = adapter.build_product_payload(
        product,
        prepared.target.url,
    )

    bootstrap_request = CatalogBootstrapRequest(
        merchant_slug=(
            prepared.target.merchant_slug
        ),
        adapter_key=(
            prepared.target.adapter_key
        ),
        brand_slug=adapter.brand_slug,
        normalized_url=(
            prepared.target.url
        ),
        crawl_event_id=crawl_event_id,
        checked_at=checked_at,
        product=product_payload,
    )

    # Validate the complete boundary contract now rather than
    # discovering malformed identifiers only at RPC time.
    bootstrap_request.to_rpc_params()

    return bootstrap_request


def resolve_phase1_requested_variant(
    prepared: PreparedIngestionRequest,
    adapter: Phase1IngestionAdapter,
    bootstrap: CatalogBootstrapResult,
) -> tuple[str | None, str | None]:
    variant_requirements = prepared.request.get(
        "variant_requirements"
    )

    if not isinstance(
        variant_requirements,
        dict,
    ):
        raise ValueError(
            "Tracking request variant_requirements must be an object."
        )

    variant_key = adapter.requested_variant_key(
        variant_requirements
    )

    if variant_key is None:
        return None, None

    matches = [
        variant
        for variant in bootstrap.variants
        if variant.variant_key == variant_key
    ]

    if len(matches) != 1:
        raise LookupError(
            "Requested variant was not found in the scraped listing: "
            f"{variant_key!r}."
        )

    return (
        matches[0].canonical_variant_id,
        variant_key,
    )


def _persist_with_one_retry(
    operation: Callable[
        [PersistenceRequest],
        PersistenceResult,
    ],
    request: PersistenceRequest,
) -> PersistenceResult:
    try:
        return operation(request)
    except httpx.RequestError:
        logger.warning(
            "Persistence transport failed; retrying the exact request once.",
            exc_info=True,
        )

    try:
        return operation(request)
    except httpx.RequestError as exc:
        raise AmbiguousPersistenceError(
            "Persistence outcome remains unknown after a transport failure."
        ) from exc


def _persist_failure(
    prepared: PreparedIngestionRequest,
    *,
    error_code: str,
    error_message: str,
) -> Phase1IngestionResult:
    failed = mark_phase1_tracking_request_failed(
        prepared.request,
        error_code=error_code,
        error_message=error_message,
    )

    return Phase1IngestionResult(
        tracking_request_id=failed["id"],
        status="failed",
        error_code=error_code,
    )


def process_phase1_ingestion_request(
    prepared: PreparedIngestionRequest,
) -> Phase1IngestionResult:
    """
    Execute one already-claimed trusted ingestion request.

    Expected target, scraping, persistence, and user-input
    failures are persisted with stable error codes. Programmer
    errors outside those boundaries continue to surface.
    """

    request_id, attempt_count = _request_identity(
        prepared
    )

    try:
        adapter = get_phase1_ingestion_adapter(
            prepared.target.adapter_key
        )
    except ValueError:
        logger.exception(
            "Tracking request %s resolved an unavailable adapter.",
            request_id,
        )

        return _persist_failure(
            prepared,
            error_code=(
                UNSUPPORTED_ADAPTER_ERROR_CODE
            ),
            error_message=(
                "This merchant adapter is not available for ingestion."
            ),
        )

    try:
        adapter.validate_target_url(
            prepared.target.url
        )
    except ValueError as exc:
        return _persist_failure(
            prepared,
            error_code=(
                INVALID_TARGET_ERROR_CODE
            ),
            error_message=str(exc),
        )

    crawl_event_id, checked_at = (
        build_phase1_ingestion_event_identity(
            prepared
        )
    )

    try:
        product = adapter.scrape(
            prepared.target.url
        )
    except SCRAPER_EXCEPTIONS:
        logger.exception(
            "Supported merchant scrape failed for tracking request %s.",
            request_id,
        )

        return _persist_failure(
            prepared,
            error_code=(
                SCRAPE_FAILED_ERROR_CODE
            ),
            error_message=(
                INTERNAL_SCRAPE_FAILURE_MESSAGE
            ),
        )

    try:
        adapter.validate_scraped_product(
            prepared.target.url,
            product,
        )

        bootstrap_request = (
            build_phase1_catalog_bootstrap_request(
                prepared,
                product,
                crawl_event_id=(
                    crawl_event_id
                ),
                checked_at=checked_at,
            )
        )
    except ValueError:
        logger.exception(
            "Scraped product validation failed for tracking request %s.",
            request_id,
        )

        return _persist_failure(
            prepared,
            error_code=(
                INVALID_PRODUCT_ERROR_CODE
            ),
            error_message=(
                INVALID_SCRAPED_PRODUCT_MESSAGE
            ),
        )

    try:
        bootstrap = _persist_with_one_retry(
            persist_phase1_catalog_bootstrap,
            bootstrap_request,
        )
    except AmbiguousPersistenceError:
        logger.exception(
            "Catalog bootstrap outcome is unknown for tracking request %s.",
            request_id,
        )

        return Phase1IngestionResult(
            tracking_request_id=request_id,
            status="processing",
            error_code=(
                CATALOG_BOOTSTRAP_OUTCOME_UNKNOWN_ERROR_CODE
            ),
        )
    except APIError:
        logger.exception(
            "Catalog bootstrap was rejected for tracking request %s.",
            request_id,
        )

        return _persist_failure(
            prepared,
            error_code=(
                CATALOG_BOOTSTRAP_FAILED_ERROR_CODE
            ),
            error_message=(
                INTERNAL_CATALOG_FAILURE_MESSAGE
            ),
        )
    except RuntimeError:
        logger.exception(
            "Catalog bootstrap contract failed for tracking request %s.",
            request_id,
        )

        raise

    try:
        canonical_variant_id, variant_key = (
            resolve_phase1_requested_variant(
                prepared,
                adapter,
                bootstrap,
            )
        )
    except ValueError as exc:
        return _persist_failure(
            prepared,
            error_code=(
                INVALID_VARIANT_REQUIREMENTS_ERROR_CODE
            ),
            error_message=str(exc),
        )
    except LookupError as exc:
        return _persist_failure(
            prepared,
            error_code=(
                REQUESTED_VARIANT_NOT_FOUND_ERROR_CODE
            ),
            error_message=str(exc),
        )

    materialization_request = (
        WatchMaterializationRequest(
            tracking_request_id=request_id,
            attempt_count=attempt_count,
            product_id=bootstrap.product_id,
            listing_id=bootstrap.listing_id,
            normalized_url=prepared.target.url,
            canonical_variant_id=(
                canonical_variant_id
            ),
            variant_key=variant_key,
        )
    )

    try:
        materialization = _persist_with_one_retry(
            persist_phase1_watch_materialization,
            materialization_request,
        )
    except AmbiguousPersistenceError:
        logger.exception(
            "Watch materialization outcome is unknown for "
            "tracking request %s.",
            request_id,
        )

        return Phase1IngestionResult(
            tracking_request_id=request_id,
            status="processing",
            product_id=bootstrap.product_id,
            listing_id=bootstrap.listing_id,
            error_code=(
                WATCH_MATERIALIZATION_OUTCOME_UNKNOWN_ERROR_CODE
            ),
        )
    except APIError:
        logger.exception(
            "Watch materialization was rejected for tracking request %s.",
            request_id,
        )

        return _persist_failure(
            prepared,
            error_code=(
                WATCH_MATERIALIZATION_FAILED_ERROR_CODE
            ),
            error_message=(
                INTERNAL_WATCH_FAILURE_MESSAGE
            ),
        )
    except RuntimeError:
        logger.exception(
            "Watch materialization contract failed for tracking request %s.",
            request_id,
        )

        raise

    if (
        materialization.outcome
        == "duplicate_watch"
    ):
        return Phase1IngestionResult(
            tracking_request_id=request_id,
            status="failed",
            product_id=bootstrap.product_id,
            listing_id=bootstrap.listing_id,
            watch_id=materialization.watch_id,
            error_code=DUPLICATE_WATCH_ERROR_CODE,
        )

    return Phase1IngestionResult(
        tracking_request_id=request_id,
        status="completed",
        product_id=materialization.product_id,
        listing_id=materialization.listing_id,
        watch_id=materialization.watch_id,
    )


def prepare_phase1_ingestion_requests(
    limit: int = 1,
) -> list[PreparedIngestionRequest]:
    """
    Claim pending tracking requests and validate their
    crawler targets.

    Valid requests are returned as prepared work items.

    Expected validation failures are persisted as failed
    tracking requests and are not returned.

    This function intentionally performs no scraping and
    no catalog writes.
    """

    claimed_requests = (
        claim_phase1_tracking_requests(
            limit
        )
    )

    prepared: list[
        PreparedIngestionRequest
    ] = []

    for request in claimed_requests:
        try:
            target = (
                validate_tracking_request_target(
                    request
                )
            )
        except ValueError as exc:
            mark_phase1_tracking_request_failed(
                request,
                error_code=(
                    INVALID_TARGET_ERROR_CODE
                ),
                error_message=str(exc),
            )

            continue

        prepared.append(
            PreparedIngestionRequest(
                request=request,
                target=target,
            )
        )

    return prepared


def process_phase1_ingestion_requests(
    limit: int = 1,
) -> list[Phase1IngestionResult]:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit != 1
    ):
        raise ValueError(
            "The high-level ingestion processor supports exactly one "
            "request per invocation until processing leases can be "
            "reclaimed safely."
        )

    prepared_requests = (
        prepare_phase1_ingestion_requests(
            1
        )
    )

    return [
        process_phase1_ingestion_request(
            prepared
        )
        for prepared in prepared_requests
    ]
