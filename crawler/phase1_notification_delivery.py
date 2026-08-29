from dataclasses import dataclass

from crawler.phase1_delivery_database import (
    claim_phase1_delivery,
    mark_phase1_delivery_failed,
    mark_phase1_delivery_sent,
)
from crawler.phase1_email import (
    send_phase1_email,
)


@dataclass
class Phase1EmailDeliveryResult:
    status: str

    attempted: bool
    complete: bool

    delivery: dict | None
    provider_message_id: str | None

    reason: str


def deliver_phase1_notification_email(
    notification: dict,
    notification_preferences: dict | None,
) -> Phase1EmailDeliveryResult:
    """
    Deliver one persisted Phase 1 notification by email.

    Responsibilities:
      1. Respect user email preferences.
      2. Claim the delivery lease.
      3. Send through Resend.
      4. Persist sent/failed delivery state.

    This function assumes that the logical notification has
    already been created in the notifications table.
    """

    notification_id = str(
        notification.get("id")
        or ""
    ).strip()

    if not notification_id:
        raise RuntimeError(
            "Phase 1 notification is missing its id."
        )

    preferences = (
        notification_preferences
        or {}
    )

    email_enabled = (
        preferences.get("email_enabled")
        is True
    )

    if not email_enabled:
        return Phase1EmailDeliveryResult(
            status="disabled",
            attempted=False,
            complete=True,
            delivery=None,
            provider_message_id=None,
            reason="Email notifications are disabled.",
        )

    recipient = str(
        preferences.get("email_address")
        or ""
    ).strip()

    if not recipient:
        raise RuntimeError(
            "Phase 1 email notifications are enabled "
            "but no email_address is configured."
        )

    delivery, claimed = claim_phase1_delivery(
        notification_id,
        "email",
    )

    if not claimed:
        status = delivery.get("status")

        if status in (
            "sent",
            "delivered",
        ):
            return Phase1EmailDeliveryResult(
                status="already_complete",
                attempted=False,
                complete=True,
                delivery=delivery,
                provider_message_id=(
                    delivery.get(
                        "provider_message_id"
                    )
                ),
                reason=(
                    "Email delivery was already "
                    f"{status}."
                ),
            )

        if status == "pending":
            return Phase1EmailDeliveryResult(
                status="in_progress",
                attempted=False,
                complete=False,
                delivery=delivery,
                provider_message_id=None,
                reason=(
                    "Another worker currently owns "
                    "the email delivery lease."
                ),
            )

        raise RuntimeError(
            "Unclaimed Phase 1 email delivery has "
            f"unexpected status: {status!r}"
        )

    try:
        provider_result = send_phase1_email(
            notification,
            recipient,
        )

    except Exception as exc:
        try:
            mark_phase1_delivery_failed(
                delivery["id"],
                str(exc),
            )

        except Exception as state_exc:
            raise RuntimeError(
                "Phase 1 email provider failed and "
                "the delivery could not be marked failed."
            ) from state_exc

        raise

    provider_message_id = str(
        provider_result.get("id")
        or ""
    ).strip()

    if not provider_message_id:
        failure_reason = (
            "Resend returned no provider message id."
        )

        mark_phase1_delivery_failed(
            delivery["id"],
            failure_reason,
        )

        raise RuntimeError(
            failure_reason
        )

    sent_delivery = mark_phase1_delivery_sent(
        delivery["id"],
        provider_message_id,
    )

    return Phase1EmailDeliveryResult(
        status="sent",
        attempted=True,
        complete=True,
        delivery=sent_delivery,
        provider_message_id=provider_message_id,
        reason="Email delivery completed.",
    )
