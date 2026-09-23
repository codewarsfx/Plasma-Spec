const { contextBridge, ipcRenderer } = require("electron");

// Exposes a minimal, explicit surface to the renderer for the desktop-only
// Google sign-in flow (see main.cjs's ipcMain.handle("auth:sign-in", ...)).
// contextIsolation is on and nodeIntegration is off (main.cjs), so this is
// the only bridge between the sandboxed renderer and Node/Electron APIs.
contextBridge.exposeInMainWorld("electronAuth", {
  signIn: () => ipcRenderer.invoke("auth:sign-in"),
  signOut: () => ipcRenderer.invoke("auth:sign-out"),
  onSession: (callback) => {
    const listener = (_event, session) => callback(session);
    ipcRenderer.on("auth:session", listener);
    return () => ipcRenderer.removeListener("auth:session", listener);
  },
});
