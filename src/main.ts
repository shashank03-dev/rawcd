import "./styles.css";

import { formatProgress, mountedDevices, statusTone } from "./appState";
import {
  createEngineClient,
  DiscInspection,
  JobStatusPayload,
  OpticalDevice
} from "./engineClient";

const client = createEngineClient();
const root = document.querySelector<HTMLDivElement>("#app");

type UiState = {
  devices: OpticalDevice[];
  selectedMountPath: string;
  manualPath: string;
  inspection: DiscInspection | null;
  outputDir: string;
  aiRepair: boolean;
  preserveQuality: boolean;
  job: JobStatusPayload | null;
  busy: boolean;
  log: string[];
};

const state: UiState = {
  devices: [],
  selectedMountPath: "",
  manualPath: "",
  inspection: null,
  outputDir: "~/Videos/RawCD",
  aiRepair: true,
  preserveQuality: true,
  job: null,
  busy: false,
  log: ["Ready. Insert a personal, unprotected CD/DVD and scan devices."]
};

let pollTimer: number | undefined;

if (!root) {
  throw new Error("RawCD root element was not found.");
}

render();
void scanDevices();

function render() {
  const activeDeviceCount = mountedDevices(state.devices).length;
  const selectedSources = state.inspection?.playable_sources ?? [];
  const canInspect = Boolean(currentInputPath()) && !state.busy;
  const canConvert = selectedSources.length > 0 && state.outputDir.length > 0 && !state.busy;
  const tone = statusTone(state.job?.status ?? "idle");

  root!.innerHTML = `
    <main class="shell">
      <header class="topbar">
        <div class="brand-block">
          <p class="brand-mark">RawCD v0.1</p>
          <h1>Disc to MP4 restoration desk</h1>
          <p class="dek">A local proofing table for personal optical media: inspect the source, convert each clip, and keep a clear repair ledger.</p>
        </div>
        <div class="status-pill tone-${tone}">
          ${state.job ? escapeHtml(state.job.stage) : `${activeDeviceCount} mounted source${activeDeviceCount === 1 ? "" : "s"}`}
        </div>
      </header>

      <section class="workspace">
        <aside class="source-rail">
          <div class="section-title">
            <span>Source proof</span>
            <h2>Locate media</h2>
          </div>
          <button id="scan-devices" class="primary-action" ${state.busy ? "disabled" : ""}>Scan drives</button>
          <div class="device-list">
            ${renderDevices()}
          </div>
          <label class="field">
            <span>Manual mount path</span>
            <input id="manual-path" value="${escapeAttr(state.manualPath)}" placeholder="/media/user/MY_DISC" />
          </label>
          <button id="inspect-disc" class="secondary-action" ${canInspect ? "" : "disabled"}>Inspect media</button>
        </aside>

        <section class="main-panel">
          <div class="section-title">
            <span>Clip ledger</span>
            <h2>Review detected clips</h2>
          </div>
          <div class="inspection">
            ${renderInspection()}
          </div>

          <div class="convert-grid">
            <label class="field">
              <span>Output folder</span>
              <input id="output-dir" value="${escapeAttr(state.outputDir)}" />
            </label>
            <details class="advanced" open>
              <summary>Advanced repair and encode</summary>
              <label class="check-row">
                <input id="ai-repair" type="checkbox" ${state.aiRepair ? "checked" : ""} />
                <span>Use AI repair for damaged/frozen ranges when available</span>
              </label>
              <label class="check-row">
                <input id="preserve-quality" type="checkbox" ${state.preserveQuality ? "checked" : ""} />
                <span>Preserve source resolution and high-quality H.264/AAC output</span>
              </label>
            </details>
          </div>

          <div class="actions">
            <button id="start-conversion" class="primary-action" ${canConvert ? "" : "disabled"}>Convert to MP4</button>
            <button id="cancel-job" class="secondary-action" ${state.job?.status === "running" ? "" : "disabled"}>Cancel</button>
            <button id="open-output" class="secondary-action" ${state.job?.outputs?.length ? "" : "disabled"}>Open output</button>
          </div>

          <div class="progress-block">
            ${renderProgress()}
          </div>
        </section>

        <aside class="log-rail">
          <div class="section-title">
            <span>Run notes</span>
            <h2>Engine ledger</h2>
          </div>
          <ol class="log-list">
            ${state.log.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}
          </ol>
        </aside>
      </section>
    </main>
  `;

  bindEvents();
}

