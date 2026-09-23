const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const childProcess = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { createClient } = require("@supabase/supabase-js");

const BACKEND_PORT = Number(process.env.PLASMA_SPEC_BACKEND_PORT || 18765);
const FRONTEND_PORT = Number(process.env.PLASMA_SPEC_FRONTEND_PORT || 18766);
const HOST = "127.0.0.1";

let backendProcess = null;
let frontendProcess = null;
let mainWindow = null;

// scripts/desktop/build-frontend.mjs writes this from NEXT_PUBLIC_SUPABASE_*
// at package time (same values the renderer's Next bundle gets baked in
// with) so the packaged app has them without requiring an end user to set
// environment variables. `npm run desktop:dev` has no generated file, so it
// falls back to whatever the developer's own shell already exports.
let generatedEnv = {};
try {
  generatedEnv = require("./env.generated.cjs");
} catch {
  // Expected outside a packaged build.
}
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || generatedEnv.SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || generatedEnv.SUPABASE_ANON_KEY || "";

function resourcePath(...parts) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, ...parts);
  }
  return path.join(__dirname, "..", ...parts);
}

function backendExecutablePath() {
  const executable = process.platform === "win32"
    ? "plasma-spec-backend.exe"
    : "plasma-spec-backend";
  return resourcePath("backend", executable);
}

function frontendServerPath() {
  return resourcePath("frontend", "server.js");
}

function studioUrl() {
  if (!app.isPackaged) {
    return process.env.PLASMA_SPEC_FRONTEND_URL || "http://127.0.0.1:3005/studio";
  }
  return `http://${HOST}:${FRONTEND_PORT}/studio`;
}

// --- Desktop Google sign-in ---------------------------------------------
//
// Google refuses to complete OAuth inside an embedded/webview-style browser
// (which Electron's BrowserWindow is treated as), so sign-in has to happen
// in the user's real system browser, with the result routed back into the
// app via a temporary loopback HTTP server:
//   1. Ask Supabase for the Google authorize URL (skipBrowserRedirect,
//      since there's no window to redirect in this Node process).
//   2. Open it in the system browser (shell.openExternal).
//   3. A loopback server on an OS-assigned ephemeral port catches Google's
//      redirect back with ?code=...
//   4. Exchange the code for a session using the SAME client instance that
//      started the flow (PKCE requires this -- the code_verifier lives in
//      that client's in-memory storage).
//   5. Send the session to the renderer over IPC; its own Supabase client
//      adopts it via setSession() and takes over from there (persisted,
//      auto-refreshing), exactly like the web sign-in flow.

let authClient = null;

function getAuthClient() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;
  if (!authClient) {
    // No localStorage in a Node/main-process context -- use an explicit
    // in-memory adapter instead of relying on supabase-js's own
    // browser-vs-server auto-detection. This client only exists to run the
    // PKCE dance once per sign-in attempt; the real, persisted session
    // lives in the renderer's cookie-backed client (lib/supabase/client.ts).
    const memory = new Map();
    authClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        storage: {
          getItem: (key) => (memory.has(key) ? memory.get(key) : null),
          setItem: (key, value) => memory.set(key, value),
          removeItem: (key) => memory.delete(key),
        },
        persistSession: false,
        autoRefreshToken: false,
        detectSessionInUrl: false,
      },
    });
  }
  return authClient;
}

let loopbackServer = null;

function stopLoopbackServer() {
  if (loopbackServer) {
    loopbackServer.close();
    loopbackServer = null;
  }
}

function signInWithGoogleLoopback() {
  const client = getAuthClient();
  if (!client) {
    return Promise.reject(
      new Error("Supabase isn't configured for this build (SUPABASE_URL/SUPABASE_ANON_KEY missing)."),
    );
  }
  stopLoopbackServer(); // in case a previous attempt is still hanging open

  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      stopLoopbackServer();
      fn(value);
    };

    loopbackServer = http.createServer((req, res) => {
      const requestUrl = new URL(req.url, "http://127.0.0.1");
      if (requestUrl.pathname !== "/callback") {
        res.writeHead(404);
        res.end();
        return;
      }
      const code = requestUrl.searchParams.get("code");
      const errorDescription =
        requestUrl.searchParams.get("error_description") || requestUrl.searchParams.get("error");
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end("<html><body>Signed in. You can close this tab and return to PlasmaSpec Studio.</body></html>");

      if (errorDescription) {
        finish(reject, new Error(errorDescription));
        return;
      }
      if (!code) {
        finish(reject, new Error("Google sign-in did not return an authorization code."));
        return;
      }
      client.auth
        .exchangeCodeForSession(code)
        .then(({ data, error }) => {
          if (error) throw error;
          finish(resolve, data.session);
        })
        .catch((error) => finish(reject, error));
    });

    loopbackServer.on("error", (error) => finish(reject, error));

    loopbackServer.listen(0, "127.0.0.1", () => {
      const { port } = loopbackServer.address();
      client.auth
        .signInWithOAuth({
          provider: "google",
          options: { redirectTo: `http://127.0.0.1:${port}/callback`, skipBrowserRedirect: true },
        })
        .then(({ data, error }) => {
          if (error || !data.url) {
            throw error || new Error("Failed to build the Google sign-in URL.");
          }
          shell.openExternal(data.url);
        })
        .catch((error) => finish(reject, error));
    });

    // Give up if nobody completes sign-in in the browser within 5 minutes.
    setTimeout(() => finish(reject, new Error("Sign-in timed out.")), 5 * 60 * 1000);
  });
}

