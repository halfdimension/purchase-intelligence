from datetime import datetime, timezone

from crawler.database import get_supabase


MIN_CLAIM_LIMIT = 1
MAX_CLAIM_LIMIT = 50


def claim_phase1_tracking_requests(
    limit: int = 1,
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

    supabase = get_supabase()

    response = (
        supabase
        .rpc(
            "claim_tracking_requests",
            {
                "p_limit": limit,
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

    return rows


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
