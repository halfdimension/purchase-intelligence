import {
  type EmailOtpType,
} from "@supabase/supabase-js";
import {
  type NextRequest,
  NextResponse,
} from "next/server";

import {
  createSupabaseServerClient,
} from "@/lib/supabase-auth-server";

export async function GET(
  request: NextRequest,
) {
  const tokenHash =
    request.nextUrl.searchParams.get(
      "token_hash",
    );

  const type =
    request.nextUrl.searchParams.get(
      "type",
    ) as EmailOtpType | null;

  if (tokenHash && type) {
    const supabase =
      await createSupabaseServerClient();

    const { error } =
      await supabase.auth.verifyOtp({
        type,
        token_hash: tokenHash,
      });

    if (!error) {
      return NextResponse.redirect(
        new URL(
          "/?confirmed=1",
          request.url,
        ),
      );
    }
  }

  return NextResponse.redirect(
    new URL(
      "/login?error=confirmation_failed",
      request.url,
    ),
  );
}
