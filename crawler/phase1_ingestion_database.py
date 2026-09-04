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
