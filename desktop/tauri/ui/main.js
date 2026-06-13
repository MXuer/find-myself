const tauri = window.__TAURI__ || {};
const invoke = tauri.core?.invoke?.bind(tauri.core) || tauri.invoke?.bind(tauri);

const presets = {
  strict: { threshold: 0.48, limit: 36 },
  balanced: { threshold: 0.38, limit: 60 },
  wide: { threshold: 0.3, limit: 96 },
};

const state = {
  status: null,
  selectedFolder: "",
  referenceFile: null,
  referencePreview: "",
  searchResults: [],
  selectedResult: null,
  decisions: new Map(),
  exportedKeys: new Set(),
  resultView: "lightTable",
  preset: "balanced",
  busy: false,
  busyStartedAt: 0,
  busyTimer: null,
};

const ui = {
  statusBanner: document.querySelector("#statusBanner"),
  runtimeState: document.querySelector("#runtimeState"),
  dataDir: document.querySelector("#dataDir"),
  runtimeDir: document.querySelector("#runtimeDir"),
  photoCount: document.querySelector("#photoCount"),
  faceCount: document.querySelector("#faceCount"),
  indexState: document.querySelector("#indexState"),
  modelPolicy: document.querySelector("#modelPolicy"),
  refreshButton: document.querySelector("#refreshButton"),
  resetButton: document.querySelector("#resetButton"),
  logsButton: document.querySelector("#logsButton"),
  revealDataButton: document.querySelector("#revealDataButton"),
  folderPath: document.querySelector("#folderPath"),
  pickFolderButton: document.querySelector("#pickFolderButton"),
  recursiveToggle: document.querySelector("#recursiveToggle"),
  libraryHint: document.querySelector("#libraryHint"),
  thresholdRange: document.querySelector("#thresholdRange"),
  thresholdValue: document.querySelector("#thresholdValue"),
  limitRange: document.querySelector("#limitRange"),
  limitValue: document.querySelector("#limitValue"),
  presetButtons: Array.from(document.querySelectorAll(".preset-button")),
  referenceInput: document.querySelector("#referenceInput"),
  referencePreview: document.querySelector("#referencePreview"),
  referenceName: document.querySelector("#referenceName"),
  referenceHint: document.querySelector("#referenceHint"),
  clearReferenceButton: document.querySelector("#clearReferenceButton"),
  indexButton: document.querySelector("#indexButton"),
  searchButton: document.querySelector("#searchButton"),
  lightTableViewButton: document.querySelector("#lightTableViewButton"),
  stackViewButton: document.querySelector("#stackViewButton"),
  gridViewButton: document.querySelector("#gridViewButton"),
  lightTableView: document.querySelector("#lightTableView"),
  lightTableImage: document.querySelector("#lightTableImage"),
  lightTableName: document.querySelector("#lightTableName"),
  lightTableScore: document.querySelector("#lightTableScore"),
  filmstrip: document.querySelector("#filmstrip"),
  resultsStack: document.querySelector("#resultsStack"),
  resultsGrid: document.querySelector("#resultsGrid"),
  emptyState: document.querySelector("#emptyState"),
  resultCount: document.querySelector("#resultCount"),
  inspectorReference: document.querySelector("#inspectorReference"),
  inspectorImage: document.querySelector("#inspectorImage"),
  inspectorFace: document.querySelector("#inspectorFace"),
  inspectorBadge: document.querySelector("#inspectorBadge"),
  inspectorName: document.querySelector("#inspectorName"),
  inspectorScore: document.querySelector("#inspectorScore"),
  inspectorPath: document.querySelector("#inspectorPath"),
  inspectorDir: document.querySelector("#inspectorDir"),
  inspectorBbox: document.querySelector("#inspectorBbox"),
  inspectorExportState: document.querySelector("#inspectorExportState"),
  sessionSummary: document.querySelector("#sessionSummary"),
  rejectButton: document.querySelector("#rejectButton"),
  maybeButton: document.querySelector("#maybeButton"),
  confirmButton: document.querySelector("#confirmButton"),
  openOriginalButton: document.querySelector("#openOriginalButton"),
  exportCurrentButton: document.querySelector("#exportCurrentButton"),
  exportButton: document.querySelector("#exportButton"),
  busyOverlay: document.querySelector("#busyOverlay"),
  busyText: document.querySelector("#busyText"),
  busyHint: document.querySelector("#busyHint"),
  busyLogPath: document.querySelector("#busyLogPath"),
  busyLogsButton: document.querySelector("#busyLogsButton"),
};

