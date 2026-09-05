from dataclasses import dataclass

from crawler.models import ProductData
from crawler.phase1_ingestion_contract import (
    CatalogBootstrapRequest,
)
from crawler.phase1_ingestion_database import (
    claim_phase1_tracking_requests,
    mark_phase1_tracking_request_failed,
)
from crawler.phase1_ingestion_payload import (
    build_nike_catalog_product_payload,
)
from crawler.phase1_ingestion_validation import (
    NIKE_ADAPTER_KEY,
    ValidatedIngestionTarget,
    validate_tracking_request_target,
)


INVALID_TARGET_ERROR_CODE = (
    "invalid_ingestion_target"
)


@dataclass(frozen=True)
class PreparedIngestionRequest:
    request: dict
    target: ValidatedIngestionTarget


NIKE_BRAND_SLUG = "nike"


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

    if (
        prepared.target.adapter_key
        != NIKE_ADAPTER_KEY
    ):
        raise ValueError(
            "Unsupported catalog bootstrap adapter."
        )

    if (
        not isinstance(product.brand, str)
        or product.brand.strip().lower()
        != NIKE_BRAND_SLUG
    ):
        raise ValueError(
            "Nike ingestion returned an unexpected brand."
        )

    product_payload = (
        build_nike_catalog_product_payload(
            product,
            normalized_url=(
                prepared.target.url
            ),
        )
    )

    bootstrap_request = CatalogBootstrapRequest(
        merchant_slug=(
            prepared.target.merchant_slug
        ),
        adapter_key=(
            prepared.target.adapter_key
        ),
        brand_slug=NIKE_BRAND_SLUG,
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
