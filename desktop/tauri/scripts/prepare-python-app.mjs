import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tauriRoot = resolve(__dirname, "..");
const projectRoot = resolve(tauriRoot, "..", "..");
const targetDir = join(tauriRoot, "resources", "python-app");

rmSync(targetDir, { force: true, recursive: true });
mkdirSync(targetDir, { recursive: true });

const files = [
  "app.py",
  "requirements.txt",
  "LICENSE",
  "MODEL_LICENSE.md",
  "README.md",
  "manifest.json",
];

for (const relativePath of files) {
  const source = join(projectRoot, relativePath);
  if (!existsSync(source)) {
    throw new Error(`Missing required source file: ${relativePath}`);
  }
  cpSync(source, join(targetDir, relativePath));
}

mkdirSync(join(targetDir, "data", "photos"), { recursive: true });
mkdirSync(join(targetDir, "data", "thumbs"), { recursive: true });
mkdirSync(join(targetDir, "data", "exports"), { recursive: true });