function setBanner(kind, message) {
  ui.statusBanner.dataset.kind = kind;
  ui.statusBanner.textContent = message;
}

function syncActionState() {
  const runtimeReady = Boolean(state.status?.runtime?.ready);
  const indexReady = Boolean(state.status?.library?.indexReady);
  const hasFolder = Boolean(state.selectedFolder);
  const hasReference = Boolean(state.referenceFile);

  ui.refreshButton.disabled = state.busy;
  ui.resetButton.disabled = state.busy;
  ui.pickFolderButton.disabled = state.busy;
  ui.indexButton.disabled = state.busy || !runtimeReady || !hasFolder;
  ui.searchButton.disabled = state.busy || !runtimeReady || !indexReady || !hasReference;

  if (!runtimeReady) {
    ui.searchButton.textContent = "引擎不可用";
  } else if (!indexReady) {
    ui.searchButton.textContent = "先准备照片库";
  } else if (!hasReference) {
    ui.searchButton.textContent = "先选择参考照";
  } else {
    ui.searchButton.textContent = "开始找照片";
  }
}

function setBusy(busy, message = "处理中...", hint = "首次识别会加载本地模型，可能需要一点时间。") {
  state.busy = busy;
  ui.busyOverlay.hidden = !busy;
  ui.busyText.textContent = message;
  ui.busyHint.textContent = hint;
  ui.busyLogPath.textContent = state.status?.paths?.logsDir || "";

  if (state.busyTimer) {
    window.clearInterval(state.busyTimer);
    state.busyTimer = null;
  }

  if (busy) {
    state.busyStartedAt = Date.now();
    state.busyTimer = window.setInterval(() => {
      const elapsed = Math.round((Date.now() - state.busyStartedAt) / 1000);
      if (elapsed >= 90) {
        ui.busyHint.textContent = `已等待 ${elapsed} 秒。首次使用可能正在下载模型；如果长期停留，请打开日志目录查看 engine.log。`;
      } else if (elapsed >= 30) {
        ui.busyHint.textContent = `已等待 ${elapsed} 秒。模型加载和批量照片处理会比较慢，请保持应用打开。`;
      }
    }, 1000);
  }

  syncActionState();
}

async function call(command, args = {}) {
  if (!invoke) {
    throw new Error("Tauri API unavailable.");
  }
  return invoke(command, args);
}

