use serde::Serialize;
use std::fs::{self, OpenOptions};
use std::io;
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, State};

#[derive(Default)]
struct SharedRuntime {
    inner: Arc<Mutex<RuntimeState>>,
}

#[derive(Default)]
struct RuntimeState {
    install_phase: InstallPhase,
    backend: Option<BackendProcess>,
    last_error: Option<String>,
}

#[derive(Default)]
enum InstallPhase {
    #[default]
    Missing,
    Installing,
    Ready,
    Failed(String),
}

struct BackendProcess {
    child: Child,
    url: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AppStatus {
    runtime: RuntimeStatus,
    backend: BackendStatus,
    paths: AppPaths,
    model_policy: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    ready: bool,
    installing: bool,
    failed: bool,
    error: Option<String>,
    phase_label: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendStatus {
    running: bool,
    url: Option<String>,
    phase_label: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AppPaths {
    data_dir: String,
    runtime_dir: String,
    logs_dir: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct StartBackendResponse {
    url: String,
}

fn app_support_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let mut dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("failed to resolve app data dir: {err}"))?;
    dir.push("runtime");
    Ok(dir)
}

fn runtime_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_support_dir(app)?.join(".venv"))
}

fn logs_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_support_dir(app)?.join("logs"))
}

fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_support_dir(app)?.join("data"))
}

fn bundled_python_app_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .resource_dir()
        .map_err(|err| format!("failed to resolve resource dir: {err}"))?
        .join("python-app"))
}

fn runtime_python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(runtime_dir(app)?.join("bin").join("python"))
}

fn streamlit_log(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(logs_dir(app)?.join("streamlit.log"))
}

fn install_log(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(logs_dir(app)?.join("runtime-install.log"))
}

fn ensure_dirs(app: &AppHandle) -> Result<(), String> {
    fs::create_dir_all(app_support_dir(app)?).map_err(io_error)?;
    fs::create_dir_all(logs_dir(app)?).map_err(io_error)?;
    let data = data_dir(app)?;
    fs::create_dir_all(data.join("photos")).map_err(io_error)?;
    fs::create_dir_all(data.join("thumbs")).map_err(io_error)?;
    fs::create_dir_all(data.join("exports")).map_err(io_error)?;
    Ok(())
}

fn io_error(err: io::Error) -> String {
    err.to_string()
}

fn file_for_append(path: PathBuf) -> Result<Stdio, String> {
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(io_error)?;
    Ok(Stdio::from(file))
}

fn python3_cmd() -> &'static str {
    "python3"
}

fn run_logged_command(program: &str, args: &[String], log_file: PathBuf) -> Result<(), String> {
    let stdout = file_for_append(log_file.clone())?;
    let stderr = file_for_append(log_file)?;
    let status = Command::new(program)
        .args(args)
        .stdout(stdout)
        .stderr(stderr)
        .status()
        .map_err(|err| format!("failed to run {program}: {err}"))?;

    if !status.success() {
        return Err(format!("{program} exited with status {status}"));
    }
    Ok(())
}

fn is_runtime_ready(app: &AppHandle) -> bool {
    runtime_python(app).map(|path| path.exists()).unwrap_or(false)
}

fn choose_free_port() -> Result<u16, String> {
    for port in 8501..8600 {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }
    Err("no free localhost port found between 8501 and 8599".into())
}

fn wait_for_server(url: &str, timeout: Duration) -> Result<(), String> {
    let started = Instant::now();
    let address = url.trim_start_matches("http://");
    while started.elapsed() < timeout {
        if TcpStream::connect(address).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(500));
    }
    Err(format!("backend did not start within {} seconds", timeout.as_secs()))
}

