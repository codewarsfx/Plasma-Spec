import type { Session } from "@supabase/supabase-js";

export {};

declare global {
  interface Window {
    /** Present only inside the packaged Electron app (see desktop/preload.cjs). */
    electronAuth?: {
      /** Opens the system browser for Google sign-in via the main process's
       * loopback-server flow; resolves once triggered (the session itself
       * arrives asynchronously via the "session" event). */
      signIn: () => Promise<void>;
      signOut: () => Promise<void>;
      onSession: (callback: (session: Session) => void) => () => void;
    };
  }
}
