"use client";

import { LogOut, User } from "lucide-react";
import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "@/lib/supabase/client";

export function AuthButton() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!supabase) {
      setReady(true);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });

    // Desktop: the main process delivers the session from its own loopback
    // OAuth flow over IPC (see desktop/preload.cjs) -- adopt it into this
    // window's own Supabase client so it behaves exactly like the web flow
    // (persisted, auto-refreshing) from then on.
    const unsubscribeElectron = window.electronAuth?.onSession((electronSession) => {
      supabase?.auth.setSession({
        access_token: electronSession.access_token,
        refresh_token: electronSession.refresh_token,
      });
    });

    return () => {
      subscription.subscription.unsubscribe();
      unsubscribeElectron?.();
    };
  }, []);

  if (!supabase || !ready) {
    return null;
  }

  async function signIn() {
    if (window.electronAuth) {
      await window.electronAuth.signIn();
      return;
    }
    await supabase?.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
  }

  async function signOut() {
    await supabase?.auth.signOut();
    await window.electronAuth?.signOut();
  }

  if (!session) {
    return (
      <button type="button" className="text-button" onClick={signIn}>
        Sign in
      </button>
    );
  }

  const label = session.user.user_metadata?.full_name || session.user.email || "Signed in";

  return (
    <div className="flex items-center gap-2">
      <span className="hidden items-center gap-1.5 text-xs text-slate-500 sm:flex" title={session.user.email ?? undefined}>
        <User className="h-3.5 w-3.5" />
        {label}
      </span>
      <button type="button" className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out">
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}
