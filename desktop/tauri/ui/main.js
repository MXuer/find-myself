const tauri = window.__TAURI__ || {};
const invoke =
  tauri.core?.invoke?.bind(tauri.core) ||
  tauri.invoke?.bind(tauri);

const statusBanner = document.querySelector("#statusBanner");
const runtimeState = document.querySelector("#runtimeState");
const backendState = document.querySelector("#backendState");
const dataDir = document.querySelector("#dataDir");
const runtimeDir = document.querySelector("#runtimeDir");
const logsDir = document.querySelector("#logsDir");
const backendUrl = document.querySelector("#backendUrl");
const modelPolicy = document.querySelector("#modelPolicy");

const refreshButton = document.querySelector("#refreshButton");
const installButton = document.querySelector("#installButton");
const startButton = document.querySelector("#startButton");
const stopButton = document.querySelector("#stopButton");
const logsButton = document.querySelector("#logsButton");

let pollTimer = null;

function setBanner(kind, message) {
  statusBanner.className = `status-banner status-banner--${kind}`;
  statusBanner.textContent = message;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  if (label) {
    button.dataset.label = button.dataset.label || button.textContent;
    button.textContent = busy ? label : button.dataset.label;
  }
}

async function call(command, args = {}) {
  if (!invoke) {
    throw new Error("Tauri API unavailable. Use the desktop app instead of a plain browser.");
  }
  return invoke(command, args);
}

function renderStatus(status) {
  runtimeState.textContent = status.runtime.phaseLabel;
  backendState.textContent = status.backend.phaseLabel;
  dataDir.textContent = status.paths.dataDir;
  runtimeDir.textContent = status.paths.runtimeDir;
  logsDir.textContent = status.paths.logsDir;
  backendUrl.textContent = status.backend.url || "-";
  modelPolicy.textContent = status.modelPolicy;

  if (status.backend.running) {
    setBanner("success", "本地服务已启动，可以直接进入应用。");
  } else if (status.runtime.installing) {
    setBanner("warning", "正在安装本地运行环境。安装完成前请不要关闭窗口。");
  } else if (status.runtime.ready) {
    setBanner("neutral", "运行环境已就绪，点击“启动桌面应用”进入检索界面。");
  } else if (status.runtime.failed) {
    setBanner("danger", status.runtime.error || "运行环境安装失败。请查看日志。");
  } else {
    setBanner("neutral", "当前尚未安装本地运行环境。");
  }

  installButton.disabled = status.runtime.installing;
  startButton.disabled = !status.runtime.ready && !status.backend.running;
  stopButton.disabled = !status.backend.running;
}

async function refreshStatus() {
  const status = await call("app_status");
  renderStatus(status);
  return status;
}

async function installRuntime() {
  setBusy(installButton, true, "安装中…");
  try {
    await call("install_runtime");
    await refreshStatus();
  } finally {
    setBusy(installButton, false);
  }
}

async function startBackend() {
  setBusy(startButton, true, "启动中…");
  try {
    const result = await call("start_backend");
    await refreshStatus();
    if (result.url) {
      window.location.replace(result.url);
    }
  } finally {
    setBusy(startButton, false);
  }
}

async function stopBackend() {
  setBusy(stopButton, true, "停止中…");
  try {
    await call("stop_backend");
    await refreshStatus();
  } finally {
    setBusy(stopButton, false);
  }
}

async function openLogs() {
  await call("open_logs_dir");
}

refreshButton.addEventListener("click", () => refreshStatus().catch(handleError));
installButton.addEventListener("click", () => installRuntime().catch(handleError));
startButton.addEventListener("click", () => startBackend().catch(handleError));
stopButton.addEventListener("click", () => stopBackend().catch(handleError));
logsButton.addEventListener("click", () => openLogs().catch(handleError));

function handleError(error) {
  setBanner("danger", error?.message || String(error));
}

async function bootstrap() {
  await refreshStatus();
  pollTimer = window.setInterval(() => {
    refreshStatus().catch(() => {});
  }, 2000);
}

window.addEventListener("beforeunload", () => {
  if (pollTimer) {
    window.clearInterval(pollTimer);
  }
});

bootstrap().catch(handleError);
