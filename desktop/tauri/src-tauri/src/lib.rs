use serde::{Deserialize, Serialize};
use std::env::consts::{ARCH, OS};
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, State};

#[derive(Default)]
struct SharedRuntime {
    inner: Arc<Mutex<RuntimeState>>,
}

#[derive(Default)]
struct RuntimeState {
    last_error: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AppStatus {
    runtime: RuntimeStatus,
    library: LibraryStats,
    paths: AppPaths,
    model_policy: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    ready: bool,
    failed: bool,
    error: Option<String>,
    phase_label: String,
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct LibraryStats {
    data_dir: String,
    photo_dir: String,
    thumb_dir: String,
    export_dir: String,
    index_ready: bool,
    photo_count: usize,
    face_count: usize,
    vector_count: usize,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AppPaths {
    data_dir: String,
    runtime_dir: String,
    logs_dir: String,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct IndexReport {
    selected: usize,
    added_photos: usize,
    added_faces: usize,
    duplicates: usize,
    no_face: usize,
    failed: usize,
    folder: String,
    finished_at: String,
    library_photos: usize,
    library_faces: usize,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SearchResult {
    source_key: String,
    original_name: String,
    photo_path: String,
    thumb_path: String,
    score: f64,
    bbox: Vec<f64>,
    annotated_image: String,
    face_thumb: Option<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SearchResponse {
    warning: Option<String>,
    reference_preview: String,
    results: Vec<SearchResult>,
    result_count: usize,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExportResponse {
    export_path: String,
    copied: usize,
}

fn app_support_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let mut dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("failed to resolve app data dir: {err}"))?;
    dir.push("runtime");
    Ok(dir)
}

fn logs_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_support_dir(app)?.join("logs"))
}

fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_support_dir(app)?.join("data"))
}

fn temp_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_support_dir(app)?.join("tmp"))
}

fn bundled_backend_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|err| format!("failed to resolve resource dir: {err}"))?;

    let direct = resource_dir.join("backend");
    if direct.exists() {
        return Ok(direct);
    }

    let nested = resource_dir.join("_up_").join("resources").join("backend");
    if nested.exists() {
        return Ok(nested);
    }

    Ok(direct)
}

fn bundled_backend_executable(app: &AppHandle) -> Result<PathBuf, String> {
    let root = bundled_backend_dir(app)?;
    let binary_name = if cfg!(target_os = "windows") {
        "find-myself-backend.exe"
    } else {
        "find-myself-backend"
    };
    let collected = root.join("find-myself-backend").join(binary_name);
    if collected.exists() {
        return Ok(collected);
    }
    Ok(root.join(binary_name))
}

fn engine_log(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(logs_dir(app)?.join("engine.log"))
}

fn ensure_dirs(app: &AppHandle) -> Result<(), String> {
    fs::create_dir_all(app_support_dir(app)?).map_err(io_error)?;
    fs::create_dir_all(logs_dir(app)?).map_err(io_error)?;
    fs::create_dir_all(temp_dir(app)?).map_err(io_error)?;
    let data = data_dir(app)?;
    fs::create_dir_all(data.join("photos")).map_err(io_error)?;
    fs::create_dir_all(data.join("thumbs")).map_err(io_error)?;
    fs::create_dir_all(data.join("exports")).map_err(io_error)?;
    Ok(())
}

fn io_error(err: io::Error) -> String {
    err.to_string()
}

fn is_runtime_ready(app: &AppHandle) -> bool {
    bundled_backend_executable(app)
        .map(|path| path.exists())
        .unwrap_or(false)
}

fn runtime_status_for(state: &RuntimeState, app: &AppHandle) -> RuntimeStatus {
    if is_runtime_ready(app) {
        RuntimeStatus {
            ready: true,
            failed: false,
            error: None,
            phase_label: format!("原生桌面引擎已内置（{} / {}）", OS, ARCH),
        }
    } else {
        RuntimeStatus {
            ready: false,
            failed: true,
            error: state
                .last_error
                .clone()
                .or_else(|| Some("bundled engine executable is missing".into())),
            phase_label: "内置引擎缺失".into(),
        }
    }
}

