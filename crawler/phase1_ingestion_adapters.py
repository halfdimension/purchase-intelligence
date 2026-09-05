from dataclasses import dataclass
from typing import Callable

from crawler.models import ProductData
from crawler.phase1_database import (
    size_variant_key,
)
from crawler.phase1_ingestion_payload import (
    build_nike_catalog_product_payload,
)
from crawler.phase1_ingestion_validation import (
    NIKE_ADAPTER_KEY,
)
from crawler.scrapers.nike import NikeScraper
from crawler.scrapers.nike_url import (
    nike_india_product_id,
)


ProductPayloadBuilder = Callable[
    [ProductData, str],
    dict,
]
VariantKeyBuilder = Callable[[dict], str | None]
TargetUrlValidator = Callable[[str], None]
ScrapedProductValidator = Callable[
    [str, ProductData],
    None,
]


@dataclass(frozen=True)
class Phase1IngestionAdapter:
    key: str
    brand_slug: str
    scrape: Callable[[str], ProductData]
    build_product_payload: ProductPayloadBuilder
    requested_variant_key: VariantKeyBuilder
    validate_target_url: TargetUrlValidator
    validate_scraped_product: ScrapedProductValidator


def _validate_nike_target_url(
    url: str,
) -> None:
    nike_india_product_id(url)


def _validate_nike_scraped_product(
    target_url: str,
    product: ProductData,
) -> None:
    if not isinstance(product, ProductData):
        raise ValueError(
            "Nike scraper returned invalid product data."
        )

    target_product_id = nike_india_product_id(
        target_url
    )

    if (
        not isinstance(product.url, str)
        or not product.url.strip()
    ):
        raise ValueError(
            "Nike scrape did not return a final product URL."
        )

    try:
        final_product_id = nike_india_product_id(
            product.url
        )
    except ValueError as exc:
        raise ValueError(
            "Nike scrape final URL is not a supported Nike India "
            "product URL."
        ) from exc

    if final_product_id != target_product_id:
        raise ValueError(
            "Nike scrape redirected to a different product identity."
        )


def _build_nike_product_payload(
    product: ProductData,
    normalized_url: str,
) -> dict:
    _validate_nike_scraped_product(
        normalized_url,
        product,
    )

    if (
        not isinstance(product.brand, str)
        or product.brand.strip().lower()
        != "nike"
    ):
        raise ValueError(
            "Nike ingestion returned an unexpected brand."
        )

    return build_nike_catalog_product_payload(
        product,
        normalized_url=normalized_url,
    )


def _nike_requested_variant_key(
    variant_requirements: dict,
) -> str | None:
    if not variant_requirements:
        return None

    if set(variant_requirements) != {"size"}:
        raise ValueError(
            "Nike ingestion supports only a size variant requirement."
        )

    requested_size = variant_requirements.get(
        "size"
    )

    if (
        not isinstance(requested_size, str)
        or not requested_size.strip()
    ):
        raise ValueError(
            "Nike ingestion requires a non-empty size value."
        )

    return size_variant_key(
        requested_size
    )


def _scrape_nike(url: str) -> ProductData:
    return NikeScraper(
        guard_main_frame_navigations=True
    ).scrape(url)


NIKE_INGESTION_ADAPTER = (
    Phase1IngestionAdapter(
        key=NIKE_ADAPTER_KEY,
        brand_slug="nike",
        scrape=_scrape_nike,
        build_product_payload=(
            _build_nike_product_payload
        ),
        requested_variant_key=(
            _nike_requested_variant_key
        ),
        validate_target_url=(
            _validate_nike_target_url
        ),
        validate_scraped_product=(
            _validate_nike_scraped_product
        ),
    )
)


INGESTION_ADAPTERS = {
    NIKE_INGESTION_ADAPTER.key:
        NIKE_INGESTION_ADAPTER,
}


def get_phase1_ingestion_adapter(
    adapter_key: str,
) -> Phase1IngestionAdapter:
    adapter = INGESTION_ADAPTERS.get(
        adapter_key
    )

    if adapter is None:
        raise ValueError(
            "Unsupported ingestion adapter: "
            f"{adapter_key!r}."
        )

    return adapter
