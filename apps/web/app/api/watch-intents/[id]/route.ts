import { NextResponse } from "next/server";

import {
  createSupabaseServerClient,
} from "@/lib/supabase-auth-server";

export async function DELETE(
  _request: Request,
  context: {
    params: Promise<{ id: string }>;
  },
) {
  try {
    const { id } = await context.params;

    if (!id) {
      return NextResponse.json(
        {
          error: "Watch ID is required.",
        },
        {
          status: 400,
        },
      );
    }

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
      data: deletedWatch,
      error: deleteError,
    } = await supabase
      .from("watch_intents")
      .delete()
      .eq("id", id)
      .eq("user_id", user.id)
      .select("id")
      .maybeSingle();

    if (deleteError) {
      console.error(
        "Failed to delete Phase 1 watch:",
        deleteError,
      );

      return NextResponse.json(
        {
          error: "Failed to remove watch.",
        },
        {
          status: 500,
        },
      );
    }

    if (!deletedWatch) {
      return NextResponse.json(
        {
          error: "Watch not found.",
        },
        {
          status: 404,
        },
      );
    }

    return NextResponse.json({
      success: true,
      id: deletedWatch.id,
    });
  } catch (error) {
    console.error(
      "DELETE /api/watch-intents/:id failed:",
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