fn append_log(app: &AppHandle, content: &[u8]) -> Result<(), String> {
    if content.is_empty() {
        return Ok(());
    }

    let path = engine_log(app)?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(io_error)?;
    file.write_all(content).map_err(io_error)?;
    file.write_all(b"\n").map_err(io_error)?;
    Ok(())
}

#[cfg(target_os = "windows")]
fn engine_command(executable: &PathBuf) -> Command {
    let mut command = Command::new(executable);
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

#[cfg(not(target_os = "windows"))]
fn engine_command(executable: &PathBuf) -> Command {
    Command::new(executable)
}

fn engine_timeout(args: &[String]) -> Duration {
    match args.first().map(|item| item.as_str()) {
        Some("stats") => Duration::from_secs(30),
        Some("search-image") => Duration::from_secs(9 * 60),
        Some("index-folder") => Duration::from_secs(30 * 60),
        Some("export-matches") => Duration::from_secs(10 * 60),
        Some("reset-index") => Duration::from_secs(60),
        _ => Duration::from_secs(5 * 60),
    }
}

fn run_engine(app: &AppHandle, args: &[String]) -> Result<String, String> {
    ensure_dirs(app)?;

    let executable = bundled_backend_executable(app)?;
    let timeout = engine_timeout(args);
    let started = Instant::now();
    let mut child = engine_command(&executable)
        .args(args)
        .env("FIND_MYSELF_DATA_DIR", data_dir(app)?)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("failed to run bundled engine: {err}"))?;

    loop {
        match child
            .try_wait()
            .map_err(|err| format!("failed to wait for bundled engine: {err}"))?
        {
            Some(_) => break,
            None if started.elapsed() >= timeout => {
                let _ = child.kill();
                let output = child
                    .wait_with_output()
                    .map_err(|err| format!("failed to collect timed-out engine output: {err}"))?;
                let _ = append_log(app, &output.stderr);
                let timeout_message = format!(
                    "engine timeout after {} seconds while running {:?}",
                    timeout.as_secs(),
                    args
                );
                let _ = append_log(app, timeout_message.as_bytes());
                return Err("本地识别引擎执行超时。首次使用可能卡在模型下载；请检查网络，或打开日志目录查看 engine.log。".into());
            }
            None => thread::sleep(Duration::from_millis(200)),
        }
    }

    let output = child
        .wait_with_output()
        .map_err(|err| format!("failed to collect bundled engine output: {err}"))?;

    let _ = append_log(app, &output.stderr);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        let message = if !stderr.trim().is_empty() {
            stderr.trim().to_string()
        } else if !stdout.trim().is_empty() {
            stdout.trim().to_string()
        } else {
            format!("engine exited with status {}", output.status)
        };
        return Err(message);
    }

    String::from_utf8(output.stdout)
        .map(|text| text.trim().to_string())
        .map_err(|err| format!("engine returned invalid UTF-8: {err}"))
}

fn write_temp_file(app: &AppHandle, filename: &str, bytes: &[u8]) -> Result<PathBuf, String> {
    let extension = PathBuf::from(filename)
        .extension()
        .and_then(|item| item.to_str())
        .unwrap_or("bin")
        .to_string();
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|err| err.to_string())?
        .as_millis();
    let path = temp_dir(app)?.join(format!("input-{stamp}.{extension}"));
    fs::write(&path, bytes).map_err(io_error)?;
    Ok(path)
}