fn runtime_status_for(state: &RuntimeState, app: &AppHandle) -> RuntimeStatus {
    let runtime_exists = is_runtime_ready(app);
    match &state.install_phase {
        InstallPhase::Installing => RuntimeStatus {
            ready: false,
            installing: true,
            failed: false,
            error: None,
            phase_label: "安装中".into(),
        },
        InstallPhase::Ready if runtime_exists => RuntimeStatus {
            ready: true,
            installing: false,
            failed: false,
            error: None,
            phase_label: "已就绪".into(),
        },
        InstallPhase::Failed(err) => RuntimeStatus {
            ready: false,
            installing: false,
            failed: true,
            error: Some(err.clone()),
            phase_label: "安装失败".into(),
        },
        _ if runtime_exists => RuntimeStatus {
            ready: true,
            installing: false,
            failed: false,
            error: None,
            phase_label: "已就绪".into(),
        },
        _ => RuntimeStatus {
            ready: false,
            installing: false,
            failed: false,
            error: None,
            phase_label: "未安装".into(),
        },
    }
}

fn backend_status_for(state: &mut RuntimeState) -> BackendStatus {
    let mut running = false;
    let mut url = None;

    if let Some(process) = state.backend.as_mut() {
      match process.child.try_wait() {
          Ok(None) => {
              running = true;
              url = Some(process.url.clone());
          }
          Ok(Some(_)) => {
              state.backend = None;
          }
          Err(err) => {
              state.last_error = Some(format!("failed to query backend process: {err}"));
              state.backend = None;
          }
      }
    }

    BackendStatus {
        running,
        url: url.clone(),
        phase_label: if running {
            "运行中".into()
        } else {
            "未启动".into()
        },
    }
}

fn current_status(app: &AppHandle, shared: &SharedRuntime) -> Result<AppStatus, String> {
    ensure_dirs(app)?;
    let mut state = shared.inner.lock().map_err(|_| "runtime state poisoned".to_string())?;
    let runtime = runtime_status_for(&state, app);
    let backend = backend_status_for(&mut state);

    Ok(AppStatus {
        runtime,
        backend,
        paths: AppPaths {
            data_dir: data_dir(app)?.display().to_string(),
            runtime_dir: runtime_dir(app)?.display().to_string(),
            logs_dir: logs_dir(app)?.display().to_string(),
        },
        model_policy: "默认不随安装包分发 InsightFace buffalo_l 模型权重。首次真正使用识别功能时，运行环境仍会按 InsightFace 现有机制在本地下载模型；若未来获得分发授权或替换为允许再分发的模型，再改为随安装包分发。".into(),
    })
}

fn install_runtime_inner(app: &AppHandle) -> Result<(), String> {
    ensure_dirs(app)?;
    let runtime = runtime_dir(app)?;
    let log_file = install_log(app)?;
    let python_app = bundled_python_app_dir(app)?;
    let requirements = python_app.join("requirements.txt");

    if is_runtime_ready(app) {
        return Ok(());
    }

    if runtime.exists() {
        fs::remove_dir_all(&runtime).map_err(io_error)?;
    }

    run_logged_command(
        python3_cmd(),
        &[
            "-m".into(),
            "venv".into(),
            runtime.display().to_string(),
        ],
        log_file.clone(),
    )?;

    let runtime_python_path = runtime_python(app)?;
    let runtime_python_text = runtime_python_path.display().to_string();

    run_logged_command(
        &runtime_python_text,
        &[
            "-m".into(),
            "pip".into(),
            "install".into(),
            "--upgrade".into(),
            "pip".into(),
            "setuptools".into(),
            "wheel".into(),
        ],
        log_file.clone(),
    )?;

    run_logged_command(
        &runtime_python_text,
        &[
            "-m".into(),
            "pip".into(),
            "install".into(),
            "--only-binary=insightface".into(),
            "insightface==1.0.1".into(),
        ],
        log_file.clone(),
    )?;

    run_logged_command(
        &runtime_python_text,
        &[
            "-m".into(),
            "pip".into(),
            "install".into(),
            "-r".into(),
            requirements.display().to_string(),
        ],
        log_file,
    )?;

    Ok(())
}

fn stop_backend_inner(state: &mut RuntimeState) {
    if let Some(mut process) = state.backend.take() {
        let _ = process.child.kill();
        let _ = process.child.wait();
    }
}

#[tauri::command]
fn app_status(app: AppHandle, shared: State<SharedRuntime>) -> Result<AppStatus, String> {
    current_status(&app, &shared)
}

