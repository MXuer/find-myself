import { existsSync, mkdirSync, rmSync, symlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tauriRoot = resolve(__dirname, "..");
const projectRoot = resolve(tauriRoot, "..", "..");
const productName = "Find Myself";
const version = "0.2.0";
const appPath = join(tauriRoot, "src-tauri", "target", "release", "bundle", "macos", `${productName}.app`);
const stagingDir = join(tauriRoot, ".dmg-staging");
const outputDir = join(projectRoot, "dist");
const arch = "arm64";
const outputPath = join(outputDir, `${productName}_${version}_${arch}.dmg`);

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: projectRoot,
    stdio: "inherit",
    ...options,
  });

  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`);
  }
}

if (!existsSync(appPath)) {
  throw new Error(`Missing built app: ${appPath}`);
}

rmSync(stagingDir, { force: true, recursive: true });
mkdirSync(stagingDir, { recursive: true });
run("cp", ["-R", appPath, stagingDir]);

const applicationsLink = join(stagingDir, "Applications");
if (!existsSync(applicationsLink)) {
  symlinkSync("/Applications", applicationsLink);
}

mkdirSync(outputDir, { recursive: true });
rmSync(outputPath, { force: true });

run("hdiutil", [
  "create",
  "-volname",
  productName,
  "-srcfolder",
  stagingDir,
  "-ov",
  "-format",
  "UDZO",
  outputPath,
]);
