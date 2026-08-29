import os

from collections.abc import Mapping
from dataclasses import dataclass


NOTIFICATION_MODE_ENV = (
    "PURCHASE_INTELLIGENCE_NOTIFICATION_MODE"
)


@dataclass(frozen=True)
class NotificationRuntimeMode:
    name: str

    phase1_notification_execution_enabled: bool
    phase0_notification_execution_enabled: bool


def get_notification_runtime_mode(
    environ: Mapping[str, str] | None = None,
) -> NotificationRuntimeMode:
    """
    Resolve which notification implementation is authoritative.

    shadow:
        Phase 1 evaluates watches but cannot send notifications.
        Phase 0 remains authoritative.

    phase1:
        Phase 1 owns notification execution.
        Phase 0 notification execution must be disabled.

    The safe default is shadow.
    """

    source = (
        os.environ
        if environ is None
        else environ
    )

    mode = (
        source.get(
            NOTIFICATION_MODE_ENV,
            "shadow",
        )
        .strip()
        .lower()
    )

    if mode == "shadow":
        return NotificationRuntimeMode(
            name="shadow",
            phase1_notification_execution_enabled=False,
            phase0_notification_execution_enabled=True,
        )

    if mode == "phase1":
        return NotificationRuntimeMode(
            name="phase1",
            phase1_notification_execution_enabled=True,
            phase0_notification_execution_enabled=False,
        )

    raise RuntimeError(
        f"Invalid {NOTIFICATION_MODE_ENV}={mode!r}. "
        "Expected 'shadow' or 'phase1'."
    )
