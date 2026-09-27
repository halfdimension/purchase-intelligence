import { NextResponse } from "next/server";

export function POST() {
  return NextResponse.json(
    {
      error:
        "Account registration is currently disabled.",
    },
    {
      status: 403,
    },
  );
}
