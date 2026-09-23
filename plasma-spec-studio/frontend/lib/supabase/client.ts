"use client";

import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Cookie-backed (not localStorage) so the session is also visible to
// middleware.ts and any server component -- that's the whole point of
// @supabase/ssr over the plain supabase-js browser client.
export const supabase =
  supabaseUrl && supabaseAnonKey ? createBrowserClient(supabaseUrl, supabaseAnonKey) : null;

// lib/api.ts needs the current access token synchronously (exportUrl() /
// batchStreamUrl() return plain strings used as <a href>/EventSource URLs,
// not something we can await at call time), but supabase-js's own
// getSession() is async. Cache it here, kept in sync via onAuthStateChange
// (which fires once immediately with the session restored from the
// cookie, then again on every sign-in/sign-out/refresh).
let cachedAccessToken: string | null = null;

supabase?.auth.onAuthStateChange((_event, session) => {
  cachedAccessToken = session?.access_token ?? null;
});

export function getCachedAccessToken(): string | null {
  return cachedAccessToken;
}
