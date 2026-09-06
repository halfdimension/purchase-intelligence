from dataclasses import dataclass
import os


PHASE1_INGESTION_LEASE_SECONDS_ENV = (
    "PHASE1_INGESTION_LEASE_SECONDS"
)

DEFAULT_PHASE1_INGESTION_LEASE_SECONDS = 600
MIN_PHASE1_INGESTION_LEASE_SECONDS = 300
MAX_PHASE1_INGESTION_LEASE_SECONDS = 1200


def validate_phase1_ingestion_lease_seconds(
    value: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
    ):
        raise ValueError(
            "Phase 1 ingestion lease duration must be an integer."
        )

    if (
        value
        < MIN_PHASE1_INGESTION_LEASE_SECONDS
        or value
        > MAX_PHASE1_INGESTION_LEASE_SECONDS
    ):
        raise ValueError(
            "Phase 1 ingestion lease duration must be between "
            f"{MIN_PHASE1_INGESTION_LEASE_SECONDS} and "
            f"{MAX_PHASE1_INGESTION_LEASE_SECONDS} seconds."
        )

    return value


def _read_integer_policy(
    environment_name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        environment_name
    )

    if raw_value is None:
        return default

    try:
        return int(raw_value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(
            f"{environment_name} must be an integer."
        ) from exc


@dataclass(frozen=True)
class Phase1IngestionPolicy:
    lease_duration_seconds: int = (
        DEFAULT_PHASE1_INGESTION_LEASE_SECONDS
    )

    def __post_init__(self) -> None:
        validate_phase1_ingestion_lease_seconds(
            self.lease_duration_seconds
        )


def load_phase1_ingestion_policy(
) -> Phase1IngestionPolicy:
    return Phase1IngestionPolicy(
        lease_duration_seconds=(
            _read_integer_policy(
                PHASE1_INGESTION_LEASE_SECONDS_ENV,
                DEFAULT_PHASE1_INGESTION_LEASE_SECONDS,
            )
        ),
    )
