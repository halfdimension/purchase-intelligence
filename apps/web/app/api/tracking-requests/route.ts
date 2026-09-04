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
