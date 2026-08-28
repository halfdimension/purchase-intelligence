import { NextResponse } from "next/server";

import { getSupabaseAdmin } from "@/lib/supabase-server";

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
        { error: "Watchlist ID is required." },
        { status: 400 },
      );
    }

    const supabase = getSupabaseAdmin();

    const { data, error } = await supabase
      .from("watchlists")
      .delete()
      .eq("id", id)
      .select("id")
      .maybeSingle();

    if (error) {
      console.error("Failed to remove watchlist item:", error);

      return NextResponse.json(
        { error: "Failed to remove watchlist item." },
        { status: 500 },
      );
    }

    if (!data) {
      return NextResponse.json(
        { error: "Watchlist item not found." },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      id: data.id,
    });
  } catch (error) {
    console.error("DELETE /api/watchlist/:id failed:", error);

    return NextResponse.json(
      { error: "Internal server error." },
      { status: 500 },
    );
  }
}
