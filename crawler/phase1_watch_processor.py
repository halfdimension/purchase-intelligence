from dataclasses import dataclass

from crawler.models import ProductData
from crawler.phase1_evaluator import (
    Phase1WatchEvaluation,
    evaluate_phase1_watch,
)
from crawler.phase1_notification_builder import (
    build_phase1_notification_draft,
)
from crawler.phase1_notification_database import (
    get_or_create_phase1_notification,
)
from crawler.phase1_notification_delivery import (
    Phase1EmailDeliveryResult,
    deliver_phase1_notification_email,
)
from crawler.phase1_notification_policy import (
    Phase1NotificationDecision,
    decide_phase1_notification,
)
from crawler.phase1_watch_database import (
    save_phase1_evaluation_state,
)


@dataclass
class Phase1WatchProcessResult:
    evaluation: Phase1WatchEvaluation
    decision: Phase1NotificationDecision

    notification: dict | None
    notification_created: bool

    delivery: Phase1EmailDeliveryResult | None

    evaluation_state: dict | None
    state_persisted: bool


def process_phase1_watch(
    watch_context: dict,
    listing: dict,
    product: ProductData,
    *,
    notification_execution_enabled: bool = True,
) -> Phase1WatchProcessResult:
    """
    Process one Phase 1 watch against one freshly scraped
    merchant listing.

    Flow:

        evaluate
            ↓
        transition policy
            ↓
        optionally create/reuse notification
            ↓
        optionally deliver email
            ↓
        persist evaluation state

    Critical retry rule:

    If a required notification delivery is still in progress or
    fails, this function does NOT advance watch_evaluation_state.

    Keeping the previous false state unchanged means a retry
    produces the same false->true transition and therefore the
    same notification dedupe key.
    """

    watch = watch_context.get(
        "watch"
    )

    if not isinstance(
        watch,
        dict,
    ):
        raise RuntimeError(
            "Phase 1 watch context is missing its watch."
        )

    previous_state = watch_context.get(
        "evaluation_state"
    )

    notification_preferences = (
        watch_context.get(
            "notification_preferences"
        )
    )

    evaluation = evaluate_phase1_watch(
        watch,
        product,
    )

    decision = decide_phase1_notification(
        watch,
        evaluation,
        previous_state,
    )

    # --------------------------------------------------------
    # No logical notification is required for this transition.
    #
    # Examples:
    #   false -> false
    #   true  -> true
    #   true  -> false
    #   false -> true with watch notification policy disabled
    #
    # The latest evaluation can be safely persisted immediately.
    # --------------------------------------------------------

    if not decision.should_create_notification:
        saved_state = save_phase1_evaluation_state(
            evaluation,
            previous_state,
        )

        return Phase1WatchProcessResult(
            evaluation=evaluation,
            decision=decision,
            notification=None,
            notification_created=False,
            delivery=None,
            evaluation_state=saved_state,
            state_persisted=True,
        )

    # --------------------------------------------------------
    # false -> true notification path.
    #
    # During runtime shadow integration, Phase 0 remains the
    # authoritative notification system. In that mode we must
    # not create/deliver a Phase 1 notification and must not
    # advance the Phase 1 state to true.
    #
    # Leaving the previous false state unchanged preserves the
    # legitimate false->true transition for the eventual Phase 1
    # notification cutover.
    # --------------------------------------------------------

    if not notification_execution_enabled:
        return Phase1WatchProcessResult(
            evaluation=evaluation,
            decision=decision,
            notification=None,
            notification_created=False,
            delivery=None,
            evaluation_state=None,
            state_persisted=False,
        )

    draft = build_phase1_notification_draft(
        watch,
        listing,
        product,
        evaluation,
        decision,
        previous_state,
    )

    notification, notification_created = (
        get_or_create_phase1_notification(
            draft
        )
    )

    delivery = (
        deliver_phase1_notification_email(
            notification,
            notification_preferences,
        )
    )

    # --------------------------------------------------------
    # Another worker currently owns the delivery lease.
    #
    # Do NOT persist the new true evaluation yet.
    #
    # The worker that successfully completes delivery should
    # advance the watch state.
    # --------------------------------------------------------

    if not delivery.complete:
        return Phase1WatchProcessResult(
            evaluation=evaluation,
            decision=decision,
            notification=notification,
            notification_created=(
                notification_created
            ),
            delivery=delivery,
            evaluation_state=None,
            state_persisted=False,
        )

    # --------------------------------------------------------
    # Notification processing is complete.
    #
    # Prefer the delivery timestamp when a delivery row exists.
    # For a channel-disabled notification, fall back to the
    # logical notification creation time.
    #
    # save_phase1_evaluation_state() writes the evaluation and
    # notification metadata together.
    # --------------------------------------------------------

    notified_at = notification.get(
        "created_at"
    )

    if delivery.delivery is not None:
        notified_at = (
            delivery.delivery.get(
                "delivered_at"
            )
            or delivery.delivery.get(
                "attempted_at"
            )
            or notified_at
        )

    saved_state = save_phase1_evaluation_state(
        evaluation,
        previous_state,
        notification_completed=True,
        notified_at=notified_at,
    )

    return Phase1WatchProcessResult(
        evaluation=evaluation,
        decision=decision,
        notification=notification,
        notification_created=(
            notification_created
        ),
        delivery=delivery,
        evaluation_state=saved_state,
        state_persisted=True,
    )
