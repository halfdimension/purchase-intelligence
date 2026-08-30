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
      data: profile,
      error: profileError,
    } = await supabase
      .from("profiles")
      .select(
        [
          "id",
          "email",
          "display_name",
          "avatar_url",
          "role",
          "created_at",
          "updated_at",
        ].join(","),
      )
      .eq("id", user.id)
      .single();

    if (profileError) {
      console.error(
        "Failed to load authenticated profile:",
        profileError,
      );

      return NextResponse.json(
        {
          error: "Failed to load profile.",
        },
        {
          status: 500,
        },
      );
    }

    return NextResponse.json({
      profile,
    });
  } catch (error) {
    console.error(
      "GET /api/profile/me failed:",
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
