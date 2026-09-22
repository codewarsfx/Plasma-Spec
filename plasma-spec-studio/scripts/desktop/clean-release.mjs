import { rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

rmSync(path.join(root, "release"), {
  recursive: true,
  force: true,
  maxRetries: 3,
  retryDelay: 100,
});

console.log("Cleaned desktop release output.");
