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

function isSupportedHostname(hostname: string) {
  const normalized = hostname.toLowerCase();

  return (
    normalized === "nike.in" ||
    normalized.endsWith(".nike.in")
  );
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
      data: requests,
      error: requestsError,
    } = await supabase
      .from("tracking_requests")
      .select(
        `
          id,
          user_id,
          requested_url,
          normalized_url,
          variant_requirements,
          target_price,
          target_currency,
          conditions,
          status,
          attempt_count,
          result_product_id,
          result_listing_id,
          result_watch_id,
          error_code,
          error_message,
          created_at,
          updated_at,
          started_at,
          completed_at
        `,
      )
      .eq("user_id", user.id)
      .order(
        "created_at",
        {
          ascending: false,
        },
      );

    if (requestsError) {
      console.error(
        "Failed to load tracking requests:",
        requestsError,
      );

      return NextResponse.json(
        {
          error:
            "Failed to load tracking requests.",
        },
        {
          status: 500,
        },
      );
    }

    return NextResponse.json({
      requests,
    });
  } catch (error) {
    console.error(
      "GET /api/tracking-requests failed:",
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
      parsedUrl.username ||
      parsedUrl.password
    ) {
      return NextResponse.json(
        {
          error:
            "Product URLs containing credentials are not supported.",
        },
        {
          status: 400,
        },
      );
    }

    if (
      !isSupportedHostname(parsedUrl.hostname)
    ) {
      return NextResponse.json(
        {
          error:
            "This merchant is not supported for Phase 1 ingestion.",
        },
        {
          status: 422,
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
      data: existingListings,
      error: existingListingError,
    } = await supabase
      .from("merchant_listings")
      .select("id")
      .eq("url", normalizedUrl)
      .eq("active", true)
      .limit(1);

    if (existingListingError) {
      console.error(
        "Failed to check existing listing:",
        existingListingError,
      );

      return NextResponse.json(
        {
          error:
            "Failed to check product listing.",
        },
        {
          status: 500,
        },
      );
    }

    if (
      existingListings &&
      existingListings.length > 0
    ) {
      return NextResponse.json(
        {
          error:
            "This product is already indexed and does not need an ingestion request.",
        },
        {
          status: 409,
        },
      );
    }

    const variantRequirements =
      requestedSize
        ? {
            size: normalizeSize(
              requestedSize,
            ),
          }
        : {};

    const conditions = {
      require_in_stock: true,
      notify_target_price:
        targetPrice !== null,
      notify_restock: true,
    };

    const {
      data: trackingRequest,
      error: insertError,
    } = await supabase
      .from("tracking_requests")
      .insert({
        user_id: user.id,
        requested_url: productUrl,
        normalized_url: normalizedUrl,
        variant_requirements:
          variantRequirements,
        target_price: targetPrice,
        target_currency: "INR",
        conditions,
      })
      .select(
        `
          id,
          user_id,
          requested_url,
          normalized_url,
          variant_requirements,
          target_price,
          target_currency,
          conditions,
          status,
          attempt_count,
          result_product_id,
          result_listing_id,
          result_watch_id,
          error_code,
          error_message,
          created_at,
          updated_at,
          started_at,
          completed_at
        `,
      )
      .single();

    if (insertError || !trackingRequest) {
      console.error(
        "Failed to create tracking request:",
        insertError,
      );

      return NextResponse.json(
        {
          error:
            "Failed to create tracking request.",
        },
        {
          status: 500,
        },
      );
    }

    return NextResponse.json(
      {
        request: trackingRequest,
      },
      {
        status: 202,
      },
    );
  } catch (error) {
    console.error(
      "POST /api/tracking-requests failed:",
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
