import { NextRequest, NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

/** Supabase redirects here with ?code=... after Google sign-in completes;
 * exchange it for a session (sets the auth cookies) and continue on to
 * wherever the user was headed. Same NextRequest/NextResponse route-handler
 * shape as app/downloads/[platform]/route.ts. */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/studio";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`);
}
