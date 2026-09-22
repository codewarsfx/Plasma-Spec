import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const backendDir = path.join(root, "backend");
const outRoot = path.join(root, "desktop-dist");
const backendOut = path.join(outRoot, "backend");
const molecularOut = path.join(outRoot, "molecular");

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

function resetDir(dir) {
  rmSync(dir, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  if (existsSync(dir)) {
    for (const entry of readdirSync(dir)) {
      rmSync(path.join(dir, entry), { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
    }
  }
  mkdirSync(dir, { recursive: true });
}

function pythonCommand() {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venvPython = process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");
  return existsSync(venvPython) ? venvPython : "python";
}

resetDir(backendOut);
const pyinstallerConfigDir = path.join(backendDir, "build", "pyinstaller-cache");
const matplotlibConfigDir = path.join(backendDir, "build", "matplotlib-cache");
mkdirSync(matplotlibConfigDir, { recursive: true });

run(pythonCommand(), ["-m", "PyInstaller", "pyinstaller.spec", "--noconfirm", "--clean"], {
  cwd: backendDir,
  env: {
    ...process.env,
    PYINSTALLER_CONFIG_DIR: pyinstallerConfigDir,
    MPLCONFIGDIR: matplotlibConfigDir,
  },
});

const executable = process.platform === "win32" ? "plasma-spec-backend.exe" : "plasma-spec-backend";
const builtExecutable = path.join(backendDir, "dist", executable);
if (!existsSync(builtExecutable)) {
  throw new Error(`PyInstaller did not produce ${builtExecutable}`);
}
cpSync(builtExecutable, path.join(backendOut, executable));

resetDir(molecularOut);
const molecularCandidates = [
  path.resolve(root, "..", "Molecular Line Data"),
  path.join(root, "Molecular Line Data"),
];
const molecularSource = molecularCandidates.find((candidate) => existsSync(candidate));
let bundledDbCount = 0;
if (molecularSource) {
  for (const entry of readdirSync(molecularSource)) {
    if (entry.toLowerCase().endsWith(".db")) {
      cpSync(path.join(molecularSource, entry), path.join(molecularOut, entry));
      bundledDbCount += 1;
    }
  }
}
if (bundledDbCount === 0) {
  // Packaging used to silently drop a README.txt placeholder here and let
  // the build "succeed" -- every installer built that way ships with
  // molecular band fitting completely broken (every OH/N2/NO/N2+ fit
  // request 404s) with nothing in the build log calling that out. Fail
  // loudly instead: whoever is cutting a release needs to either provide
  // the databases or explicitly acknowledge they're shipping without them.
  writeFileSync(
    path.join(molecularOut, "README.txt"),
    "Place MassiveOES SQLite .db molecular databases here before packaging if you want validated molecular band fits bundled.\n",
  );
  const message =
    "No molecular .db files found (looked in: " +
    molecularCandidates.join(", ") +
    "). This build would ship with molecular band fitting completely broken. " +
    "Provide the databases, or set PLASMA_SPEC_ALLOW_MISSING_MOLECULAR_DB=1 to " +
    "intentionally build a demo-only package without them.";
  if (process.env.PLASMA_SPEC_ALLOW_MISSING_MOLECULAR_DB === "1") {
    console.warn(`[build-backend] WARNING: ${message}`);
  } else {
    throw new Error(`[build-backend] ${message}`);
  }
}

console.log(`Prepared backend desktop bundle at ${backendOut}`);
console.log(`Prepared molecular database bundle at ${molecularOut}`);
