const { app, BrowserWindow, dialog, shell } = require("electron");
const childProcess = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const BACKEND_PORT = Number(process.env.PLASMA_SPEC_BACKEND_PORT || 18765);
const FRONTEND_PORT = Number(process.env.PLASMA_SPEC_FRONTEND_PORT || 18766);
const HOST = "127.0.0.1";

let backendProcess = null;
let frontendProcess = null;
let mainWindow = null;

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
  fs.mkdirSync(storageDir, { recursive: true });
  fs.mkdirSync(matplotlibDir, { recursive: true });

  const molecularDir = resourcePath("molecular");
  const env = {
    ...process.env,
    PLASMA_SPEC_HOST: HOST,
    PLASMA_SPEC_PORT: String(BACKEND_PORT),
    PLASMA_SPEC_STORAGE_DIR: storageDir,
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
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
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
