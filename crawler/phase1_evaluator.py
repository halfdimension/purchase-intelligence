import re
from dataclasses import dataclass

from crawler.models import ProductData, ProductVariant


@dataclass
class Phase1WatchEvaluation:
    watch_id: str
    user_id: str

    target_price: float | None
    current_price: float | None

    variant_requirements: dict
    matched_variant: ProductVariant | None

    variant_available: bool | None
    price_target_reached: bool
    stock_requirement_met: bool

    condition_met: bool
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


def find_required_variant(
    product: ProductData,
    variant_requirements: dict,
) -> ProductVariant | None:
    if not variant_requirements:
        return None

    supported_keys = {"size"}

    unsupported_keys = (
        set(variant_requirements)
        - supported_keys
    )

    if unsupported_keys:
        raise RuntimeError(
            "Unsupported Phase 1 variant requirement(s): "
            + ", ".join(
                sorted(unsupported_keys)
            )
        )

    desired_size = variant_requirements.get(
        "size"
    )

    if not desired_size:
        return None

    wanted = normalize_size(
        str(desired_size)
    )

    for variant in product.variants:
        if normalize_size(variant.size) == wanted:
            return variant

    return None


def evaluate_phase1_watch(
    watch: dict,
    product: ProductData,
) -> Phase1WatchEvaluation:
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

    variant_requirements = (
        watch.get("variant_requirements")
        or {}
    )

    conditions = (
        watch.get("conditions")
        or {}
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

    matched_variant = find_required_variant(
        product,
        variant_requirements,
    )

    has_variant_requirement = bool(
        variant_requirements
    )

    if has_variant_requirement:
        variant_available = (
            matched_variant is not None
            and matched_variant.in_stock is True
        )
    else:
        variant_available = (
            product.in_stock is True
        )

    require_in_stock = (
        conditions.get(
            "require_in_stock",
            True,
        )
        is True
    )

    if require_in_stock:
        stock_requirement_met = (
            variant_available is True
        )
    else:
        stock_requirement_met = True

    condition_met = (
        price_target_reached
        and stock_requirement_met
    )

    desired_size = (
        variant_requirements.get("size")
    )

    if condition_met:
        if desired_size:
            reason = (
                "Target price reached and "
                f"{desired_size} is available."
            )
        else:
            reason = (
                "Target price reached and "
                "product is available."
            )

    elif (
        require_in_stock
        and not stock_requirement_met
    ):
        reason = (
            f"{desired_size or 'Product'} "
            "is currently out of stock."
        )

    elif not price_target_reached:
        if (
            current_price is not None
            and target_price is not None
        ):
            reason = (
                f"Current price ₹{current_price:,.0f} "
                f"is above target ₹{target_price:,.0f}."
            )
        else:
            reason = (
                "Current price is unavailable, so the "
                "target price cannot be evaluated."
            )

    else:
        reason = (
            "Watch conditions are not currently met."
        )

    return Phase1WatchEvaluation(
        watch_id=watch_id,
        user_id=user_id,
        target_price=target_price,
        current_price=current_price,
        variant_requirements=variant_requirements,
        matched_variant=matched_variant,
        variant_available=variant_available,
        price_target_reached=price_target_reached,
        stock_requirement_met=stock_requirement_met,
        condition_met=condition_met,
        reason=reason,
    )
