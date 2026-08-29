import { NextResponse } from "next/server";

import { getSupabaseAdmin } from "@/lib/supabase-server";


export async function GET(
  _request: Request,
  context: {
    params: Promise<{ id: string }>;
  },
) {
  try {
    const { id } = await context.params;

    if (!id) {
      return NextResponse.json(
        { error: "Product ID is required." },
        { status: 400 },
      );
    }

    const supabase = getSupabaseAdmin();

    const { data, error } = await supabase
      .from("price_snapshots")
      .select(`
        id,
        mrp,
        selling_price,
        currency,
        in_stock,
        checked_at
      `)
      .eq("product_id", id)
      .order("checked_at", { ascending: true })
      .limit(500);

    if (error) {
      console.error(
        "Failed to load product price history:",
        error,
      );

      return NextResponse.json(
        { error: "Failed to load price history." },
        { status: 500 },
      );
    }

    const history = data ?? [];

    const prices = history
      .map((snapshot) => snapshot.selling_price)
      .filter(
        (price): price is number =>
          typeof price === "number",
      );

    const lowestPrice =
      prices.length > 0
        ? Math.min(...prices)
        : null;

    const highestPrice =
      prices.length > 0
        ? Math.max(...prices)
        : null;

    const latest =
      history.length > 0
        ? history[history.length - 1]
        : null;

    return NextResponse.json({
      product_id: id,
      stats: {
        lowest_price: lowestPrice,
        highest_price: highestPrice,
        latest_price: latest?.selling_price ?? null,
        snapshot_count: history.length,
      },
      history,
    });
  } catch (error) {
    console.error(
      "GET /api/products/:id/history failed:",
      error,
    );

    return NextResponse.json(
      { error: "Internal server error." },
      { status: 500 },
    );
  }
}