async function callWithTimeout(command, args, timeoutMs, timeoutMessage) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error(timeoutMessage)), timeoutMs);
  });
  try {
    return await Promise.race([call(command, args), timeout]);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function openLogs() {
  const logsPath = state.status?.paths?.logsDir || "";
  if (state.busy && logsPath) {
    ui.busyHint.textContent = `正在打开日志目录。路径：${logsPath}`;
    ui.busyLogPath.textContent = logsPath;
  } else if (logsPath) {
    setBanner("warning", `正在打开日志目录：${logsPath}`);
  }

  await call("open_logs_dir");

  if (state.busy && logsPath) {
    ui.busyHint.textContent = `已请求打开日志目录。如果 Finder 没有弹出，可手动打开下面路径。`;
  } else if (logsPath) {
    setBanner("success", `已请求打开日志目录：${logsPath}`);
  }
}

function formatPercent(score) {
  return `${Math.round(score * 100)}%`;
}

function dirname(path) {
  return path ? path.replace(/\/[^/]+$/, "") || path : "-";
}

function formatBbox(bbox = []) {
  if (!bbox.length || bbox.length < 4) {
    return "-";
  }
  return bbox.slice(0, 4).map((value) => Math.round(Number(value))).join(", ");
}

function getDecision(item) {
  return item ? state.decisions.get(item.sourceKey) || "maybe" : "maybe";
}

function setDecision(decision) {
  if (!state.selectedResult) {
    return;
  }
  state.decisions.set(state.selectedResult.sourceKey, decision);
  renderResults();
  renderInspector();
}

function getConfirmedResults() {
  const confirmed = state.searchResults.filter((item) => state.decisions.get(item.sourceKey) === "confirmed");
  return confirmed.length > 0 ? confirmed : state.searchResults;
}

function setResultView(view) {
  state.resultView = view;
  renderResults();
}

function selectResult(item) {
  state.selectedResult = item;
  renderResults();
  renderInspector();
}

function syncViewButtons() {
  ui.lightTableViewButton.classList.toggle("view-toggle__button--active", state.resultView === "lightTable");
  ui.stackViewButton.classList.toggle("view-toggle__button--active", state.resultView === "stack");
  ui.gridViewButton.classList.toggle("view-toggle__button--active", state.resultView === "grid");
}

function syncPresetButtons() {
  for (const button of ui.presetButtons) {
    button.classList.toggle("preset-button--active", button.dataset.preset === state.preset);
  }
}

function updateRangeLabels() {
  ui.thresholdValue.textContent = Number(ui.thresholdRange.value).toFixed(2);
  ui.limitValue.textContent = ui.limitRange.value;
}

function applyPreset(name) {
  state.preset = name;
  const preset = presets[name];
  ui.thresholdRange.value = preset.threshold;
  ui.limitRange.value = preset.limit;
  syncPresetButtons();
  updateRangeLabels();
}

function renderStatus() {
  const status = state.status;
  if (!status) {
    return;
  }

  ui.photoCount.textContent = String(status.library.photoCount);
  ui.faceCount.textContent = String(status.library.faceCount);
  ui.indexState.textContent = status.library.indexReady ? "已准备" : "未准备";
  ui.folderPath.value = state.selectedFolder;
  ui.libraryHint.textContent = status.library.indexReady
    ? `已准备 ${status.library.photoCount} 张照片，可以开始搜索。`
    : "选择文件夹后准备照片库。";

  if (ui.runtimeState) {
    ui.runtimeState.textContent = status.runtime.phaseLabel;
  }
  if (ui.dataDir) {
    ui.dataDir.textContent = status.paths.dataDir;
  }
  if (ui.runtimeDir) {
    ui.runtimeDir.textContent = status.paths.runtimeDir;
  }
  if (ui.modelPolicy) {
    ui.modelPolicy.textContent = status.modelPolicy || "";
  }

  if (status.runtime.ready) {
    setBanner("success", `${status.library.photoCount} 张照片 · ${status.library.faceCount} 张人脸 · ${status.library.indexReady ? "照片库已准备" : "等待准备照片库"}`);
  } else {
    setBanner("danger", status.runtime.error || "内置引擎不可用。");
  }
  syncActionState();
}

function renderReferencePreview(src = "", name = "上传一张清晰参考照", hint = "最好是正脸、少遮挡、只有自己。") {
  state.referencePreview = src;
  ui.referencePreview.src = src;
  ui.referencePreview.hidden = !src;
  ui.referenceName.textContent = name;
  ui.referenceHint.textContent = hint;
  ui.inspectorReference.src = src;
  ui.inspectorReference.hidden = !src;
}

function resultStateLabel(item) {
  const decision = getDecision(item);
  if (decision === "confirmed") {
    return "是我";
  }
  if (decision === "rejected") {
    return "不是我";
  }
  return "待确认";
}

function resultStateClass(item) {
  return `result-state--${getDecision(item)}`;
}

function renderResults() {
  syncViewButtons();
  ui.resultsStack.innerHTML = "";
  ui.resultsGrid.innerHTML = "";
  ui.filmstrip.innerHTML = "";

  const total = state.searchResults.length;
  const confirmed = state.searchResults.filter((item) => state.decisions.get(item.sourceKey) === "confirmed").length;
  ui.resultCount.textContent = `${total} 张`;
  ui.sessionSummary.textContent = `${total} 条结果 · ${confirmed} 张已确认`;

  const hasResults = total > 0;
  ui.emptyState.hidden = hasResults;
  ui.lightTableView.hidden = !hasResults || state.resultView !== "lightTable";
  ui.resultsStack.hidden = !hasResults || state.resultView !== "stack";
  ui.resultsGrid.hidden = !hasResults || state.resultView !== "grid";

  if (!hasResults) {
    renderInspector();
    return;
  }

  if (!state.selectedResult) {
    state.selectedResult = state.searchResults[0];
  }

  if (state.resultView === "lightTable") {
    renderLightTable();
  } else if (state.resultView === "stack") {
    renderStackCards();
  } else {
    renderGridCards();
  }

  renderInspector();
}

function renderLightTable() {
  const item = state.selectedResult || state.searchResults[0];
  ui.lightTableImage.src = item.annotatedImage;
  ui.lightTableName.textContent = item.originalName;
  ui.lightTableScore.textContent = formatPercent(item.score);

  for (const candidate of state.searchResults) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "filmstrip-card";
    if (candidate.sourceKey === item.sourceKey) {
      button.dataset.active = "true";
    }
    button.innerHTML = `
      <img src="${candidate.annotatedImage}" alt="${candidate.originalName}" />
      <span>${formatPercent(candidate.score)}</span>
    `;
    button.addEventListener("click", () => selectResult(candidate));
    ui.filmstrip.appendChild(button);
  }
}

