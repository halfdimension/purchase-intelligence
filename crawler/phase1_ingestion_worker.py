from dataclasses import dataclass

from crawler.phase1_ingestion_database import (
    claim_phase1_tracking_requests,
    mark_phase1_tracking_request_failed,
)
from crawler.phase1_ingestion_validation import (
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