#[tauri::command]
fn install_runtime(app: AppHandle, shared: State<SharedRuntime>) -> Result<(), String> {
    ensure_dirs(&app)?;
    {
        let mut state = shared.inner.lock().map_err(|_| "runtime state poisoned".to_string())?;
        if matches!(state.install_phase, InstallPhase::Installing) {
            return Ok(());
        }
        if is_runtime_ready(&app) {
            state.install_phase = InstallPhase::Ready;
            return Ok(());
        }
        state.install_phase = InstallPhase::Installing;
        state.last_error = None;
    }

    let app_handle = app.clone();
    let shared_runtime = shared.inner.clone();
    thread::spawn(move || {
        let result = install_runtime_inner(&app_handle);
        if let Ok(mut state) = shared_runtime.lock() {
            match result {
                Ok(()) => {
                    state.install_phase = InstallPhase::Ready;
                    state.last_error = None;
                }
                Err(err) => {
                    state.install_phase = InstallPhase::Failed(err.clone());
                    state.last_error = Some(err);
                }
            }
        }
    });

    Ok(())
}

#[tauri::command]
fn start_backend(app: AppHandle, shared: State<SharedRuntime>) -> Result<StartBackendResponse, String> {
    ensure_dirs(&app)?;

    {
        let mut state = shared.inner.lock().map_err(|_| "runtime state poisoned".to_string())?;
        if let Some(process) = state.backend.as_mut() {
            if process.child.try_wait().map_err(|err| err.to_string())?.is_none() {
                return Ok(StartBackendResponse {
                    url: process.url.clone(),
                });
            }
            state.backend = None;
        }
    }

    if !is_runtime_ready(&app) {
        return Err("runtime is not installed yet".into());
    }

    let port = choose_free_port()?;
    let url = format!("http://127.0.0.1:{port}");
    let log_file = streamlit_log(&app)?;
    let data_path = data_dir(&app)?;
    let python_app = bundled_python_app_dir(&app)?;
    let python = runtime_python(&app)?;
    let app_file = python_app.join("app.py");

    let stdout = file_for_append(log_file.clone())?;
    let stderr = file_for_append(log_file)?;
    let child = Command::new(&python)
        .arg("-m")
        .arg("streamlit")
        .arg("run")
        .arg(app_file)
        .arg("--server.address")
        .arg("127.0.0.1")
        .arg("--server.port")
        .arg(port.to_string())
        .arg("--server.headless")
        .arg("true")
        .arg("--browser.gatherUsageStats")
        .arg("false")
        .env("FIND_MYSELF_DATA_DIR", data_path)
        .current_dir(&python_app)
        .stdout(stdout)
        .stderr(stderr)
        .spawn()
        .map_err(|err| format!("failed to spawn backend: {err}"))?;

    {
        let mut state = shared.inner.lock().map_err(|_| "runtime state poisoned".to_string())?;
        state.backend = Some(BackendProcess {
            child,
            url: url.clone(),
        });
    }

    if let Err(err) = wait_for_server(&url, Duration::from_secs(45)) {
        if let Ok(mut state) = shared.inner.lock() {
            stop_backend_inner(&mut state);
        }
        return Err(err);
    }

    Ok(StartBackendResponse { url })
}

#[tauri::command]
fn stop_backend(app: AppHandle, shared: State<SharedRuntime>) -> Result<(), String> {
    let mut state = shared.inner.lock().map_err(|_| "runtime state poisoned".to_string())?;
    stop_backend_inner(&mut state);
    state.last_error = None;
    let _ = app;
    Ok(())
}

#[tauri::command]
fn open_logs_dir(app: AppHandle) -> Result<(), String> {
    ensure_dirs(&app)?;
    let directory = logs_dir(&app)?;
    Command::new("open")
        .arg(directory)
        .status()
        .map_err(|err| format!("failed to open logs dir: {err}"))?;
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .manage(SharedRuntime::default())
        .setup(|app| {
            ensure_dirs(&app.handle()).map_err(|err| -> Box<dyn std::error::Error> { err.into() })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            app_status,
            install_runtime,
            start_backend,
            stop_backend,
            open_logs_dir
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
