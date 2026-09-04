import re
from urllib.parse import urlsplit

from crawler.models import ProductData
from crawler.phase1_database import (
    normalize_size,
    size_variant_key,
)


def _require_product_name(
    product: ProductData,
) -> str:
    if not isinstance(product.name, str):
        raise ValueError(
            "Scraped product name is required "
            "for catalog bootstrap."
        )

    name = product.name.strip()

    if not name:
        raise ValueError(
            "Scraped product name must not be empty."
        )

    return name


def _nike_external_id(
    normalized_url: str,
) -> str | None:
    """
    Extract Nike's merchant-specific product identity.

    Example:
        /some-product/p/24932950
        -> 24932950

    The URL has already passed authoritative ingestion-target
    validation before this function is called.
    """

    path = urlsplit(
        normalized_url
    ).path

    match = re.search(
        r"/p/([^/?#]+)(?:/)?$",
        path,
    )

    if match is None:
        return None

    value = match.group(1).strip()

    return value or None


def build_nike_catalog_product_payload(
    product: ProductData,
    *,
    normalized_url: str,
) -> dict:
    """
    Convert Nike ProductData into the merchant-independent /
    merchant-specific normalized payload expected by the
    catalog-bootstrap RPC.

    Merchant parsing and size normalization stop here.
    PostgreSQL must consume these identities rather than
    reproduce Nike-specific normalization logic.
    """

    name = _require_product_name(
        product
    )

    currency = (
        product.currency.strip().upper()
        if isinstance(product.currency, str)
        and product.currency.strip()
        else "INR"
    )

    normalized_variants: list[dict] = []
    seen_variant_keys: set[str] = set()

    for variant in product.variants:
        if not isinstance(variant.size, str):
            raise ValueError(
                "Nike variant size must be a string."
            )

        merchant_size_label = (
            variant.size.strip()
        )

        if not merchant_size_label:
            raise ValueError(
                "Nike variant size must not be empty."
            )

        canonical_size = normalize_size(
            merchant_size_label
        )

        variant_key = size_variant_key(
            merchant_size_label
        )

        if variant_key in seen_variant_keys:
            raise ValueError(
                "Multiple Nike variants normalize to "
                f"the same variant_key {variant_key!r}."
            )

        seen_variant_keys.add(
            variant_key
        )

        normalized_variants.append(
            {
                "variant_key": variant_key,
                "canonical_title": (
                    canonical_size
                ),
                "canonical_attributes": {
                    "size": canonical_size,
                },
                "external_sku": variant.sku,
                "listing_title": (
                    merchant_size_label
                ),
                "listing_attributes": {
                    "size": canonical_size,
                    "merchant_size_label": (
                        merchant_size_label
                    ),
                },
                "mrp": variant.mrp,
                "current_price": (
                    variant.current_price
                ),
                "in_stock": variant.in_stock,
                "stock_remaining": (
                    variant.stock_remaining
                ),
            }
        )

    normalized_variants.sort(
        key=lambda item: item["variant_key"]
    )

    return {
        "name": name,
        "image_url": product.image_url,
        "external_id": _nike_external_id(
            normalized_url
        ),
        "mrp": product.mrp,
        "current_price": product.current_price,
        "currency": currency,
        "in_stock": product.in_stock,
        "variants": normalized_variants,
    }
