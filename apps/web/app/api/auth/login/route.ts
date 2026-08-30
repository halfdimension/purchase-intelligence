import { NextResponse } from "next/server";

import {
  createSupabaseServerClient,
} from "@/lib/supabase-auth-server";

export async function POST(request: Request) {
  try {
    let body: unknown;

    try {
      body = await request.json();
    } catch {
      return NextResponse.json(
        {
          error: "Invalid JSON body.",
        },
        {
          status: 400,
        },
      );
    }

    if (
      typeof body !== "object"
      || body === null
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

    const payload =
      body as Record<string, unknown>;

    const email =
      typeof payload.email === "string"
        ? payload.email.trim().toLowerCase()
        : "";

    const password =
      typeof payload.password === "string"
        ? payload.password
        : "";

    if (!email || !password) {
      return NextResponse.json(
        {
          error:
            "Email and password are required.",
        },
        {
          status: 400,
        },
      );
    }

    const supabase =
      await createSupabaseServerClient();

    const {
      data,
      error,
    } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error || !data.user) {
      return NextResponse.json(
        {
          error: "Invalid email or password.",
        },
        {
          status: 401,
        },
      );
    }

    return NextResponse.json({
      authenticated: true,
      user: {
        id: data.user.id,
        email: data.user.email ?? null,
      },
    });
  } catch (error) {
    console.error(
      "POST /api/auth/login failed:",
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
