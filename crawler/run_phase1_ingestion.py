import json
import logging

from crawler.phase1_ingestion_worker import (
    Phase1IngestionResult,
    process_phase1_ingestion_requests,
)


logger = logging.getLogger(__name__)

EVENT_NAME = "phase1_ingestion_runner"
SUCCESS_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "cancelled",
        "ownership_lost",
    }
)


def _write_outcome(
    *,
    tracking_request_id: str | None = None,
    status: str,
    product_id: str | None = None,
    listing_id: str | None = None,
    watch_id: str | None = None,
    error_code: str | None = None,
) -> None:
    print(
        json.dumps(
            {
                "event": EVENT_NAME,
                "tracking_request_id": tracking_request_id,
                "status": status,
                "product_id": product_id,
                "listing_id": listing_id,
                "watch_id": watch_id,
                "error_code": error_code,
            },
            sort_keys=True,
        )
    )


def _write_result(
    result: Phase1IngestionResult,
    *,
    error_code: str | None = None,
) -> None:
    _write_outcome(
        tracking_request_id=(
            result.tracking_request_id
        ),
        status=result.status,
        product_id=result.product_id,
        listing_id=result.listing_id,
        watch_id=result.watch_id,
        error_code=(
            result.error_code
            if error_code is None
            else error_code
        ),
    )


def main() -> int:
    try:
        results = (
            process_phase1_ingestion_requests(
                limit=1
            )
        )

        if not isinstance(results, list):
            logger.error(
                "Phase 1 ingestion worker returned an invalid result collection."
            )
            _write_outcome(
                status="runner_failed",
                error_code="invalid_result_collection",
            )
            return 1

        if len(results) > 1:
            logger.error(
                "Phase 1 ingestion worker violated the one-result invariant."
            )
            _write_outcome(
                status="runner_failed",
                error_code=(
                    "unexpected_result_cardinality"
                ),
            )
            return 1

        if not results:
            _write_outcome(status="no_work")
            return 0

        result = results[0]

        if not isinstance(
            result,
            Phase1IngestionResult,
        ):
            logger.error(
                "Phase 1 ingestion worker returned an invalid result."
            )
            _write_outcome(
                status="runner_failed",
                error_code="invalid_result",
            )
            return 1

        if result.status in SUCCESS_STATUSES:
            _write_result(result)
            return 0

        if result.status == "processing":
            _write_result(result)
            return 2

        logger.error(
            "Phase 1 ingestion worker returned an unknown status."
        )
        _write_outcome(
            tracking_request_id=(
                result.tracking_request_id
            ),
            status="runner_failed",
            product_id=result.product_id,
            listing_id=result.listing_id,
            watch_id=result.watch_id,
            error_code="unknown_result_status",
        )
        return 1
    except Exception:
        logger.exception(
            "Phase 1 ingestion runner failed unexpectedly."
        )
        _write_outcome(
            status="runner_failed",
            error_code="unexpected_exception",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
