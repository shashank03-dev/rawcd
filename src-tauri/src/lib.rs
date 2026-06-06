use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::State;
use tokio::time::sleep;

const ENGINE_HOST: &str = "127.0.0.1";
const ENGINE_PORT: u16 = 8765;

pub fn engine_url(base_url: &str, path: &str) -> String {
    format!(
        "{}/{}",
        base_url.trim_end_matches('/'),
        path.trim_start_matches('/')
    )
}

pub fn python_server_args(host: &str, port: u16) -> Vec<String> {
    vec![
        "-m".to_string(),
        "rawcd.server".to_string(),
        "--host".to_string(),
        host.to_string(),
        "--port".to_string(),
        port.to_string(),
    ]
}

struct EngineState {
    base_url: String,
    client: reqwest::Client,
    child: Mutex<Option<Child>>,
    work_dir: PathBuf,
}

impl EngineState {
    fn new() -> Self {
        Self {
            base_url: format!("http://{}:{}", ENGINE_HOST, ENGINE_PORT),
            client: reqwest::Client::new(),
            child: Mutex::new(None),
            work_dir: engine_work_dir(),
        }
    }

    async fn ensure_running(&self) -> Result<(), String> {
        if self.health_ok().await {
            return Ok(());
        }

        {
            let mut child = self
                .child
                .lock()
                .map_err(|_| "engine process lock is poisoned".to_string())?;
            if child.is_none() {
                let args = python_server_args(ENGINE_HOST, ENGINE_PORT);
                let spawned = Command::new("python3")
                    .args(args)
                    .current_dir(&self.work_dir)
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .spawn()
                    .map_err(|error| format!("failed to start RawCD engine: {error}"))?;
                *child = Some(spawned);
            }
        }

        for _ in 0..50 {
            if self.health_ok().await {
                return Ok(());
            }
            sleep(Duration::from_millis(100)).await;
        }

        Err("RawCD engine did not become ready on 127.0.0.1:8765".to_string())
    }

    async fn health_ok(&self) -> bool {
        self.client
            .get(engine_url(&self.base_url, "/health"))
            .send()
            .await
            .map(|response| response.status().is_success())
            .unwrap_or(false)
    }

    async fn get_json(&self, path: &str) -> Result<Value, String> {
        self.ensure_running().await?;
        let response = self
            .client
            .get(engine_url(&self.base_url, path))
            .send()
            .await
            .map_err(|error| error.to_string())?;
        response
            .error_for_status()
            .map_err(|error| error.to_string())?
            .json::<Value>()
            .await
            .map_err(|error| error.to_string())
    }

    async fn post_json<T: Serialize>(&self, path: &str, body: &T) -> Result<Value, String> {
        self.ensure_running().await?;
        let response = self
            .client
            .post(engine_url(&self.base_url, path))
            .json(body)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        response
            .error_for_status()
            .map_err(|error| error.to_string())?
            .json::<Value>()
            .await
            .map_err(|error| error.to_string())
    }
}

#[derive(Deserialize, Serialize)]
struct InspectDiscRequest {
    path: String,
}

#[derive(Deserialize, Serialize)]
struct StartConversionRequest {
    source_paths: Vec<String>,
    output_dir: String,
    ai_repair: bool,
    preserve_quality: bool,
}

#[tauri::command]
async fn scan_devices(state: State<'_, EngineState>) -> Result<Value, String> {
    state.get_json("/scan_devices").await
}

#[tauri::command]
async fn inspect_disc(
    state: State<'_, EngineState>,
    request: InspectDiscRequest,
) -> Result<Value, String> {
    state.post_json("/inspect_disc", &request).await
}

#[tauri::command]
async fn start_conversion(
    state: State<'_, EngineState>,
    request: StartConversionRequest,
) -> Result<Value, String> {
    state.post_json("/start_conversion", &request).await
}

#[tauri::command]
async fn get_job_status(state: State<'_, EngineState>, job_id: String) -> Result<Value, String> {
    state.get_json(&format!("/get_job_status/{job_id}")).await
}

#[tauri::command]
async fn cancel_job(state: State<'_, EngineState>, job_id: String) -> Result<Value, String> {
    state.post_json(&format!("/cancel_job/{job_id}"), &serde_json::json!({}))
        .await
}

#[derive(Serialize)]
struct OpenFolderResult {
    opened: bool,
}

#[tauri::command]
fn open_output_folder(path: String) -> Result<OpenFolderResult, String> {
    Command::new("xdg-open")
        .arg(path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("failed to open output folder: {error}"))?;
    Ok(OpenFolderResult { opened: true })
}

fn engine_work_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .to_path_buf()
}

pub fn run() {
    tauri::Builder::default()
        .manage(EngineState::new())
        .invoke_handler(tauri::generate_handler![
            scan_devices,
            inspect_disc,
            start_conversion,
            get_job_status,
            cancel_job,
            open_output_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running RawCD");
}

#[cfg(test)]
mod tests {
    use super::{engine_url, python_server_args};

    #[test]
    fn builds_engine_endpoint_url_without_double_slashes() {
        assert_eq!(
            engine_url("http://127.0.0.1:8765", "/scan_devices"),
            "http://127.0.0.1:8765/scan_devices"
        );
        assert_eq!(
            engine_url("http://127.0.0.1:8765/", "health"),
            "http://127.0.0.1:8765/health"
        );
    }

    #[test]
    fn builds_python_server_args_for_loopback_engine() {
        assert_eq!(
            python_server_args("127.0.0.1", 8765),
            vec!["-m", "rawcd.server", "--host", "127.0.0.1", "--port", "8765"]
        );
    }
}
