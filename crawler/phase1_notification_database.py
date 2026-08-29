from crawler.database import get_supabase
from crawler.phase1_notification_builder import (
    Phase1NotificationDraft,
)


def get_notification_by_dedupe_key(
    dedupe_key: str,
) -> dict | None:
    """
    Return an existing Phase 1 notification for a dedupe key.
    """

    if not dedupe_key:
        raise RuntimeError(
            "Notification dedupe_key is required."
        )

    supabase = get_supabase()

    response = (
        supabase
        .table("notifications")
        .select(
            "id,"
            "user_id,"
            "watch_id,"
            "type,"
            "title,"
            "body,"
            "payload,"
            "dedupe_key,"
            "created_at"
        )
        .eq(
            "dedupe_key",
            dedupe_key,
        )
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def get_or_create_phase1_notification(
    draft: Phase1NotificationDraft,
) -> tuple[dict, bool]:
    """
    Return one persisted notification for the draft.

    Returns:
        (notification, created)

    created=True:
        this call inserted the notification.

    created=False:
        the same logical notification already existed.

    PostgreSQL's unique dedupe_key index is the final concurrency
    guard. If another worker wins an insert race, this function
    reads and returns that worker's row instead.
    """

    existing = get_notification_by_dedupe_key(
        draft.dedupe_key
    )

    if existing is not None:
        return existing, False

    payload = {
        "user_id": draft.user_id,
        "watch_id": draft.watch_id,
        "type": draft.event_type,
        "title": draft.title,
        "body": draft.body,
        "payload": draft.payload,
        "dedupe_key": draft.dedupe_key,
    }

    supabase = get_supabase()

    try:
        response = (
            supabase
            .table("notifications")
            .insert(payload)
            .execute()
        )

    except Exception:
        # A concurrent worker may have inserted the same
        # dedupe_key after our initial lookup.
        existing = get_notification_by_dedupe_key(
            draft.dedupe_key
        )

        if existing is not None:
            return existing, False

        # Not a dedupe race. Preserve the real database error.
        raise

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one inserted notification, "
            f"received {len(rows)}."
        )

    return rows[0], True
