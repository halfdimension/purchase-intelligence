import { NextResponse } from "next/server";

import {
  createSupabaseServerClient,
} from "@/lib/supabase-auth-server";

export async function POST() {
  try {
    const supabase =
      await createSupabaseServerClient();

    const { error } =
      await supabase.auth.signOut();

    if (error) {
      console.error(
        "Supabase logout failed:",
        error,
      );

      return NextResponse.json(
        {
          error: "Failed to log out.",
        },
        {
          status: 500,
        },
      );
    }

    return NextResponse.json({
      authenticated: false,
    });
  } catch (error) {
    console.error(
      "POST /api/auth/logout failed:",
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
