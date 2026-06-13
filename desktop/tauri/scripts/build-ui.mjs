import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tauriRoot = resolve(__dirname, "..");
const sourceDir = join(tauriRoot, "ui");
const targetDir = join(tauriRoot, "dist-ui");

if (!existsSync(sourceDir)) {
  throw new Error(`Missing UI source directory: ${sourceDir}`);
}

rmSync(targetDir, { recursive: true, force: true });
mkdirSync(targetDir, { recursive: true });
cpSync(sourceDir, targetDir, { recursive: true });