function renderStackCards() {
  const visibleCards = state.searchResults.slice(0, Math.min(state.searchResults.length, 8));

  const header = document.createElement("div");
  header.className = "results-stack__summary";
  header.innerHTML = `
    <div>
      <strong>平行堆叠预览</strong>
      <span>点击任意照片进入筛选台，或展开网格批量查看。</span>
    </div>
    <button class="secondary-button secondary-button--strong" type="button" id="stackExpandButton">展开网格</button>
  `;
  ui.resultsStack.appendChild(header);

  const stage = document.createElement("div");
  stage.className = "results-stack__stage";

  visibleCards.forEach((item, index) => {
    const stackCard = document.createElement("button");
    stackCard.type = "button";
    stackCard.className = "stack-card";
    if (state.selectedResult?.sourceKey === item.sourceKey) {
      stackCard.dataset.active = "true";
    }
    stackCard.style.setProperty("--stack-index", String(index));
    stackCard.innerHTML = `
      <img src="${item.annotatedImage}" alt="${item.originalName}" />
      <div class="stack-card__footer">
        <strong title="${item.originalName}">${item.originalName}</strong>
        <span>${formatPercent(item.score)}</span>
      </div>
    `;
    stackCard.addEventListener("click", () => {
      state.resultView = "lightTable";
      selectResult(item);
    });
    stage.appendChild(stackCard);
  });

  ui.resultsStack.appendChild(stage);
  ui.resultsStack.querySelector("#stackExpandButton")?.addEventListener("click", () => setResultView("grid"));
}

function makeResultCard(item) {
  const card = document.createElement("article");
  card.className = "result-card";
  card.dataset.decision = getDecision(item);
  if (state.selectedResult?.sourceKey === item.sourceKey) {
    card.dataset.active = "true";
  }
  card.innerHTML = `
    <button class="result-card__preview" type="button">
      <img src="${item.annotatedImage}" alt="${item.originalName}" />
      <span class="result-card__score">${formatPercent(item.score)}</span>
    </button>
    <div class="result-card__meta">
      <div class="result-card__head">
        <strong title="${item.originalName}">${item.originalName}</strong>
        <span class="result-card__state ${resultStateClass(item)}">${resultStateLabel(item)}</span>
      </div>
      <span title="${dirname(item.photoPath)}">${dirname(item.photoPath)}</span>
    </div>
    <div class="result-card__actions">
      <button class="card-tool-button" type="button" data-role="confirm">是我</button>
      <button class="card-tool-button" type="button" data-role="reject">不是我</button>
    </div>
  `;
  card.querySelector(".result-card__preview")?.addEventListener("click", () => {
    state.resultView = "lightTable";
    selectResult(item);
  });
  card.querySelector('[data-role="confirm"]')?.addEventListener("click", (event) => {
    event.stopPropagation();
    state.selectedResult = item;
    setDecision("confirmed");
  });
  card.querySelector('[data-role="reject"]')?.addEventListener("click", (event) => {
    event.stopPropagation();
    state.selectedResult = item;
    setDecision("rejected");
  });
  return card;
}

function renderGridCards() {
  for (const item of state.searchResults) {
    ui.resultsGrid.appendChild(makeResultCard(item));
  }
}

