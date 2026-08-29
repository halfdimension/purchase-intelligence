import hashlib
import json
from dataclasses import dataclass

from crawler.models import ProductData
from crawler.phase1_evaluator import (
    Phase1WatchEvaluation,
)
from crawler.phase1_notification_policy import (
    Phase1NotificationDecision,
)


@dataclass
class Phase1NotificationDraft:
    user_id: str
    watch_id: str

    event_type: str
    title: str
    body: str

    payload: dict
    dedupe_key: str


def build_phase1_notification_draft(
    watch: dict,
    listing: dict,
    product: ProductData,
    evaluation: Phase1WatchEvaluation,
    decision: Phase1NotificationDecision,
    previous_state: dict | None,
) -> Phase1NotificationDraft:
    """
    Build a notification record without writing anything.

    The dedupe key is anchored to the previous unsatisfied
    evaluation state. Retries of the same false->true transition
    therefore produce the same key.
    """

    watch_id = watch.get("id")
    user_id = watch.get("user_id")

    if not watch_id:
        raise RuntimeError(
            "Phase 1 watch is missing its id."
        )

    if not user_id:
        raise RuntimeError(
            "Phase 1 watch is missing its user_id."
        )

    if evaluation.watch_id != watch_id:
        raise RuntimeError(
            "Evaluation watch_id does not match watch."
        )

    if evaluation.user_id != user_id:
        raise RuntimeError(
            "Evaluation user_id does not match watch."
        )

    if not decision.should_create_notification:
        raise RuntimeError(
            "Notification draft requested for a decision "
            "that does not require a notification."
        )

    if not decision.event_type:
        raise RuntimeError(
            "Notification decision is missing event_type."
        )

    if decision.transition != "false->true":
        raise RuntimeError(
            "Initial Phase 1 notification creation only "
            "supports false->true transitions."
        )

    listing_id = listing.get("id")
    product_id = listing.get("product_id")
    product_url = listing.get("url")

    if not listing_id:
        raise RuntimeError(
            "Phase 1 listing is missing its id."
        )

    if not product_id:
        raise RuntimeError(
            "Phase 1 listing is missing its product_id."
        )

    if not product_url:
        raise RuntimeError(
            "Phase 1 listing is missing its URL."
        )

    transition_anchor = "initial"

    if previous_state is not None:
        transition_anchor = (
            previous_state.get("last_evaluated_at")
            or "existing-state-without-time"
        )

    dedupe_source = {
        "watch_id": watch_id,
        "event_type": decision.event_type,
        "transition": decision.transition,
        "transition_anchor": transition_anchor,
    }

    dedupe_digest = hashlib.sha256(
        json.dumps(
            dedupe_source,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    dedupe_key = (
        f"phase1:{decision.event_type}:"
        f"{dedupe_digest}"
    )

    product_name = (
        product.name
        or "Tracked product"
    )

    currency = (
        watch.get("currency")
        or product.currency
        or "INR"
    )

    payload = {
        "listing_id": listing_id,
        "product_id": product_id,
        "product_name": product_name,
        "product_url": product_url,
        "currency": currency,
        "target_price": evaluation.target_price,
        "current_price": evaluation.current_price,
        "variant_requirements": (
            evaluation.variant_requirements
        ),
        "variant_available": (
            evaluation.variant_available
        ),
        "price_target_reached": (
            evaluation.price_target_reached
        ),
        "stock_requirement_met": (
            evaluation.stock_requirement_met
        ),
        "transition": decision.transition,
        "evaluation_reason": evaluation.reason,
    }

    title = f"Buy alert: {product_name}"

    body = evaluation.reason

    return Phase1NotificationDraft(
        user_id=user_id,
        watch_id=watch_id,
        event_type=decision.event_type,
        title=title,
        body=body,
        payload=payload,
        dedupe_key=dedupe_key,
    )
