from dataclasses import dataclass

from crawler.phase1_evaluator import (
    Phase1WatchEvaluation,
)


@dataclass
class Phase1NotificationDecision:
    should_create_notification: bool
    event_type: str | None

    previous_condition_met: bool
    current_condition_met: bool

    transition: str
    reason: str


def decide_phase1_notification(
    watch: dict,
    evaluation: Phase1WatchEvaluation,
    previous_state: dict | None,
) -> Phase1NotificationDecision:
    """
    Decide whether a Phase 1 notification event should be
    created for the current evaluation.

    Initial cutover policy intentionally preserves Phase 0
    behavior:

        false -> true:
            create one notification

        true -> true:
            suppress duplicate notification

        false -> false:
            no notification

        true -> false:
            no notification; evaluator state will later be
            reset by the persistence layer

    More granular events such as standalone restock alerts or
    arbitrary price-drop alerts can be introduced later without
    changing this transition model.
    """

    if evaluation.watch_id != watch.get("id"):
        raise RuntimeError(
            "Evaluation watch_id does not match "
            "the supplied Phase 1 watch."
        )

    conditions = (
        watch.get("conditions")
        or {}
    )

    previous_condition_met = (
        previous_state is not None
        and previous_state.get(
            "condition_met"
        ) is True
    )

    current_condition_met = (
        evaluation.condition_met is True
    )

    notification_policy_enabled = (
        conditions.get(
            "notify_target_price",
            True,
        )
        is True
        or conditions.get(
            "notify_restock",
            True,
        )
        is True
    )

    if (
        previous_condition_met
        and current_condition_met
    ):
        return Phase1NotificationDecision(
            should_create_notification=False,
            event_type=None,
            previous_condition_met=True,
            current_condition_met=True,
            transition="true->true",
            reason=(
                "Watch conditions remain satisfied; "
                "duplicate notification suppressed."
            ),
        )

    if (
        not previous_condition_met
        and current_condition_met
    ):
        if not notification_policy_enabled:
            return Phase1NotificationDecision(
                should_create_notification=False,
                event_type=None,
                previous_condition_met=False,
                current_condition_met=True,
                transition="false->true",
                reason=(
                    "Watch conditions became satisfied, "
                    "but notification policy is disabled."
                ),
            )

        return Phase1NotificationDecision(
            should_create_notification=True,
            event_type="watch_conditions_met",
            previous_condition_met=False,
            current_condition_met=True,
            transition="false->true",
            reason=(
                "Watch conditions transitioned from "
                "not satisfied to satisfied."
            ),
        )

    if (
        previous_condition_met
        and not current_condition_met
    ):
        return Phase1NotificationDecision(
            should_create_notification=False,
            event_type=None,
            previous_condition_met=True,
            current_condition_met=False,
            transition="true->false",
            reason=(
                "Watch conditions are no longer satisfied."
            ),
        )

    return Phase1NotificationDecision(
        should_create_notification=False,
        event_type=None,
        previous_condition_met=False,
        current_condition_met=False,
        transition="false->false",
        reason=(
            "Watch conditions remain unsatisfied."
        ),
    )
