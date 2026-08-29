from datetime import datetime, timedelta, timezone

from crawler.database import get_supabase


VALID_CHANNELS = {
    "email",
    "push",
    "telegram",
    "whatsapp",
}

PENDING_LEASE_TIMEOUT = timedelta(
    minutes=15
)


def get_phase1_delivery(
    notification_id: str,
    channel: str,
) -> dict | None:
    if not notification_id:
        raise RuntimeError(
            "notification_id is required."
        )

    if channel not in VALID_CHANNELS:
        raise RuntimeError(
            f"Unsupported notification channel: {channel!r}"
        )

    supabase = get_supabase()

    response = (
        supabase
        .table("notification_deliveries")
        .select(
            "id,"
            "notification_id,"
            "channel,"
            "status,"
            "provider_message_id,"
            "attempted_at,"
            "delivered_at,"
            "failure_reason,"
            "created_at"
        )
        .eq(
            "notification_id",
            notification_id,
        )
        .eq(
            "channel",
            channel,
        )
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def parse_timestamp(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    parsed = datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def pending_delivery_is_stale(
    delivery: dict,
    now: datetime,
) -> bool:
    attempted_at = parse_timestamp(
        delivery.get("attempted_at")
    )

    if attempted_at is None:
        return True

    return (
        now - attempted_at
        >= PENDING_LEASE_TIMEOUT
    )


def claim_phase1_delivery(
    notification_id: str,
    channel: str,
) -> tuple[dict, bool]:
    """
    Claim one provider delivery attempt.

    Returns:
        (delivery, claimed)

    A fresh pending row acts as a lease and cannot be claimed by
    another worker.

    A stale pending row or a failed row can be atomically
    reclaimed.

    sent/delivered rows are final for this notification/channel.
    """

    if not notification_id:
        raise RuntimeError(
            "notification_id is required."
        )

    if channel not in VALID_CHANNELS:
        raise RuntimeError(
            f"Unsupported notification channel: {channel!r}"
        )

    existing = get_phase1_delivery(
        notification_id,
        channel,
    )

    now_dt = datetime.now(
        timezone.utc
    )

    now = now_dt.isoformat()

    supabase = get_supabase()

    if existing is None:
        payload = {
            "notification_id": notification_id,
            "channel": channel,
            "status": "pending",
            "attempted_at": now,
        }

        try:
            response = (
                supabase
                .table("notification_deliveries")
                .insert(payload)
                .execute()
            )

        except Exception:
            winner = get_phase1_delivery(
                notification_id,
                channel,
            )

            if winner is not None:
                return winner, False

            raise

        rows = response.data or []

        if len(rows) != 1:
            raise RuntimeError(
                "Expected exactly one inserted delivery, "
                f"received {len(rows)}."
            )

        return rows[0], True

    status = existing.get("status")

    if status in (
        "sent",
        "delivered",
    ):
        return existing, False

    if status == "pending":
        if not pending_delivery_is_stale(
            existing,
            now_dt,
        ):
            return existing, False

        old_attempted_at = existing.get(
            "attempted_at"
        )

        query = (
            supabase
            .table("notification_deliveries")
            .update(
                {
                    "attempted_at": now,
                    "failure_reason": None,
                    "provider_message_id": None,
                    "delivered_at": None,
                }
            )
            .eq(
                "id",
                existing["id"],
            )
            .eq(
                "status",
                "pending",
            )
        )

        if old_attempted_at is None:
            query = query.is_(
                "attempted_at",
                "null",
            )
        else:
            query = query.eq(
                "attempted_at",
                old_attempted_at,
            )

        response = query.execute()

        rows = response.data or []

        if len(rows) == 1:
            return rows[0], True

        if len(rows) == 0:
            winner = get_phase1_delivery(
                notification_id,
                channel,
            )

            if winner is None:
                raise RuntimeError(
                    "Delivery disappeared during "
                    "stale-pending claim."
                )

            return winner, False

        raise RuntimeError(
            "Expected at most one stale pending claim, "
            f"received {len(rows)}."
        )

    if status != "failed":
        raise RuntimeError(
            "Unexpected Phase 1 delivery status: "
            f"{status!r}"
        )

    response = (
        supabase
        .table("notification_deliveries")
        .update(
            {
                "status": "pending",
                "attempted_at": now,
                "failure_reason": None,
                "provider_message_id": None,
                "delivered_at": None,
            }
        )
        .eq(
            "id",
            existing["id"],
        )
        .eq(
            "status",
            "failed",
        )
        .execute()
    )

    rows = response.data or []

    if len(rows) == 1:
        return rows[0], True

    if len(rows) == 0:
        winner = get_phase1_delivery(
            notification_id,
            channel,
        )

        if winner is None:
            raise RuntimeError(
                "Delivery disappeared during retry claim."
            )

        return winner, False

    raise RuntimeError(
        "Expected at most one delivery retry claim, "
        f"received {len(rows)}."
    )


def mark_phase1_delivery_sent(
    delivery_id: str,
    provider_message_id: str,
) -> dict:
    if not delivery_id:
        raise RuntimeError(
            "delivery_id is required."
        )

    if not provider_message_id:
        raise RuntimeError(
            "provider_message_id is required."
        )

    supabase = get_supabase()

    response = (
        supabase
        .table("notification_deliveries")
        .update(
            {
                "status": "sent",
                "provider_message_id": (
                    provider_message_id
                ),
                "failure_reason": None,
            }
        )
        .eq(
            "id",
            delivery_id,
        )
        .eq(
            "status",
            "pending",
        )
        .execute()
    )

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one pending delivery "
            "to become sent."
        )

    return rows[0]


def mark_phase1_delivery_failed(
    delivery_id: str,
    failure_reason: str,
) -> dict:
    if not delivery_id:
        raise RuntimeError(
            "delivery_id is required."
        )

    failure_reason = failure_reason.strip()

    if not failure_reason:
        raise RuntimeError(
            "failure_reason is required."
        )

    supabase = get_supabase()

    response = (
        supabase
        .table("notification_deliveries")
        .update(
            {
                "status": "failed",
                "failure_reason": failure_reason,
            }
        )
        .eq(
            "id",
            delivery_id,
        )
        .eq(
            "status",
            "pending",
        )
        .execute()
    )

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one pending delivery "
            "to become failed."
        )

    return rows[0]
