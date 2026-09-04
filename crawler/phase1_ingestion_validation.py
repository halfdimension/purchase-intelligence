from dataclasses import dataclass
from urllib.parse import (
    SplitResult,
    urlsplit,
    urlunsplit,
)


NIKE_ROOT_HOST = "nike.in"
NIKE_ADAPTER_KEY = "nike"
NIKE_MERCHANT_SLUG = "nike-india"


@dataclass(frozen=True)
class ValidatedIngestionTarget:
    url: str
    hostname: str
    adapter_key: str
    merchant_slug: str


def _is_nike_india_hostname(
    hostname: str,
) -> bool:
    return (
        hostname == NIKE_ROOT_HOST
        or hostname.endswith(
            f".{NIKE_ROOT_HOST}"
        )
    )


def validate_tracking_request_target(
    request: dict,
) -> ValidatedIngestionTarget:
    """
    Revalidate and renormalize a claimed user-submitted URL
    before any crawler network access.

    This is the authoritative worker-side trust boundary.

    Browser/API validation is intentionally not trusted here.
    """

    if not isinstance(request, dict):
        raise ValueError(
            "Tracking request must be a dictionary."
        )

    requested_url = request.get(
        "requested_url"
    )

    if (
        not isinstance(requested_url, str)
        or not requested_url.strip()
    ):
        raise ValueError(
            "Tracking request is missing requested_url."
        )

    requested_url = requested_url.strip()

    try:
        parsed = urlsplit(
            requested_url
        )
    except ValueError as exc:
        raise ValueError(
            "Tracking request URL is invalid."
        ) from exc

    scheme = parsed.scheme.lower()

    if scheme not in (
        "http",
        "https",
    ):
        raise ValueError(
            "Only HTTP and HTTPS ingestion URLs "
            "are supported."
        )

    if (
        parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            "Ingestion URLs containing credentials "
            "are not supported."
        )

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Tracking request URL contains "
            "an invalid port."
        ) from exc

    if explicit_port is not None:
        raise ValueError(
            "Ingestion URLs with explicit ports "
            "are not supported."
        )

    hostname = parsed.hostname

    if not hostname:
        raise ValueError(
            "Tracking request URL is missing "
            "a hostname."
        )

    hostname = hostname.lower()

    if (
        "%" in hostname
        or not hostname.isascii()
        or hostname.startswith(".")
        or hostname.endswith(".")
        or ".." in hostname
    ):
        raise ValueError(
            "Tracking request URL contains "
            "an invalid hostname."
        )

    labels = hostname.split(".")

    for label in labels:
        if (
            not label
            or label.startswith("-")
            or label.endswith("-")
            or not all(
                character.isalnum()
                or character == "-"
                for character in label
            )
        ):
            raise ValueError(
                "Tracking request URL contains "
                "an invalid hostname."
            )

    if not _is_nike_india_hostname(
        hostname
    ):
        raise ValueError(
            "Tracking request merchant is not "
            "supported for ingestion."
        )

    normalized = SplitResult(
        scheme=scheme,
        netloc=hostname,
        path=parsed.path or "/",
        query=parsed.query,
        fragment="",
    )

    normalized_url = urlunsplit(
        normalized
    )

    return ValidatedIngestionTarget(
        url=normalized_url,
        hostname=hostname,
        adapter_key=NIKE_ADAPTER_KEY,
        merchant_slug=NIKE_MERCHANT_SLUG,
    )
