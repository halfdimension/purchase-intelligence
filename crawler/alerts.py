import re
from dataclasses import dataclass

from crawler.models import ProductData, ProductVariant


@dataclass
class WatchEvaluation:
    email: str
    desired_size: str | None
    target_price: float | None

    current_price: float | None
    size_available: bool | None
    price_target_reached: bool | None

    should_alert: bool
    reason: str


def normalize_size(value: str) -> str:
    value = value.strip().upper()

    match = re.search(
        r"\bUK\s*([0-9]+(?:\.[0-9]+)?)",
        value,
    )

    if match:
        return f"UK {match.group(1)}"

    return " ".join(value.split())


def find_variant(
    product: ProductData,
    desired_size: str,
) -> ProductVariant | None:
    wanted = normalize_size(
        desired_size
    )

    for variant in product.variants:
        if normalize_size(variant.size) == wanted:
            return variant

    return None


def evaluate_watch(
    watch: dict,
    product: ProductData,
) -> WatchEvaluation:
    email = watch["email"]

    desired_size = watch.get(
        "desired_size"
    )

    raw_target = watch.get(
        "target_price"
    )

    target_price = (
        float(raw_target)
        if raw_target is not None
        else None
    )

    current_price = product.current_price

    if target_price is None:
        price_target_reached = True

    elif current_price is None:
        price_target_reached = False

    else:
        price_target_reached = (
            current_price <= target_price
        )

    size_available = None

    if desired_size:
        variant = find_variant(
            product,
            desired_size,
        )

        if variant is None:
            size_available = False
        else:
            size_available = (
                variant.in_stock is True
            )
    else:
        size_available = (
            product.in_stock is True
        )

    should_alert = (
        price_target_reached
        and size_available
    )

    if should_alert:
        reason = (
            "Target price reached and "
            "desired size is available."
        )

    elif not size_available:
        reason = (
            f"{desired_size or 'Product'} "
            "is currently out of stock."
        )

    elif not price_target_reached:
        reason = (
            f"Current price ₹{current_price:,.0f} "
            f"is above target ₹{target_price:,.0f}."
        )

    else:
        reason = (
            "Watch conditions are not currently met."
        )

    return WatchEvaluation(
        email=email,
        desired_size=desired_size,
        target_price=target_price,
        current_price=current_price,
        size_available=size_available,
        price_target_reached=price_target_reached,
        should_alert=should_alert,
        reason=reason,
    )