fn choose_folder_macos(prompt: &str) -> Result<String, String> {
    let escaped = prompt.replace('"', "\\\"");
    let script = format!("POSIX path of (choose folder with prompt \"{escaped}\")");
    let output = Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .map_err(|err| format!("failed to open folder picker: {err}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(stderr.trim().to_string());
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn choose_folder_windows(prompt: &str) -> Result<String, String> {
    let escaped = prompt.replace('\'', "''");
    let script = format!(
        "Add-Type -AssemblyName System.Windows.Forms; \
         [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; \
         $dialog = New-Object System.Windows.Forms.FolderBrowserDialog; \
         $dialog.Description = '{escaped}'; \
         if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{ \
           Write-Output $dialog.SelectedPath \
         }} else {{ exit 1 }}"
    );

    let output = Command::new("powershell.exe")
        .args(["-NoProfile", "-Sta", "-Command", &script])
        .output()
        .map_err(|err| format!("failed to open folder picker: {err}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let message = stderr.trim();
        return Err(if message.is_empty() {
            "folder picker was cancelled".to_string()
        } else {
            message.to_string()
        });
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn choose_folder_native(prompt: &str) -> Result<String, String> {
    if cfg!(target_os = "macos") {
        return choose_folder_macos(prompt);
    }
    if cfg!(target_os = "windows") {
        return choose_folder_windows(prompt);
    }
    Err("folder picker is not implemented on this platform".to_string())
}

fn open_path(path: PathBuf, reveal: bool) -> Result<(), String> {
    if cfg!(target_os = "macos") {
        let mut command = Command::new("open");
        if reveal && path.is_file() {
            command.arg("-R").arg(path);
        } else {
            command.arg(path);
        }
        let output = command
            .output()
            .map_err(|err| format!("failed to open path: {err}"))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(if stderr.trim().is_empty() {
                format!("open exited with status {}", output.status)
            } else {
                stderr.trim().to_string()
            });
        }
        return Ok(());
    }

    if cfg!(target_os = "windows") {
        let mut command = Command::new("explorer.exe");
        if reveal && path.is_file() {
            command.arg(format!("/select,{}", path.display()));
        } else {
            command.arg(path);
        }
        let output = command
            .output()
            .map_err(|err| format!("failed to open path: {err}"))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(if stderr.trim().is_empty() {
                format!("explorer exited with status {}", output.status)
            } else {
                stderr.trim().to_string()
            });
        }
        return Ok(());
    }

    let output = Command::new("xdg-open")
        .arg(path)
        .output()
        .map_err(|err| format!("failed to open path: {err}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(if stderr.trim().is_empty() {
            format!("xdg-open exited with status {}", output.status)
        } else {
            stderr.trim().to_string()
        });
    }
    Ok(())
}

fn update_last_error(shared: &State<SharedRuntime>, message: Option<String>) {
    if let Ok(mut state) = shared.inner.lock() {
        state.last_error = message;
    }
}

fn current_status(app: &AppHandle, shared: &SharedRuntime) -> Result<AppStatus, String> {
    ensure_dirs(app)?;
    let state = shared
        .inner
        .lock()
        .map_err(|_| "runtime state poisoned".to_string())?;
    let runtime = runtime_status_for(&state, app);
    drop(state);

    let library = if runtime.ready {
        let raw = run_engine(app, &[String::from("stats")])?;
        serde_json::from_str::<LibraryStats>(&raw)
            .map_err(|err| format!("invalid stats payload: {err}"))?
    } else {
        LibraryStats {
            data_dir: data_dir(app)?.display().to_string(),
            photo_dir: data_dir(app)?.join("photos").display().to_string(),
            thumb_dir: data_dir(app)?.join("thumbs").display().to_string(),
            export_dir: data_dir(app)?.join("exports").display().to_string(),
            index_ready: false,
            photo_count: 0,
            face_count: 0,
            vector_count: 0,
        }
    };

    Ok(AppStatus {
        runtime,
        library,
        paths: AppPaths {
            data_dir: data_dir(app)?.display().to_string(),
            runtime_dir: bundled_backend_dir(app)?.display().to_string(),
            logs_dir: logs_dir(app)?.display().to_string(),
        },
        model_policy: "桌面应用已去掉 Streamlit 页面，前端直接调用本地识别引擎。默认仍不随安装包分发 InsightFace buffalo_l 模型权重；首次真正执行识别时，仍由内置引擎在本地下载模型。".into(),
    })
}

#[tauri::command]
fn app_status(app: AppHandle, shared: State<SharedRuntime>) -> Result<AppStatus, String> {
    current_status(&app, &shared)
}

#[tauri::command]
fn choose_folder(prompt: String) -> Result<String, String> {
    choose_folder_native(&prompt)
}

#[tauri::command]
fn index_folder(
    app: AppHandle,
    shared: State<SharedRuntime>,
    folder: String,
    recursive: bool,
) -> Result<IndexReport, String> {
    let args = vec![
        String::from("index-folder"),
        String::from("--folder"),
        folder,
        String::from("--recursive"),
        if recursive {
            String::from("true")
        } else {
            String::from("false")
        },
    ];

    let raw = run_engine(&app, &args)?;
    let report = serde_json::from_str::<IndexReport>(&raw)
        .map_err(|err| format!("invalid index payload: {err}"))?;
    update_last_error(&shared, None);
    Ok(report)
}

#[tauri::command]
fn search_reference(
    app: AppHandle,
    shared: State<SharedRuntime>,
    filename: String,
    bytes: Vec<u8>,
    threshold: f64,
    limit: usize,
) -> Result<SearchResponse, String> {
    let path = write_temp_file(&app, &filename, &bytes)?;
    let args = vec![
        String::from("search-image"),
        String::from("--image"),
        path.display().to_string(),
        String::from("--threshold"),
        threshold.to_string(),
        String::from("--limit"),
        limit.to_string(),
    ];

    let raw = run_engine(&app, &args)?;
    let response = serde_json::from_str::<SearchResponse>(&raw)
        .map_err(|err| format!("invalid search payload: {err}"))?;
    let _ = fs::remove_file(path);
    update_last_error(&shared, None);
    Ok(response)
}

#[tauri::command]
fn export_matches(
    app: AppHandle,
    shared: State<SharedRuntime>,
    parent_dir: String,
    source_keys: Vec<String>,
) -> Result<ExportResponse, String> {
    let payload = serde_json::to_string(&source_keys).map_err(|err| err.to_string())?;
    let args = vec![
        String::from("export-matches"),
        String::from("--parent-dir"),
        parent_dir,
        String::from("--source-keys-json"),
        payload,
    ];
    let raw = run_engine(&app, &args)?;
    let response = serde_json::from_str::<ExportResponse>(&raw)
        .map_err(|err| format!("invalid export payload: {err}"))?;
    update_last_error(&shared, None);
    Ok(response)
}

#[tauri::command]
fn reset_index(app: AppHandle, shared: State<SharedRuntime>) -> Result<LibraryStats, String> {
    let raw = run_engine(&app, &[String::from("reset-index")])?;
    let stats = serde_json::from_str::<LibraryStats>(&raw)
        .map_err(|err| format!("invalid reset payload: {err}"))?;
    update_last_error(&shared, None);
    Ok(stats)
}

#[tauri::command]
fn open_logs_dir(app: AppHandle) -> Result<(), String> {
    ensure_dirs(&app)?;
    open_path(logs_dir(&app)?, false)
}

#[tauri::command]
fn reveal_path(path: String) -> Result<(), String> {
    let target = PathBuf::from(path);
    open_path(target, true)
}

pub fn run() {
    tauri::Builder::default()
        .manage(SharedRuntime::default())
        .setup(|app| {
            ensure_dirs(&app.handle())
                .map_err(|err| -> Box<dyn std::error::Error> { err.into() })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            app_status,
            choose_folder,
            index_folder,
            search_reference,
            export_matches,
            reset_index,
            open_logs_dir,
            reveal_path
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
