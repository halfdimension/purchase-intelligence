import { NextResponse } from "next/server";

import { getSupabaseAdmin } from "@/lib/supabase-server";

function detectBrand(productUrl: string) {
  const hostname = new URL(productUrl).hostname.toLowerCase();

  if (hostname.includes("nike.")) {
    return "Nike";
  }

  if (hostname.includes("adidas.")) {
    return "Adidas";
  }

  if (hostname.includes("asics.")) {
    return "ASICS";
  }

  return "Other";
}

export async function GET() {
  try {
    const supabase = getSupabaseAdmin();

    const { data, error } = await supabase
      .from("watchlists")
      .select(`
        id,
        email,
        desired_size,
        target_price,
        created_at,
        products (
          id,
          url,
          brand
        )
      `)
      .order("created_at", { ascending: false });

    if (error) {
      console.error("Failed to read watchlist:", error);

      return NextResponse.json(
        { error: "Failed to load watchlist." },
        { status: 500 },
      );
    }

    return NextResponse.json({ watchlist: data });
  } catch (error) {
    console.error("GET /api/watchlist failed:", error);

    return NextResponse.json(
      { error: "Internal server error." },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const productUrl =
      typeof body.productUrl === "string" ? body.productUrl.trim() : "";

    const email =
      typeof body.email === "string" ? body.email.trim().toLowerCase() : "";

    const size =
      typeof body.size === "string" && body.size.trim()
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
        { error: "Product URL is required." },
        { status: 400 },
      );
    }

    let parsedUrl: URL;

    try {
      parsedUrl = new URL(productUrl);
    } catch {
      return NextResponse.json(
        { error: "Enter a valid product URL." },
        { status: 400 },
      );
    }

    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      return NextResponse.json(
        { error: "Only HTTP and HTTPS product URLs are supported." },
        { status: 400 },
      );
    }

    if (!email) {
      return NextResponse.json(
        { error: "Email is required." },
        { status: 400 },
      );
    }

    if (
      targetPrice !== null &&
      (!Number.isFinite(targetPrice) || targetPrice <= 0)
    ) {
      return NextResponse.json(
        { error: "Target price must be greater than 0." },
        { status: 400 },
      );
    }

    const normalizedUrl = parsedUrl.toString();
    const brand = detectBrand(normalizedUrl);

    const supabase = getSupabaseAdmin();

    const { data: product, error: productError } = await supabase
      .from("products")
      .upsert(
        {
          url: normalizedUrl,
          brand,
          updated_at: new Date().toISOString(),
        },
        {
          onConflict: "url",
        },
      )
      .select("id, url, brand")
      .single();

    if (productError || !product) {
      console.error("Failed to save product:", productError);

      return NextResponse.json(
        { error: "Failed to save product." },
        { status: 500 },
      );
    }

    const { data: watchlistItem, error: watchlistError } = await supabase
      .from("watchlists")
      .insert({
        product_id: product.id,
        email,
        desired_size: size,
        target_price: targetPrice,
      })
      .select(`
        id,
        email,
        desired_size,
        target_price,
        created_at,
        products (
          id,
          url,
          brand
        )
      `)
      .single();

    if (watchlistError) {
      if (watchlistError.code === "23505") {
        return NextResponse.json(
          { error: "This product is already tracked for this email." },
          { status: 409 },
        );
      }

      console.error("Failed to create watchlist item:", watchlistError);

      return NextResponse.json(
        { error: "Failed to create watchlist item." },
        { status: 500 },
      );
    }

    return NextResponse.json(
      { watchlistItem },
      { status: 201 },
    );
  } catch (error) {
    console.error("POST /api/watchlist failed:", error);

    return NextResponse.json(
      { error: "Internal server error." },
      { status: 500 },
    );
  }
}
