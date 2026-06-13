import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tauriRoot = resolve(__dirname, "..");
const projectRoot = resolve(tauriRoot, "..", "..");
const buildVenvDir = join(tauriRoot, ".backend-build-venv");
const backendRoot = join(projectRoot, "desktop", "backend");
const backendDistDir = join(tauriRoot, "resources", "backend");
const backendBuildDir = join(backendRoot, "build");
const backendSpec = join(backendRoot, "find_myself_backend.spec");
const requirements = join(projectRoot, "requirements.txt");
const engineCli = join(backendRoot, "engine_cli.py");
const stampFile = join(buildVenvDir, ".build-stamp");

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

function buildFingerprint() {
  const hash = createHash("sha256");
  hash.update(readFileSync(requirements));
  hash.update(readFileSync(engineCli));
  hash.update(readFileSync(backendSpec));
  hash.update(readFileSync(fileURLToPath(import.meta.url)));
  return hash.digest("hex");
}

function pythonBin() {
  return join(buildVenvDir, "bin", "python");
}

function ensureBuildVenv() {
  if (!existsSync(pythonBin())) {
    mkdirSync(buildVenvDir, { recursive: true });
    run("python3", ["-m", "venv", buildVenvDir]);
  }
}

function installBuildDepsIfNeeded() {
  const currentFingerprint = buildFingerprint();
  const previousFingerprint = existsSync(stampFile) ? readFileSync(stampFile, "utf8").trim() : "";

  if (currentFingerprint === previousFingerprint && existsSync(join(backendDistDir, "find-myself-backend"))) {
    return;
  }

  run(pythonBin(), ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]);
  run(pythonBin(), ["-m", "pip", "install", "-r", requirements]);
  run(pythonBin(), ["-m", "pip", "uninstall", "-y", "opencv-python"]);
  run(pythonBin(), ["-m", "pip", "install", "--force-reinstall", "opencv-python-headless==4.13.0.92"]);
  run(pythonBin(), ["-m", "pip", "install", "pyinstaller==6.20.0"]);

  rmSync(backendDistDir, { force: true, recursive: true });
  rmSync(backendBuildDir, { force: true, recursive: true });
  mkdirSync(backendDistDir, { recursive: true });

  run(pythonBin(), ["-m", "PyInstaller", backendSpec, "--noconfirm", "--distpath", backendDistDir, "--workpath", backendBuildDir]);

  writeFileSync(stampFile, `${currentFingerprint}\n`);
}

ensureBuildVenv();
installBuildDepsIfNeeded();
