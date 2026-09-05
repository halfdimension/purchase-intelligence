import re
from urllib.parse import urlsplit


NIKE_INDIA_ROOT_HOST = "nike.in"

NIKE_PRODUCT_PATH_PATTERN = re.compile(
    r"/p/([A-Za-z0-9_-]+)(?:/)?$"
)


def is_nike_india_hostname(
    hostname: str,
) -> bool:
    hostname = hostname.lower()

    return (
        hostname == NIKE_INDIA_ROOT_HOST
        or hostname.endswith(
            f".{NIKE_INDIA_ROOT_HOST}"
        )
    )


def require_nike_india_hostname(
    url: str,
) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError(
            "Nike URL must be a non-empty string."
        )

    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise ValueError(
            "Nike URL is invalid."
        ) from exc

    if parsed.scheme.lower() not in (
        "http",
        "https",
    ):
        raise ValueError(
            "Nike URL must use HTTP or HTTPS."
        )

    if (
        parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            "Nike URLs containing credentials are not supported."
        )

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Nike URL contains an invalid port."
        ) from exc

    if explicit_port is not None:
        raise ValueError(
            "Nike URLs with explicit ports are not supported."
        )

    hostname = parsed.hostname

    if (
        not isinstance(hostname, str)
        or not is_nike_india_hostname(hostname)
    ):
        raise ValueError(
            "Nike URL must remain on the supported Nike India hostname."
        )

    return hostname.lower()


def nike_india_product_id(
    url: str,
) -> str:
    require_nike_india_hostname(url)

    path = urlsplit(url.strip()).path
    match = NIKE_PRODUCT_PATH_PATTERN.search(
        path
    )

    if match is None:
        raise ValueError(
            "Nike ingestion requires a product URL with a non-empty "
            "/p/<id> identity."
        )

    return match.group(1)