function renderInspector() {
  const item = state.selectedResult;
  const disabled = !item;

  ui.rejectButton.disabled = disabled;
  ui.maybeButton.disabled = disabled;
  ui.confirmButton.disabled = disabled;
  ui.openOriginalButton.disabled = disabled;
  ui.exportCurrentButton.disabled = disabled;
  ui.exportButton.disabled = state.searchResults.length === 0;

  ui.rejectButton.dataset.active = item && getDecision(item) === "rejected" ? "true" : "false";
  ui.maybeButton.dataset.active = item && getDecision(item) === "maybe" ? "true" : "false";
  ui.confirmButton.dataset.active = item && getDecision(item) === "confirmed" ? "true" : "false";

  if (!item) {
    ui.inspectorImage.removeAttribute("src");
    ui.inspectorImage.hidden = true;
    ui.inspectorFace.removeAttribute("src");
    ui.inspectorFace.hidden = true;
    ui.inspectorBadge.textContent = "-";
    ui.inspectorName.textContent = "尚未选择";
    ui.inspectorScore.textContent = "相似度 -";
    ui.inspectorPath.textContent = "-";
    ui.inspectorDir.textContent = "-";
    ui.inspectorBbox.textContent = "-";
    ui.inspectorExportState.textContent = "未导出";
    ui.lightTableImage.removeAttribute("src");
    ui.lightTableName.textContent = "尚未选择";
    ui.lightTableScore.textContent = "-";
    return;
  }

  ui.inspectorImage.src = item.annotatedImage;
  ui.inspectorImage.hidden = false;
  if (item.faceThumb) {
    ui.inspectorFace.src = item.faceThumb;
    ui.inspectorFace.hidden = false;
  } else {
    ui.inspectorFace.removeAttribute("src");
    ui.inspectorFace.hidden = true;
  }
  ui.inspectorBadge.textContent = formatPercent(item.score);
  ui.inspectorName.textContent = item.originalName;
  ui.inspectorScore.textContent = `相似度 ${formatPercent(item.score)} · ${resultStateLabel(item)}`;
  ui.inspectorPath.textContent = item.photoPath;
  ui.inspectorDir.textContent = dirname(item.photoPath);
  ui.inspectorBbox.textContent = formatBbox(item.bbox);
  ui.inspectorExportState.textContent = state.exportedKeys.has(item.sourceKey) ? "已导出" : "未导出";
}

async function refreshStatus() {
  state.status = await call("app_status");
  renderStatus();
}

async function pickFolder() {
  const selected = await call("choose_folder", { prompt: "选择照片文件夹" });
  if (!selected) {
    return;
  }
  state.selectedFolder = selected;
  renderStatus();
  syncActionState();
}

async function indexFolder() {
  if (!state.selectedFolder) {
    throw new Error("请先选择照片文件夹。");
  }

  setBusy(true, "正在准备照片库...", "首次处理会加载人脸模型；照片多时会逐张提取人脸，请保持应用打开。");
  try {
    const report = await callWithTimeout(
      "index_folder",
      {
        folder: state.selectedFolder,
        recursive: ui.recursiveToggle.checked,
      },
      31 * 60 * 1000,
      "准备照片库超时。请打开日志目录查看 engine.log，确认模型下载或照片处理是否卡住。",
    );
    await refreshStatus();
    setBanner("success", `照片库已准备：新增 ${report.addedPhotos} 张照片、${report.addedFaces} 张人脸。`);
  } finally {
    setBusy(false);
  }
}

async function searchReference() {
  if (!state.referenceFile) {
    throw new Error("请先选择参考照片。");
  }
  if (!state.status?.library?.indexReady) {
    throw new Error("请先选择照片文件夹，并点击“准备照片库”。");
  }

  setBusy(true, "正在找照片...", "正在检测参考照并比对本地照片库。首次使用可能需要加载模型。");
  try {
    const bytes = Array.from(new Uint8Array(await state.referenceFile.arrayBuffer()));
    const response = await callWithTimeout(
      "search_reference",
      {
        filename: state.referenceFile.name,
        bytes,
        threshold: Number(ui.thresholdRange.value),
        limit: Number(ui.limitRange.value),
      },
      9 * 60 * 1000,
      "搜索超时。请打开日志目录查看 engine.log，确认模型下载或本地识别是否卡住。",
    );

    if (response.referencePreview) {
      renderReferencePreview(response.referencePreview, state.referenceFile.name, response.warning || "参考照已用于本次搜索。");
    }
    state.searchResults = response.results;
    state.selectedResult = response.results[0] || null;
    state.decisions.clear();
    state.exportedKeys.clear();
    state.resultView = response.results.length > 0 ? "lightTable" : "grid";
    renderResults();

    if (response.resultCount > 0) {
      setBanner("success", `找到 ${response.resultCount} 张候选照片。先确认，再导出。`);
    } else {
      setBanner("warning", "没有找到候选照片，可以切到“尽量多找”后重试。");
    }
  } finally {
    setBusy(false);
  }
}

