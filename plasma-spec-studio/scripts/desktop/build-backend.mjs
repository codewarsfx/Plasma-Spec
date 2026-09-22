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
if (molecularSource) {
  for (const entry of readdirSync(molecularSource)) {
    if (entry.toLowerCase().endsWith(".db")) {
      cpSync(path.join(molecularSource, entry), path.join(molecularOut, entry));
    }
  }
} else {
  writeFileSync(
    path.join(molecularOut, "README.txt"),
    "Place MassiveOES SQLite .db molecular databases here before packaging if you want validated molecular band fits bundled.\n",
  );
}

console.log(`Prepared backend desktop bundle at ${backendOut}`);
console.log(`Prepared molecular database bundle at ${molecularOut}`);
