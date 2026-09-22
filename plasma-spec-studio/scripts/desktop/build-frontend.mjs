import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const frontendDir = path.join(root, "frontend");
const outDir = path.join(root, "desktop-dist", "frontend");
const backendPort = process.env.PLASMA_SPEC_BACKEND_PORT || "18765";

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed`);
  }
}

run("npm", ["run", "build"], {
  cwd: frontendDir,
  env: {
    ...process.env,
    NEXT_PUBLIC_API_BASE: `http://127.0.0.1:${backendPort}`,
  },
});

const standaloneDir = path.join(frontendDir, ".next", "standalone");
if (!existsSync(standaloneDir)) {
  throw new Error("Next standalone output missing. Check frontend/next.config.ts output='standalone'.");
}

rmSync(outDir, { recursive: true, force: true });
mkdirSync(path.dirname(outDir), { recursive: true });
cpSync(standaloneDir, outDir, { recursive: true });

const staticSrc = path.join(frontendDir, ".next", "static");
if (existsSync(staticSrc)) {
  for (const staticDest of [
    path.join(outDir, ".next", "static"),
    path.join(outDir, "frontend", ".next", "static"),
  ]) {
    mkdirSync(path.dirname(staticDest), { recursive: true });
    cpSync(staticSrc, staticDest, { recursive: true });
  }
}

const publicSrc = path.join(frontendDir, "public");
if (existsSync(publicSrc)) {
  for (const publicDest of [
    path.join(outDir, "public"),
    path.join(outDir, "frontend", "public"),
  ]) {
    mkdirSync(path.dirname(publicDest), { recursive: true });
    cpSync(publicSrc, publicDest, { recursive: true });
  }
}

console.log(`Prepared frontend desktop bundle at ${outDir}`);