async function exportKeys(sourceKeys, message) {
  const parentDir = await call("choose_folder", { prompt: "选择导出目录" });
  if (!parentDir) {
    return;
  }

  setBusy(true, "正在导出照片...");
  try {
    const response = await call("export_matches", {
      parentDir,
      sourceKeys,
    });
    for (const key of sourceKeys) {
      state.exportedKeys.add(key);
    }
    renderResults();
    setBanner("success", `${message}：${response.exportPath}`);
    await call("reveal_path", { path: response.exportPath });
  } finally {
    setBusy(false);
  }
}

async function exportMatches() {
  if (state.searchResults.length === 0) {
    throw new Error("当前没有可导出的匹配结果。");
  }
  const sourceKeys = getConfirmedResults().map((item) => item.sourceKey);
  await exportKeys(sourceKeys, `已导出 ${sourceKeys.length} 张照片`);
}

async function exportCurrentMatch() {
  if (!state.selectedResult) {
    throw new Error("请先选择一张结果照片。");
  }
  await exportKeys([state.selectedResult.sourceKey], "已导出当前照片");
}

async function resetIndex() {
  const confirmed = window.confirm("确定清空当前照片库索引吗？原图不会被删除。");
  if (!confirmed) {
    return;
  }

  setBusy(true, "正在清空照片库...");
  try {
    const stats = await call("reset_index");
    state.searchResults = [];
    state.selectedResult = null;
    state.decisions.clear();
    state.exportedKeys.clear();
    state.status.library = stats;
    renderResults();
    renderStatus();
    setBanner("warning", "照片库已清空。");
  } finally {
    setBusy(false);
  }
}

function handleReferenceChange(event) {
  const [file] = event.target.files || [];
  state.referenceFile = file || null;
  syncActionState();

  if (!file) {
    renderReferencePreview();
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    renderReferencePreview(reader.result, file.name, "参考照已选择，可以开始搜索。");
  };
  reader.readAsDataURL(file);
}

function clearReference() {
  state.referenceFile = null;
  ui.referenceInput.value = "";
  renderReferencePreview();
  syncActionState();
}

function bindEvents() {
  ui.refreshButton.addEventListener("click", () => refreshStatus().catch(handleError));
  ui.resetButton.addEventListener("click", () => resetIndex().catch(handleError));
  ui.logsButton.addEventListener("click", () => openLogs().catch(handleError));
  ui.revealDataButton.addEventListener("click", () => call("reveal_path", { path: state.status?.paths?.dataDir || "" }).catch(handleError));
  ui.pickFolderButton.addEventListener("click", () => pickFolder().catch(handleError));
  ui.indexButton.addEventListener("click", () => indexFolder().catch(handleError));
  ui.searchButton.addEventListener("click", () => searchReference().catch(handleError));
  ui.busyLogsButton.addEventListener("click", () => openLogs().catch(handleError));
  ui.exportButton.addEventListener("click", () => exportMatches().catch(handleError));
  ui.exportCurrentButton.addEventListener("click", () => exportCurrentMatch().catch(handleError));
  ui.referenceInput.addEventListener("change", handleReferenceChange);
  ui.clearReferenceButton.addEventListener("click", clearReference);
  ui.thresholdRange.addEventListener("input", updateRangeLabels);
  ui.limitRange.addEventListener("input", updateRangeLabels);
  ui.lightTableViewButton.addEventListener("click", () => setResultView("lightTable"));
  ui.stackViewButton.addEventListener("click", () => setResultView("stack"));
  ui.gridViewButton.addEventListener("click", () => setResultView("grid"));
  ui.rejectButton.addEventListener("click", () => setDecision("rejected"));
  ui.maybeButton.addEventListener("click", () => setDecision("maybe"));
  ui.confirmButton.addEventListener("click", () => setDecision("confirmed"));
  ui.openOriginalButton.addEventListener("click", () => {
    if (state.selectedResult) {
      call("reveal_path", { path: state.selectedResult.photoPath }).catch(handleError);
    }
  });
  for (const button of ui.presetButtons) {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  }
}

function handleError(error) {
  setBusy(false);
  setBanner("danger", error?.message || String(error));
}

async function bootstrap() {
  applyPreset("balanced");
  renderReferencePreview();
  renderResults();
  bindEvents();
  syncActionState();
  await refreshStatus();
}

bootstrap().catch(handleError);