ipcMain.handle("auth:sign-in", async (event) => {
  try {
    const session = await signInWithGoogleLoopback();
    event.sender.send("auth:session", session);
  } catch (error) {
    dialog.showErrorBox("Sign-in failed", error instanceof Error ? error.message : String(error));
  }
});

ipcMain.handle("auth:sign-out", async () => {
  // The renderer's own client already signed itself out (AuthButton.tsx);
  // this just resets our ephemeral PKCE helper so the next sign-in starts
  // from a clean state.
  authClient = null;
});

function appDataPath(...parts) {
  return path.join(app.getPath("userData"), ...parts);
}

function spawnLogged(command, args, options) {
  const child = childProcess.spawn(command, args, {
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    ...options,
  });
  child.stdout?.on("data", (data) => console.log(`[${options.name}] ${data}`.trim()));
  child.stderr?.on("data", (data) => console.error(`[${options.name}] ${data}`.trim()));
  child.on("exit", (code, signal) => {
    console.log(`[${options.name}] exited`, { code, signal });
  });
  return child;
}

function startBackend() {
  const executable = backendExecutablePath();
  if (!fs.existsSync(executable)) {
    throw new Error(`Backend executable not found: ${executable}`);
  }
  const storageDir = appDataPath("storage");
  const matplotlibDir = appDataPath("matplotlib");
  const atomicDataDir = appDataPath("atomic");
  fs.mkdirSync(storageDir, { recursive: true });
  fs.mkdirSync(matplotlibDir, { recursive: true });
  fs.mkdirSync(atomicDataDir, { recursive: true });

  const molecularDir = resourcePath("molecular");
  const env = {
    ...process.env,
    PLASMA_SPEC_HOST: HOST,
    PLASMA_SPEC_PORT: String(BACKEND_PORT),
    PLASMA_SPEC_STORAGE_DIR: storageDir,
    PLASMA_SPEC_ATOMIC_DATA_DIR: atomicDataDir,
    PLASMA_SPEC_CORS_ORIGINS: `http://${HOST}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}`,
    MPLCONFIGDIR: matplotlibDir,
  };
  if (fs.existsSync(molecularDir)) {
    env.PLASMA_SPEC_MOLECULAR_DB_DIR = molecularDir;
  }

  backendProcess = spawnLogged(executable, [], {
    cwd: path.dirname(executable),
    env,
    name: "backend",
  });
}

function startFrontend() {
  const server = frontendServerPath();
  if (!fs.existsSync(server)) {
    throw new Error(`Frontend server not found: ${server}`);
  }
  frontendProcess = spawnLogged(process.execPath, [server], {
    cwd: path.dirname(server),
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      NODE_ENV: "production",
      NEXT_TELEMETRY_DISABLED: "1",
      HOSTNAME: HOST,
      PORT: String(FRONTEND_PORT),
    },
    name: "frontend",
  });
}

function waitForHttp(url, timeoutMs = 45_000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get(url, (response) => {
        response.resume();
        if (response.statusCode && response.statusCode >= 200 && response.statusCode < 500) {
          resolve();
        } else if (Date.now() - started > timeoutMs) {
          reject(new Error(`Timed out waiting for ${url}`));
        } else {
          setTimeout(attempt, 500);
        }
      });
      request.on("error", () => {
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`Timed out waiting for ${url}`));
        } else {
          setTimeout(attempt, 500);
        }
      });
      request.setTimeout(1500, () => request.destroy());
    };
    attempt();
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1180,
    minHeight: 760,
    title: "PlasmaSpec Studio",
    backgroundColor: "#f8fafc",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  // Exports/reports (ExportPanel.tsx, StudioResultsTable.tsx) link to the
  // local backend via target="_blank"/window.open. Those used to be treated
  // like any other "external" link -- shell.openExternal(url) -- which
  // ejected the user out of the app into their OS browser just to download
  // a CSV/PDF. Route same-origin-as-backend URLs through Electron's own
  // download machinery instead (native Save dialog, stays in-app); keep
  // openExternal for anything that isn't the app's own backend.
  const backendOrigin = `http://${HOST}:${BACKEND_PORT}`;
  mainWindow.webContents.session.on("will-download", (_event, item) => {
    item.setSaveDialogOptions({ title: `Save ${item.getFilename()}` });
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(`${backendOrigin}/`)) {
      mainWindow.webContents.downloadURL(url);
    } else {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  await mainWindow.loadURL(studioUrl());
}

function stopChild(child) {
  if (!child || child.killed) return;
  if (process.platform === "win32") {
    childProcess.spawn("taskkill", ["/pid", String(child.pid), "/f", "/t"], {
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    child.kill("SIGTERM");
  }
}

async function startApp() {
  try {
    if (app.isPackaged) {
      startBackend();
      startFrontend();
      await waitForHttp(`http://${HOST}:${BACKEND_PORT}/api/health`);
      await waitForHttp(`http://${HOST}:${FRONTEND_PORT}/studio`);
    }
    await createWindow();
  } catch (error) {
    console.error(error);
    dialog.showErrorBox(
      "PlasmaSpec Studio failed to start",
      error instanceof Error ? error.message : String(error),
    );
    app.quit();
  }
}

app.whenReady().then(startApp);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", () => {
  stopChild(frontendProcess);
  stopChild(backendProcess);
});