function bindEvents() {
  document.querySelector("#scan-devices")?.addEventListener("click", () => void scanDevices());
  document.querySelector("#inspect-disc")?.addEventListener("click", () => void inspectDisc());
  document.querySelector("#start-conversion")?.addEventListener("click", () => void startConversion());
  document.querySelector("#cancel-job")?.addEventListener("click", () => void cancelJob());
  document.querySelector("#open-output")?.addEventListener("click", () => void openOutput());

  document.querySelectorAll<HTMLInputElement>("input[name='device']").forEach((input) => {
    input.addEventListener("change", () => {
      state.selectedMountPath = input.value;
      state.manualPath = "";
      state.inspection = null;
      render();
    });
  });

  document.querySelector<HTMLInputElement>("#manual-path")?.addEventListener("input", (event) => {
    state.manualPath = (event.target as HTMLInputElement).value;
    state.selectedMountPath = "";
  });
  document.querySelector<HTMLInputElement>("#output-dir")?.addEventListener("input", (event) => {
    state.outputDir = (event.target as HTMLInputElement).value;
  });
  document.querySelector<HTMLInputElement>("#ai-repair")?.addEventListener("change", (event) => {
    state.aiRepair = (event.target as HTMLInputElement).checked;
  });
  document.querySelector<HTMLInputElement>("#preserve-quality")?.addEventListener("change", (event) => {
    state.preserveQuality = (event.target as HTMLInputElement).checked;
  });
}

async function scanDevices() {
  state.busy = true;
  pushLog("Scanning Linux optical devices.");
  render();
  try {
    state.devices = await client.scanDevices();
    const mounted = mountedDevices(state.devices);
    state.selectedMountPath = mounted[0]?.mount_path ?? "";
    pushLog(mounted.length ? `Found ${mounted.length} mounted disc source(s).` : "No mounted optical disc found.");
  } catch (error) {
    pushLog(`Scan failed: ${errorMessage(error)}`);
  } finally {
    state.busy = false;
    render();
  }
}

async function inspectDisc() {
  const path = currentInputPath();
  if (!path) return;
  state.busy = true;
  state.inspection = null;
  pushLog(`Inspecting ${path}.`);
  render();
  try {
    state.inspection = await client.inspectDisc(path);
    pushLog(
      `Detected ${state.inspection.label} with ${state.inspection.playable_sources.length} playable source(s).`
    );
    for (const warning of state.inspection.warnings) pushLog(warning);
  } catch (error) {
    pushLog(`Inspection failed: ${errorMessage(error)}`);
  } finally {
    state.busy = false;
    render();
  }
}

async function startConversion() {
  const sources = state.inspection?.playable_sources.map((source) => source.path) ?? [];
  if (!sources.length) return;
  state.busy = true;
  pushLog(`Starting conversion for ${sources.length} source(s).`);
  render();
  try {
    state.job = await client.startConversion({
      source_paths: sources,
      output_dir: state.outputDir,
      ai_repair: state.aiRepair,
      preserve_quality: state.preserveQuality
    });
    pushLog(`Job ${state.job.job_id} is ${state.job.status}.`);
    startPolling(state.job.job_id);
  } catch (error) {
    pushLog(`Conversion failed to start: ${errorMessage(error)}`);
  } finally {
    state.busy = false;
    render();
  }
}

