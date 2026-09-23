"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FlaskConical } from "lucide-react";

import { supabase } from "@/lib/supabase/client";

type Mode = "signin" | "signup";

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/studio";
  const authFailed = searchParams.get("error") === "auth_callback_failed";
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkEmail, setCheckEmail] = useState(false);

  function notConfigured() {
    setError("Supabase isn't configured for this deployment (NEXT_PUBLIC_SUPABASE_URL/ANON_KEY missing).");
  }

  async function signInWithGoogle() {
    if (!supabase) return notConfigured();
    setBusy(true);
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });
    if (signInError) {
      setError(signInError.message);
      setBusy(false);
    }
    // On success the browser navigates away to Google, so nothing else to do here.
  }

  async function submitEmailPassword(event: FormEvent) {
    event.preventDefault();
    if (!supabase) return notConfigured();
    setBusy(true);
    setError(null);
    setCheckEmail(false);

    if (mode === "signup") {
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
      });
      setBusy(false);
      if (signUpError) {
        setError(signUpError.message);
        return;
      }
      if (!data.session) {
        // Email confirmation is required (the default) -- no session yet.
        setCheckEmail(true);
        return;
      }
      router.push(next);
      return;
    }

    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (signInError) {
      setError(signInError.message);
      return;
    }
    router.push(next);
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col items-center justify-center gap-6 px-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center border border-teal-200 bg-teal-50 text-teal-900" style={{ borderRadius: 10 }}>
        <FlaskConical className="h-6 w-6" />
      </div>
      <div>
        <h1 className="text-xl font-semibold text-ink">
          {mode === "signup" ? "Create your account" : "Sign in to PlasmaSpec Studio"}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Your spectra, recipes, and results sync across every device you sign into.
        </p>
      </div>

      {checkEmail ? (
        <p className="text-sm text-slate-600">
          Check <strong>{email}</strong> for a confirmation link, then come back and sign in.
        </p>
      ) : (
        <>
          {(error || authFailed) && (
            <p className="text-sm text-red-600">{error ?? "Sign-in failed. Please try again."}</p>
          )}

          <button
            type="button"
            onClick={signInWithGoogle}
            disabled={busy}
            className="primary-button w-full justify-center"
          >
            {busy ? "Redirecting…" : "Continue with Google"}
          </button>

          <div className="flex w-full items-center gap-3 text-xs text-slate-400">
            <span className="h-px flex-1 bg-line" />
            or
            <span className="h-px flex-1 bg-line" />
          </div>

          <form onSubmit={submitEmailPassword} className="flex w-full flex-col gap-3 text-left">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-500">Email</span>
              <input
                type="email"
                required
                autoComplete="email"
                className="field"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-500">Password</span>
              <input
                type="password"
                required
                minLength={6}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                className="field"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit" disabled={busy} className="text-button w-full justify-center border border-line">
              {busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in with email"}
            </button>
          </form>

          <button
            type="button"
            className="text-xs text-slate-500 underline"
            onClick={() => {
              setMode(mode === "signup" ? "signin" : "signup");
              setError(null);
            }}
          >
            {mode === "signup" ? "Already have an account? Sign in" : "New here? Create an account"}
          </button>
        </>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginContent />
    </Suspense>
  );
}
