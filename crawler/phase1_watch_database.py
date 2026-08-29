from crawler.database import get_supabase


def get_phase1_watches_for_listing(
    listing: dict,
) -> list[dict]:
    """
    Resolve active Phase 1 watch intents that apply to one
    merchant listing.

    Returned rows also include:
      - notification preferences
      - current watch evaluation state

    This function is read-only.
    """

    listing_id = listing.get("id")
    product_id = listing.get("product_id")

    if not listing_id:
        raise RuntimeError(
            "Phase 1 listing is missing its id."
        )

    if not product_id:
        raise RuntimeError(
            "Phase 1 listing is missing its product_id."
        )

    supabase = get_supabase()

    watch_response = (
        supabase
        .table("watch_intents")
        .select(
            "id,"
            "user_id,"
            "product_id,"
            "canonical_variant_id,"
            "tracking_scope,"
            "target_price,"
            "currency,"
            "variant_requirements,"
            "conditions,"
            "status"
        )
        .eq(
            "product_id",
            product_id,
        )
        .eq(
            "status",
            "active",
        )
        .execute()
    )

    watches = watch_response.data or []

    if not watches:
        return []

    explicit_watch_ids: list[str] = []

    for watch in watches:
        scope = watch.get("tracking_scope")

        if scope in (
            "specific_listing",
            "selected_listings",
        ):
            explicit_watch_ids.append(
                watch["id"]
            )

        elif scope != "any_listing":
            raise RuntimeError(
                "Unsupported Phase 1 tracking scope: "
                f"{scope!r}"
            )

    targeted_watch_ids: set[str] = set()

    if explicit_watch_ids:
        target_response = (
            supabase
            .table("watch_listing_targets")
            .select(
                "watch_id,"
                "listing_id"
            )
            .in_(
                "watch_id",
                explicit_watch_ids,
            )
            .eq(
                "listing_id",
                listing_id,
            )
            .execute()
        )

        targeted_watch_ids = {
            row["watch_id"]
            for row in target_response.data or []
        }

    applicable_watches: list[dict] = []

    for watch in watches:
        scope = watch["tracking_scope"]

        if (
            scope == "any_listing"
            or watch["id"] in targeted_watch_ids
        ):
            applicable_watches.append(
                watch
            )

    if not applicable_watches:
        return []

    watch_ids = [
        watch["id"]
        for watch in applicable_watches
    ]

    user_ids = list(
        {
            watch["user_id"]
            for watch in applicable_watches
        }
    )

    preference_response = (
        supabase
        .table("notification_preferences")
        .select(
            "user_id,"
            "email_enabled,"
            "email_address,"
            "push_enabled,"
            "telegram_enabled,"
            "whatsapp_enabled"
        )
        .in_(
            "user_id",
            user_ids,
        )
        .execute()
    )

    preferences_by_user = {
        row["user_id"]: row
        for row in preference_response.data or []
    }

    state_response = (
        supabase
        .table("watch_evaluation_state")
        .select(
            "watch_id,"
            "condition_met,"
            "last_reason,"
            "state,"
            "last_evaluated_at,"
            "last_notified_at,"
            "last_notified_effective_price"
        )
        .in_(
            "watch_id",
            watch_ids,
        )
        .execute()
    )

    states_by_watch = {
        row["watch_id"]: row
        for row in state_response.data or []
    }

    return [
        {
            "watch": watch,
            "notification_preferences": (
                preferences_by_user.get(
                    watch["user_id"]
                )
            ),
            "evaluation_state": (
                states_by_watch.get(
                    watch["id"]
                )
            ),
        }
        for watch in applicable_watches
    ]



def save_phase1_evaluation_state(
    evaluation,
    previous_state: dict | None = None,
    *,
    notification_completed: bool = False,
    notified_at: str | None = None,
) -> dict:
    """
    Persist the latest Phase 1 watch evaluation state.

    By default, existing notification metadata is left
    untouched.

    When notification_completed=True, the evaluation update and
    notification metadata are persisted in the same database
    write.

    This function does NOT create or deliver a notification.
    """

    from datetime import datetime, timezone

    watch_id = evaluation.watch_id

    if not watch_id:
        raise RuntimeError(
            "Phase 1 evaluation is missing its watch_id."
        )

    previous_details = {}

    if previous_state:
        previous_details = (
            previous_state.get("state")
            or {}
        )

    matched_variant_size = None

    if evaluation.matched_variant is not None:
        matched_variant_size = (
            evaluation.matched_variant.size
        )

    state = {
        **previous_details,
        "source": "phase1_evaluator",
        "variant_requirements": (
            evaluation.variant_requirements
        ),
        "matched_variant_size": (
            matched_variant_size
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
        "current_price": (
            evaluation.current_price
        ),
    }

    evaluated_at = datetime.now(
        timezone.utc
    ).isoformat()

    evaluation_payload = {
        "condition_met": evaluation.condition_met,
        "last_reason": evaluation.reason,
        "state": state,
        "last_evaluated_at": evaluated_at,
    }

    if notification_completed:
        completed_at = (
            notified_at
            or evaluated_at
        )

        evaluation_payload[
            "last_notified_at"
        ] = completed_at

        evaluation_payload[
            "last_notified_effective_price"
        ] = evaluation.current_price

    supabase = get_supabase()

    if previous_state is not None:
        response = (
            supabase
            .table("watch_evaluation_state")
            .update(
                evaluation_payload
            )
            .eq(
                "watch_id",
                watch_id,
            )
            .execute()
        )

    else:
        response = (
            supabase
            .table("watch_evaluation_state")
            .insert(
                {
                    "watch_id": watch_id,
                    **evaluation_payload,
                }
            )
            .execute()
        )

    rows = response.data or []

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one Phase 1 evaluation state "
            f"row, received {len(rows)}."
        )

    return rows[0]
