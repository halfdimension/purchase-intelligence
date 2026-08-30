import { NextResponse } from "next/server";

import {
  createSupabaseServerClient,
} from "@/lib/supabase-auth-server";

function normalizeSize(value: string) {
  const normalized = value.trim().toUpperCase();

  const match = normalized.match(
    /UK\s*([0-9]+(?:\.[0-9]+)?)/,
  );

  if (match) {
    return `UK ${match[1]}`;
  }

  return normalized;
}

function stringAttribute(
  value: unknown,
  key: string,
) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value)
  ) {
    return null;
  }

  const attribute = (
    value as Record<string, unknown>
  )[key];

  return typeof attribute === "string"
    ? attribute
    : null;
}

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
          evaluation:watch_evaluation_state (
            condition_met,
            last_reason,
            state,
            last_evaluated_at,
            last_notified_at,
            last_notified_effective_price
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

export async function POST(request: Request) {
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

    const body = await request
      .json()
      .catch(() => null);

    if (
      !body ||
      typeof body !== "object" ||
      Array.isArray(body)
    ) {
      return NextResponse.json(
        {
          error: "Invalid request body.",
        },
        {
          status: 400,
        },
      );
    }

    const productUrl =
      typeof body.productUrl === "string"
        ? body.productUrl.trim()
        : "";

    const requestedSize =
      typeof body.size === "string" &&
      body.size.trim()
        ? body.size.trim()
        : null;

    const targetPrice =
      body.targetPrice !== undefined &&
      body.targetPrice !== null &&
      body.targetPrice !== ""
        ? Number(body.targetPrice)
        : null;

    if (!productUrl) {
      return NextResponse.json(
        {
          error: "Product URL is required.",
        },
        {
          status: 400,
        },
      );
    }

    let parsedUrl: URL;

    try {
      parsedUrl = new URL(productUrl);
    } catch {
      return NextResponse.json(
        {
          error: "Enter a valid product URL.",
        },
        {
          status: 400,
        },
      );
    }

    if (
      parsedUrl.protocol !== "http:" &&
      parsedUrl.protocol !== "https:"
    ) {
      return NextResponse.json(
        {
          error:
            "Only HTTP and HTTPS product URLs are supported.",
        },
        {
          status: 400,
        },
      );
    }

    if (
      targetPrice !== null &&
      (
        !Number.isFinite(targetPrice) ||
        targetPrice <= 0
      )
    ) {
      return NextResponse.json(
        {
          error:
            "Target price must be greater than 0.",
        },
        {
          status: 400,
        },
      );
    }

    parsedUrl.hash = "";

    const normalizedUrl =
      parsedUrl.toString();

    const {
      data: listings,
      error: listingError,
    } = await supabase
      .from("merchant_listings")
      .select(
        `
          id,
          product_id,
          currency,
          active,
          variants:listing_variants (
            id,
            canonical_variant_id,
            title,
            attributes,
            active
          )
        `,
      )
      .eq("url", normalizedUrl)
      .eq("active", true)
      .limit(2);

    if (listingError) {
      console.error(
        "Failed to resolve Phase 1 listing:",
        listingError,
      );

      return NextResponse.json(
        {
          error:
            "Failed to resolve product listing.",
        },
        {
          status: 500,
        },
      );
    }

    if (!listings || listings.length === 0) {
      return NextResponse.json(
        {
          error:
            "This product has not been indexed in the Phase 1 catalog yet.",
        },
        {
          status: 422,
        },
      );
    }

    if (listings.length !== 1) {
      console.error(
        "Multiple Phase 1 listings resolved for URL:",
        normalizedUrl,
      );

      return NextResponse.json(
        {
          error:
            "Product listing could not be resolved uniquely.",
        },
        {
          status: 500,
        },
      );
    }

    const listing = listings[0];

    let canonicalVariantId:
      | string
      | null = null;

    let normalizedRequestedSize:
      | string
      | null = null;

    if (requestedSize) {
      normalizedRequestedSize =
        normalizeSize(requestedSize);

      const listingVariant =
        (listing.variants ?? []).find(
          (variant) =>
            normalizeSize(
              stringAttribute(
                variant.attributes,
                "size",
              ) ??
                variant.title ??
                "",
            ) === normalizedRequestedSize,
        );

      if (!listingVariant) {
        return NextResponse.json(
          {
            error:
              `Size ${normalizedRequestedSize} is not available for this listing.`,
          },
          {
            status: 422,
          },
        );
      }

      if (
        !listingVariant.canonical_variant_id
      ) {
        return NextResponse.json(
          {
            error:
              "The requested listing variant is not linked to a canonical variant yet.",
          },
          {
            status: 422,
          },
        );
      }

      canonicalVariantId =
        listingVariant.canonical_variant_id;
    }

    const duplicateBaseQuery = supabase
      .from("watch_intents")
      .select("id")
      .eq("user_id", user.id)
      .eq("product_id", listing.product_id)
      .eq(
        "tracking_scope",
        "specific_listing",
      )
      .neq("status", "archived");

    const {
      data: duplicateCandidates,
      error: duplicateCandidateError,
    } = canonicalVariantId
      ? await duplicateBaseQuery.eq(
          "canonical_variant_id",
          canonicalVariantId,
        )
      : await duplicateBaseQuery.is(
          "canonical_variant_id",
          null,
        );

    if (duplicateCandidateError) {
      console.error(
        "Failed to check duplicate watches:",
        duplicateCandidateError,
      );

      return NextResponse.json(
        {
          error:
            "Failed to check existing watches.",
        },
        {
          status: 500,
        },
      );
    }

    if (
      duplicateCandidates &&
      duplicateCandidates.length > 0
    ) {
      const candidateIds =
        duplicateCandidates.map(
          (watch) => watch.id,
        );

      const {
        data: existingTargets,
        error: existingTargetError,
      } = await supabase
        .from("watch_listing_targets")
        .select("watch_id")
        .in("watch_id", candidateIds)
        .eq("listing_id", listing.id)
        .limit(1);

      if (existingTargetError) {
        console.error(
          "Failed to check existing targets:",
          existingTargetError,
        );

        return NextResponse.json(
          {
            error:
              "Failed to check existing watches.",
          },
          {
            status: 500,
          },
        );
      }

      if (
        existingTargets &&
        existingTargets.length > 0
      ) {
        return NextResponse.json(
          {
            error:
              "This product and variant are already being tracked.",
          },
          {
            status: 409,
          },
        );
      }
    }

    const variantRequirements =
      normalizedRequestedSize
        ? {
            size: normalizedRequestedSize,
          }
        : {};

    const conditions = {
      require_in_stock: true,
      notify_target_price:
        targetPrice !== null,
      notify_restock: true,
    };

    const {
      data: watch,
      error: watchError,
    } = await supabase
      .from("watch_intents")
      .insert({
        user_id: user.id,
        product_id: listing.product_id,
        canonical_variant_id:
          canonicalVariantId,
        tracking_scope:
          "specific_listing",
        target_price: targetPrice,
        currency:
          listing.currency ?? "INR",
        variant_requirements:
          variantRequirements,
        conditions,
        status: "active",
      })
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
          updated_at
        `,
      )
      .single();

    if (watchError || !watch) {
      console.error(
        "Failed to create Phase 1 watch:",
        watchError,
      );

      return NextResponse.json(
        {
          error:
            "Failed to create watch.",
        },
        {
          status: 500,
        },
      );
    }

    const {
      error: targetError,
    } = await supabase
      .from("watch_listing_targets")
      .insert({
        watch_id: watch.id,
        listing_id: listing.id,
      });

    if (targetError) {
      console.error(
        "Failed to create watch listing target:",
        targetError,
      );

      const {
        error: rollbackError,
      } = await supabase
        .from("watch_intents")
        .delete()
        .eq("id", watch.id);

      if (rollbackError) {
        console.error(
          "Failed to roll back watch:",
          rollbackError,
        );
      }

      return NextResponse.json(
        {
          error:
            "Failed to create watch target.",
        },
        {
          status: 500,
        },
      );
    }

    return NextResponse.json(
      {
        watch,
      },
      {
        status: 201,
      },
    );
  } catch (error) {
    console.error(
      "POST /api/watch-intents failed:",
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
