import { NextResponse } from "next/server";

import {
  createSupabaseServerClient,
} from "@/lib/supabase-auth-server";

export async function GET() {
  try {
    const supabase =
      await createSupabaseServerClient();

    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      return NextResponse.json(
        {
          error: "Unauthorized.",
        },
        {
          status: 401,
        },
      );
    }

    const {
      data: watches,
      error: watchesError,
    } = await supabase
      .from("watch_intents")
      .select(
        `
          id,
          user_id,
          product_id,
          canonical_variant_id,
          tracking_scope,
          target_price,
          currency,
          variant_requirements,
          conditions,
          status,
          created_at,
          updated_at,
          product:canonical_products (
            id,
            name,
            image_url,
            brand_id,
            category_id
          ),
          canonical_variant:canonical_variants (
            id,
            title,
            canonical_sku,
            attributes,
            variant_key,
            image_url
          ),
          listing_targets:watch_listing_targets (
            listing_id,
            created_at,
            listing:merchant_listings (
              id,
              url,
              title,
              image_url,
              seller_name,
              current_mrp,
              current_price,
              currency,
              in_stock,
              last_checked_at,
              variants:listing_variants (
                id,
                canonical_variant_id,
                external_sku,
                title,
                attributes,
                variant_key,
                current_mrp,
                current_price,
                currency,
                in_stock,
                stock_remaining,
                last_checked_at
              ),
              merchant:merchants (
                id,
                slug,
                name,
                base_url,
                adapter_key
              )
            )
          )
        `,
      )
      .eq("user_id", user.id)
      .order(
        "created_at",
        {
          ascending: false,
        },
      );

    if (watchesError) {
      console.error(
        "Failed to load authenticated watches:",
        watchesError,
      );

      return NextResponse.json(
        {
          error: "Failed to load watches.",
        },
        {
          status: 500,
        },
      );
    }

    return NextResponse.json({
      watches,
    });
  } catch (error) {
    console.error(
      "GET /api/watch-intents failed:",
      error,
    );

    return NextResponse.json(
      {
        error: "Internal server error.",
      },
      {
        status: 500,
      },
    );
  }
}