async function cancelJob() {
  if (!state.job) return;
  try {
    const result = await client.cancelJob(state.job.job_id);
    pushLog(result.cancelled ? "Cancel requested." : "Job could not be canceled.");
  } catch (error) {
    pushLog(`Cancel failed: ${errorMessage(error)}`);
  }
}

async function openOutput() {
  const firstOutput = state.job?.outputs?.[0];
  if (!firstOutput) return;
  const folder = firstOutput.slice(0, firstOutput.lastIndexOf("/"));
  try {
    await client.openOutputFolder(folder || state.outputDir);
  } catch (error) {
    pushLog(`Open output failed: ${errorMessage(error)}`);
  }
}

function startPolling(jobId: string) {
  window.clearInterval(pollTimer);
  pollTimer = window.setInterval(async () => {
    try {
      state.job = await client.getJobStatus(jobId);
      if (["completed", "failed", "canceled"].includes(state.job.status)) {
        window.clearInterval(pollTimer);
        pushLog(`Job ${state.job.status}: ${state.job.stage}.`);
        for (const warning of state.job.warnings) pushLog(warning);
        if (state.job.error) pushLog(state.job.error);
      }
      render();
    } catch (error) {
      window.clearInterval(pollTimer);
      pushLog(`Status polling failed: ${errorMessage(error)}`);
      render();
    }
  }, 1000);
}

function currentInputPath(): string {
  return state.manualPath.trim() || state.selectedMountPath;
}

function renderDevices(): string {
  if (!state.devices.length) {
    return `<p class="empty">No scan results yet.</p>`;
  }
  return state.devices
    .map((device) => {
      const disabled = device.mount_path ? "" : "disabled";
      const checked = device.mount_path && device.mount_path === state.selectedMountPath ? "checked" : "";
      return `
        <label class="device-row ${device.has_media ? "" : "muted"}">
          <input name="device" type="radio" value="${escapeAttr(device.mount_path ?? "")}" ${checked} ${disabled} />
          <span>
            <strong>${escapeHtml(device.model ?? device.device_path)}</strong>
            <small>${escapeHtml(device.mount_path ?? "No mounted disc")}</small>
          </span>
        </label>
      `;
    })
    .join("");
}

function renderInspection(): string {
  if (!state.inspection) {
    return `<p class="empty">Inspect a mounted disc to list clips before conversion.</p>`;
  }
  const sources = state.inspection.playable_sources
    .map(
      (source, index) => `
        <li>
          <span class="clip-index">${String(index + 1).padStart(2, "0")}</span>
          <span>
            <strong>${escapeHtml(source.label)}</strong>
            <small>${escapeHtml(source.kind)} - ${escapeHtml(source.path)}</small>
          </span>
        </li>
      `
    )
    .join("");

  return `
    <div class="inspection-head">
      <strong>${escapeHtml(state.inspection.label)}</strong>
      <span>${state.inspection.playable_sources.length} clip(s)</span>
    </div>
    <ul class="clip-list">${sources || "<li>No playable clips detected.</li>"}</ul>
  `;
}

function renderProgress(): string {
  if (!state.job) {
    return `
      <div class="meter"><span style="width: 0%"></span></div>
      <div class="progress-meta"><span>Idle</span><span>0%</span></div>
    `;
  }
  return `
    <div class="meter"><span style="width: ${formatProgress(state.job.progress)}"></span></div>
    <div class="progress-meta">
      <span>${escapeHtml(state.job.stage)}</span>
      <span>${formatProgress(state.job.progress)}</span>
    </div>
    ${state.job.outputs.length ? `<ul class="outputs">${state.job.outputs.map((path) => `<li>${escapeHtml(path)}</li>`).join("")}</ul>` : ""}
  `;
}

function pushLog(message: string) {
  state.log = [message, ...state.log].slice(0, 12);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value: string): string {
  return escapeHtml(value);
}
