from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

from crawler.models import ProductData


ENV_FILE = (
    Path(__file__).resolve().parent.parent
    / "apps"
    / "web"
    / ".env.local"
)

load_dotenv(ENV_FILE)


def get_supabase() -> Client:
    import os

    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")

    if not url:
        raise RuntimeError("SUPABASE_URL is not configured.")

    if not secret_key:
        raise RuntimeError("SUPABASE_SECRET_KEY is not configured.")

    return create_client(
        url,
        secret_key,
    )


def save_product(
    product: ProductData,
) -> dict:
    supabase = get_supabase()

    checked_at = datetime.now(
        timezone.utc
    ).isoformat()

    product_payload = {
        "url": product.url,
        "brand": product.brand or "Other",
        "name": product.name,
        "currency": product.currency,
        "mrp": product.mrp,
        "current_price": product.current_price,
        "image_url": product.image_url,
        "in_stock": product.in_stock,
        "last_checked_at": checked_at,
        "updated_at": checked_at,
    }

    product_response = (
        supabase
        .table("products")
        .upsert(
            product_payload,
            on_conflict="url",
        )
        .execute()
    )

    if not product_response.data:
        raise RuntimeError(
            "Supabase did not return the saved product."
        )

    saved_product = product_response.data[0]
    product_id = saved_product["id"]

    snapshot_payload = {
        "product_id": product_id,
        "mrp": product.mrp,
        "selling_price": product.current_price,
        "currency": product.currency or "INR",
        "in_stock": product.in_stock,
        "checked_at": checked_at,
    }

    (
        supabase
        .table("price_snapshots")
        .insert(snapshot_payload)
        .execute()
    )

    for variant in product.variants:
        variant_payload = {
            "product_id": product_id,
            "size": variant.size,
            "sku": variant.sku,
            "mrp": variant.mrp,
            "current_price": variant.current_price,
            "in_stock": variant.in_stock,
            "stock_remaining": variant.stock_remaining,
            "last_checked_at": checked_at,
        }

        (
            supabase
            .table("product_variants")
            .upsert(
                variant_payload,
                on_conflict="product_id,size",
            )
            .execute()
        )

    return saved_product
