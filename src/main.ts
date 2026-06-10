import "./styles.css";

import {
  defaultRestoreControls,
  formatProgress,
  mountedDevices,
  previewOperationLabel,
  proControlsAvailable,
  statusTone,
  timelineMarkers,
  type RecoveryMode,
  type RestoreLane,
  type RestoreMode
} from "./appState";
import {
  createEngineClient,
  DiscInspection,
  JobPreviewPayload,
  JobStatusPayload,
  OpticalDevice,
  ProviderPayload,
  ProProfilePayload
} from "./engineClient";

const client = createEngineClient();
const root = document.querySelector<HTMLDivElement>("#app");

type UiState = {
  devices: OpticalDevice[];
  selectedMountPath: string;
  manualPath: string;
  inspection: DiscInspection | null;
  lane: RestoreLane;
  recoveryMode: RecoveryMode;
  restoreMode: RestoreMode;
  exportProfile: "prores_422_hq" | "dnxhr_hqx" | "ffv1_mkv";
  outputDir: string;
  aiRepair: boolean;
  preserveQuality: boolean;
  extractWavAudio: boolean;
  job: JobStatusPayload | null;
  preview: JobPreviewPayload | null;
  proProfile: ProProfilePayload | null;
  providers: ProviderPayload[];
  rights: {
    project_name: string;
    organization: string;
    source_title: string;
    rights_basis: string;
    permission_reference: string;
  };
  homeReport: Record<string, unknown> | null;
  proReport: Record<string, unknown> | null;
  busy: boolean;
  log: string[];
};

const restoreDefaults = defaultRestoreControls();

const state: UiState = {
  devices: [],
  selectedMountPath: "",
  manualPath: "",
  inspection: null,
  lane: restoreDefaults.lane,
  recoveryMode: restoreDefaults.recoveryMode,
  restoreMode: restoreDefaults.restoreMode,
  exportProfile: "prores_422_hq",
  outputDir: "~/Videos/RawCD",
  aiRepair: true,
  preserveQuality: true,
  extractWavAudio: false,
  job: null,
  preview: null,
  proProfile: null,
  providers: [],
  rights: {
    project_name: "",
    organization: "",
    source_title: "",
    rights_basis: "",
    permission_reference: ""
  },
  homeReport: null,
  proReport: null,
  busy: false,
  log: ["Ready. Insert a personal, unprotected CD/DVD and scan devices."]
};

let pollTimer: number | undefined;

if (!root) {
  throw new Error("RawCD root element was not found.");
}

render();
void loadProProfile();
void loadProviders();
void scanDevices();

function render() {
  const activeDeviceCount = mountedDevices(state.devices).length;
  const selectedSources = state.inspection?.playable_sources ?? [];
  const canInspect = Boolean(currentInputPath()) && !state.busy;
  const proReady = proControlsAvailable(state.proProfile);
  const canUseLane = state.lane === "home" || (proReady && rightsComplete());
  const canConvert = selectedSources.length > 0 && state.outputDir.length > 0 && !state.busy && canUseLane;
  const tone = statusTone(state.job?.status ?? "idle");

  root!.innerHTML = `
    <main class="shell">
      <header class="topbar">
        <div class="brand-block">
          <p class="brand-mark">RawCD v0.1</p>
          <h1>Disc restoration desk</h1>
          <p class="dek">A local proofing table for optical media: inspect the source, restore each clip, and keep a clear repair ledger.</p>
        </div>
        <div class="status-pill tone-${tone}">
          ${state.job ? escapeHtml(state.job.stage) : `${escapeHtml(state.lane === "home" ? "Home Restore" : "Studio / Pro")}: ${activeDeviceCount} mounted source${activeDeviceCount === 1 ? "" : "s"}`}
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
          ${renderLaneSwitch()}
          <div class="section-title">
            <span>Clip ledger</span>
            <h2>Review detected clips</h2>
          </div>
          <div class="inspection">
            ${renderInspection()}
          </div>

          ${renderRestoreControls()}
          ${state.lane === "pro" ? renderProWorkflow(proReady) : ""}

          <div class="convert-grid">
            <label class="field">
              <span>Output folder</span>
              <input id="output-dir" value="${escapeAttr(state.outputDir)}" />
            </label>
            <details class="advanced">
              <summary>Provider settings</summary>
              <label class="check-row">
                <input id="ai-repair" type="checkbox" ${state.aiRepair ? "checked" : ""} />
                <span>Use AI repair for damaged/frozen ranges when available</span>
              </label>
              <label class="check-row">
                <input id="preserve-quality" type="checkbox" ${state.preserveQuality ? "checked" : ""} />
                <span>Preserve source resolution and high-quality H.264/AAC output</span>
              </label>
              ${renderProviderSettings()}
            </details>
          </div>

          <div class="actions">
            <button id="start-conversion" class="primary-action" ${canConvert ? "" : "disabled"}>${state.lane === "home" ? "Start Home Restore" : "Start Pro Restore"}</button>
            <button id="cancel-job" class="secondary-action" ${state.job?.status === "running" ? "" : "disabled"}>Cancel</button>
            <button id="open-output" class="secondary-action" ${state.job?.outputs?.length ? "" : "disabled"}>Open output</button>
          </div>

          ${renderPreviewPanel()}

          <div class="progress-block">
            ${renderProgress()}
          </div>
          ${renderReportPanel()}
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
  document.querySelector("#save-pro-profile")?.addEventListener("click", () => void saveProProfile());
  document.querySelector("#open-home-report")?.addEventListener("click", () => void openReportFolder(state.homeReport));
  document.querySelector("#open-pro-report")?.addEventListener("click", () => void openReportFolder(state.proReport));
  document.querySelectorAll<HTMLInputElement>("[data-provider-toggle]").forEach((input) => {
    input.addEventListener("change", () => void toggleProvider(input.dataset.providerToggle ?? "", input.checked));
  });
  document.querySelectorAll<HTMLButtonElement>("[data-provider-test]").forEach((button) => {
    button.addEventListener("click", () => void testProvider(button.dataset.providerTest ?? ""));
  });

  document.querySelectorAll<HTMLInputElement>("input[name='device']").forEach((input) => {
    input.addEventListener("change", () => {
      state.selectedMountPath = input.value;
      state.manualPath = "";
      state.inspection = null;
      render();
    });
  });
  document.querySelectorAll<HTMLInputElement>("input[name='lane']").forEach((input) => {
    input.addEventListener("change", () => {
      state.lane = input.value as RestoreLane;
      render();
    });
  });
  document.querySelectorAll<HTMLInputElement>("input[name='recovery-mode']").forEach((input) => {
    input.addEventListener("change", () => {
      state.recoveryMode = input.value as RecoveryMode;
      render();
    });
  });
  document.querySelectorAll<HTMLInputElement>("input[name='restore-mode']").forEach((input) => {
    input.addEventListener("change", () => {
      state.restoreMode = input.value as RestoreMode;
      state.aiRepair = true;
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
  document.querySelector<HTMLInputElement>("#extract-wav-audio")?.addEventListener("change", (event) => {
    state.extractWavAudio = (event.target as HTMLInputElement).checked;
  });
  document.querySelector<HTMLSelectElement>("#export-profile")?.addEventListener("change", (event) => {
    state.exportProfile = (event.target as HTMLSelectElement).value as UiState["exportProfile"];
  });
  bindTextInput("#pro-name", (value) => updateProDraft("name", value));
  bindTextInput("#pro-organization", (value) => updateProDraft("organization", value));
  bindTextInput("#pro-email", (value) => updateProDraft("email", value));
  bindTextInput("#pro-country", (value) => updateProDraft("country", value));
  bindTextInput("#pro-intended-use", (value) => updateProDraft("intended_use", value));
  bindTextInput("#rights-project", (value) => (state.rights.project_name = value));
  bindTextInput("#rights-organization", (value) => (state.rights.organization = value));
  bindTextInput("#rights-source-title", (value) => (state.rights.source_title = value));
  bindTextInput("#rights-basis", (value) => (state.rights.rights_basis = value));
  bindTextInput("#rights-reference", (value) => (state.rights.permission_reference = value));
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

async function loadProProfile() {
  try {
    state.proProfile = await client.getProProfile();
    if (!state.rights.organization && state.proProfile.organization) {
      state.rights.organization = state.proProfile.organization;
    }
    render();
  } catch (error) {
    pushLog(`Pro profile unavailable: ${errorMessage(error)}`);
  }
}

async function loadProviders() {
  try {
    state.providers = await client.listProviders();
    render();
  } catch (error) {
    pushLog(`Provider registry unavailable: ${errorMessage(error)}`);
  }
}

async function saveProProfile() {
  const profile = proProfileDraft();
  try {
    state.proProfile = await client.saveProProfile(profile);
    pushLog(`Pro verification profile saved as ${state.proProfile.verification_status}.`);
    render();
  } catch (error) {
    pushLog(`Pro profile save failed: ${errorMessage(error)}`);
    render();
  }
}

async function toggleProvider(providerId: string, enabled: boolean) {
  if (!providerId) return;
  try {
    const provider = await client.configureProvider(providerId, { enabled });
    state.providers = state.providers.map((item) => (item.id === provider.id ? provider : item));
    pushLog(`${provider.label} ${enabled ? "enabled" : "disabled"}.`);
    render();
  } catch (error) {
    pushLog(`Provider update failed: ${errorMessage(error)}`);
    render();
  }
}

async function testProvider(providerId: string) {
  const provider = state.providers.find((item) => item.id === providerId);
  if (!provider) return;
  try {
    const health = await client.testProvider(providerId);
    pushLog(`${provider.label}: ${health.status} - ${health.message}`);
  } catch (error) {
    pushLog(`Provider test failed: ${errorMessage(error)}`);
  } finally {
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
  if (state.lane === "pro") {
    const validation = await validateProRights();
    if (!validation) return;
  }
  state.busy = true;
  state.homeReport = null;
  state.proReport = null;
  state.preview = null;
  pushLog(`Starting ${state.lane === "home" ? "Home Restore" : "Pro Restore"} for ${sources.length} source(s).`);
  render();
  try {
    state.job = await client.startConversion({
      source_paths: sources,
      output_dir: state.outputDir,
      ai_repair: state.aiRepair,
      preserve_quality: state.preserveQuality,
      recovery_mode: state.recoveryMode,
      restore_mode: state.restoreMode,
      export_profile: state.lane === "home" ? "home_mp4" : state.exportProfile,
      lane: state.lane,
      rights_declaration: state.lane === "pro" ? state.rights : null,
      protected_media: protectedMediaDetected(),
      commercial_use: state.lane === "pro",
      extract_wav_audio: state.lane === "pro" ? state.extractWavAudio : false
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

async function validateProRights(): Promise<boolean> {
  try {
    const result = await client.validateRights({
      lane: "pro",
      protected_media: protectedMediaDetected(),
      commercial_use: true,
      rights_declaration: state.rights
    });
    pushLog(result.reason);
    return result.allowed;
  } catch (error) {
    pushLog(`Rights validation failed: ${errorMessage(error)}`);
    return false;
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
      state.preview = await client.getJobPreview(jobId);
      if (["completed", "failed", "canceled"].includes(state.job.status)) {
        window.clearInterval(pollTimer);
        pushLog(`Job ${state.job.status}: ${state.job.stage}.`);
        for (const warning of state.job.warnings) pushLog(warning);
        if (state.job.error) pushLog(state.job.error);
        if (state.job.status === "completed" && state.lane === "home") {
          const homeReport = state.job.report.home_report as Record<string, unknown> | undefined;
          if (homeReport) {
            state.homeReport = homeReport;
            pushLog(`Home report saved: ${String(homeReport.json_save_path)}`);
          } else {
            await writeHomeReportForJob();
          }
        } else if (state.job.status === "completed" && state.lane === "pro") {
          await writeProAuditReportForJob();
        }
      }
      render();
    } catch (error) {
      window.clearInterval(pollTimer);
      pushLog(`Status polling failed: ${errorMessage(error)}`);
      render();
    }
  }, 1000);
}

async function writeHomeReportForJob() {
  if (!state.job) return;
  const reportPath = homeReportPath();
  if (!reportPath) return;
  const timeline = state.job.report.timeline as Record<string, unknown> | undefined;
  const ranges = Array.isArray(timeline?.ranges) ? (timeline.ranges as Array<Record<string, unknown>>) : [];
  try {
    state.homeReport = await client.writeHomeReport({
      report_path: reportPath,
      recovered_clips: state.job.outputs.length,
      output_files: state.job.outputs,
      damaged_sections: ranges.filter((range) => range.state === "damaged" || range.state === "missing"),
      reconstructed_sections: ranges.filter((range) => range.state === "interpolated" || range.state === "generated" || range.state === "enhanced"),
      skipped_sections: ranges.filter((range) => range.state === "skipped"),
      provider_used: String((state.job.report.repair as Record<string, unknown> | undefined)?.tool ?? ""),
      warnings: state.job.warnings
    });
    pushLog(`Home report saved: ${String(state.homeReport.json_save_path)}`);
  } catch (error) {
    pushLog(`Home report failed: ${errorMessage(error)}`);
  }
}

async function writeProAuditReportForJob() {
  if (!state.job) return;
  const reportPath = proAuditReportPath();
  if (!reportPath) return;
  try {
    state.proReport = await client.writeProReport({
      job_id: state.job.job_id,
      json_path: reportPath,
      operator_notes: `RawCD Pro restore job ${state.job.job_id}`,
      warnings: state.job.warnings
    });
    pushLog(`Pro audit report saved: ${String(state.proReport.json_save_path)}`);
  } catch (error) {
    pushLog(`Pro audit report failed: ${errorMessage(error)}`);
  }
}

function currentInputPath(): string {
  return state.manualPath.trim() || state.selectedMountPath;
}

function protectedMediaDetected(): boolean {
  return Boolean(
    state.inspection?.disc_type === "protected_media" ||
      state.inspection?.warnings.some((warning) => warning.toLowerCase().includes("protected"))
  );
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

function rightsComplete(): boolean {
  if (state.lane === "home") return true;
  return Object.values(state.rights).every((value) => value.trim().length > 0);
}

function renderLaneSwitch(): string {
  return `
    <section class="lane-switch" aria-label="Restore lane">
      <label class="lane-option ${state.lane === "home" ? "active" : ""}">
        <input name="lane" type="radio" value="home" ${state.lane === "home" ? "checked" : ""} />
        <span>Home Restore</span>
        <small>Personal media</small>
      </label>
      <label class="lane-option ${state.lane === "pro" ? "active" : ""}">
        <input name="lane" type="radio" value="pro" ${state.lane === "pro" ? "checked" : ""} />
        <span>Studio / Pro</span>
        <small>${proControlsAvailable(state.proProfile) ? "Verified" : "Verification required"}</small>
      </label>
    </section>
  `;
}

function renderRestoreControls(): string {
  return `
    <section class="restore-controls">
      <div class="control-group">
        <span class="control-label">Recovery</span>
        <div class="segmented">
          ${renderModeOption("recovery-mode", "quick", "Quick Convert", state.recoveryMode === "quick")}
          ${renderModeOption("recovery-mode", "maximum", "Maximum Recovery", state.recoveryMode === "maximum")}
        </div>
      </div>
      <div class="control-group">
        <span class="control-label">Restore</span>
        <div class="segmented">
          ${renderModeOption("restore-mode", "faithful", "Faithful Restore", state.restoreMode === "faithful")}
          ${renderModeOption("restore-mode", "enhanced", "Enhanced Restore", state.restoreMode === "enhanced")}
        </div>
      </div>
    </section>
  `;
}

function renderModeOption(name: string, value: string, label: string, checked: boolean): string {
  return `
    <label class="mode-option ${checked ? "active" : ""}">
      <input name="${escapeAttr(name)}" type="radio" value="${escapeAttr(value)}" ${checked ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

function renderProWorkflow(proReady: boolean): string {
  const profile = state.proProfile ?? emptyProProfile();
  if (!proReady) {
    return `
      <section class="pro-workflow">
        <div class="section-title">
          <span>Pro verification</span>
          <h2>Studio / Pro Restore</h2>
        </div>
        <div class="pro-grid">
          ${renderTextField("pro-name", "Name", profile.name)}
          ${renderTextField("pro-organization", "Organization", profile.organization)}
          ${renderTextField("pro-email", "Email", profile.email)}
          ${renderTextField("pro-country", "Country", profile.country)}
          ${renderTextField("pro-intended-use", "Intended use", profile.intended_use)}
        </div>
        <div class="pro-actions">
          <button id="save-pro-profile" class="secondary-action" ${state.busy ? "disabled" : ""}>Submit verification profile</button>
          <p class="pro-locked">Status: ${verificationStatusLabel(profile.verification_status)}</p>
        </div>
      </section>
    `;
  }

  return `
    <section class="pro-workflow pro-ready">
      <div class="section-title">
        <span>Pro project</span>
        <h2>Rights and archival output</h2>
      </div>
      <div class="pro-grid">
        ${renderTextField("rights-project", "Project name", state.rights.project_name)}
        ${renderTextField("rights-organization", "Organization", state.rights.organization)}
        ${renderTextField("rights-source-title", "Source title", state.rights.source_title)}
        ${renderTextField("rights-basis", "Rights basis", state.rights.rights_basis)}
        ${renderTextField("rights-reference", "Permission reference", state.rights.permission_reference)}
        <label class="field">
          <span>Archival export</span>
          <select id="export-profile">
            <option value="prores_422_hq" ${state.exportProfile === "prores_422_hq" ? "selected" : ""}>ProRes 422 HQ</option>
            <option value="dnxhr_hqx" ${state.exportProfile === "dnxhr_hqx" ? "selected" : ""}>DNxHR HQX</option>
            <option value="ffv1_mkv" ${state.exportProfile === "ffv1_mkv" ? "selected" : ""}>FFV1 Matroska</option>
          </select>
        </label>
      </div>
      <label class="check-row pro-wav">
        <input id="extract-wav-audio" type="checkbox" ${state.extractWavAudio ? "checked" : ""} />
        <span>Extract 24-bit WAV audio sidecar</span>
      </label>
      <div class="provider-routing">
        <strong>Provider routing</strong>
        <span>${renderProviderRoutingSummary()}</span>
        <small>${state.inspection?.playable_sources.length ?? 0} batch source(s)</small>
      </div>
    </section>
  `;
}

function renderTextField(id: string, label: string, value: string): string {
  return `
    <label class="field">
      <span>${escapeHtml(label)}</span>
      <input id="${escapeAttr(id)}" value="${escapeAttr(value)}" />
    </label>
  `;
}

function renderProviderRoutingSummary(): string {
  const enabled = state.providers.filter((provider) => provider.settings.enabled);
  if (!enabled.length) return "No enabled enhancement providers";
  return enabled
    .map((provider) => `${provider.label}: ${provider.capabilities.join(", ") || "health only"}`)
    .join(" / ");
}

function renderProviderSettings(): string {
  if (!state.providers.length) {
    return `<p class="empty provider-empty">No enhancement providers loaded.</p>`;
  }
  return `
    <div class="provider-list">
      ${state.providers
        .map(
          (provider) => `
            <div class="provider-row">
              <label class="check-row">
                <input data-provider-toggle="${escapeAttr(provider.id)}" type="checkbox" ${provider.settings.enabled ? "checked" : ""} />
                <span>${escapeHtml(provider.label)}</span>
              </label>
              <small>${escapeHtml(provider.kind)} / ${escapeHtml(provider.capabilities.join(", ") || "health check")}</small>
              <button data-provider-test="${escapeAttr(provider.id)}" class="secondary-action" type="button">Test</button>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderPreviewPanel(): string {
  if (!state.job) return "";
  const preview = state.preview ?? {
    job_id: state.job.job_id,
    current_frame: 0,
    current_timestamp: 0,
    current_operation: state.job.stage,
    preview_image_path: null
  };
  const markers = timelineMarkers(state.job.report);
  const operation = previewOperationLabel(preview.current_operation);
  const timestamp = `${preview.current_timestamp.toFixed(2)}s`;
  const previewSrc = previewImageSrc(preview.preview_image_path);

  return `
    <section class="preview-panel">
      <div class="preview-stage">
        <div>
          <span class="control-label">Live preview</span>
          <strong>${escapeHtml(operation)}</strong>
        </div>
        <div class="preview-meta">
          <span>Frame ${preview.current_frame}</span>
          <span>${escapeHtml(timestamp)}</span>
        </div>
      </div>
      <div class="preview-frame">
        ${
          previewSrc
            ? `<img src="${escapeAttr(previewSrc)}" alt="Current restore preview" />`
            : `<span>${escapeHtml(String(preview.current_frame).padStart(6, "0"))}</span>`
        }
      </div>
      <div class="timeline-strip" aria-label="Frame provenance">
        ${markers.length ? renderTimelineMarkers(markers) : `<span class="timeline-empty"></span>`}
      </div>
    </section>
  `;
}

function previewImageSrc(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^(https?:|data:|blob:)/.test(path)) return path;
  return null;
}

function renderTimelineMarkers(markers: ReturnType<typeof timelineMarkers>): string {
  const duration = Math.max(...markers.map((marker) => marker.end), timelineDurationSeconds(), 1);
  return markers
    .map((marker) => {
      const left = Math.max(0, Math.min(100, (marker.start / duration) * 100));
      const width = Math.max(1, Math.min(100 - left, ((marker.end - marker.start) / duration) * 100));
      return `<span class="timeline-marker state-${markerClass(marker.state)}" title="${escapeAttr(marker.state)}" style="left: ${left}%; width: ${width}%"></span>`;
    })
    .join("");
}

function renderReportPanel(): string {
  if (!state.homeReport && !state.proReport) return "";
  return `
    <section class="report-panel">
      ${state.homeReport ? renderReportCard("Home report", state.homeReport, "open-home-report") : ""}
      ${state.proReport ? renderReportCard("Pro audit report", state.proReport, "open-pro-report") : ""}
    </section>
  `;
}

function renderReportCard(title: string, report: Record<string, unknown>, buttonId: string): string {
  const jsonPath = String(report.json_save_path ?? "");
  const markdownPath = String(report.markdown_save_path ?? "");
  return `
    <article class="report-card">
      <div>
        <strong>${escapeHtml(title)}</strong>
        <div class="report-summary">
          ${renderReportSummary(report)}
        </div>
        <small>${escapeHtml(jsonPath)}</small>
        ${markdownPath ? `<small>${escapeHtml(markdownPath)}</small>` : ""}
      </div>
      <button id="${escapeAttr(buttonId)}" class="secondary-action">Open folder</button>
    </article>
  `;
}

function renderReportSummary(report: Record<string, unknown>): string {
  const recoveredClips = Number(report.recovered_clips ?? report.clips ?? 0);
  const damaged = countReportArray(report.damaged_sections);
  const reconstructed = countReportArray(report.reconstructed_sections);
  const skipped = countReportArray(report.skipped_sections);
  const warnings = countReportArray(report.warnings);
  const provider = String(report.provider_used ?? report.export_profile ?? "none");
  return [
    `${recoveredClips} clip${recoveredClips === 1 ? "" : "s"}`,
    `${damaged} damaged`,
    `${reconstructed} reconstructed`,
    `${skipped} skipped`,
    `provider ${provider}`,
    `${warnings} warning${warnings === 1 ? "" : "s"}`
  ]
    .map((item) => `<span>${escapeHtml(item)}</span>`)
    .join("");
}

function countReportArray(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
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

function bindTextInput(selector: string, updater: (value: string) => void) {
  document.querySelector<HTMLInputElement>(selector)?.addEventListener("input", (event) => {
    updater((event.target as HTMLInputElement).value);
  });
}

function updateProDraft(field: keyof ProProfilePayload, value: string) {
  state.proProfile = {
    ...emptyProProfile(),
    ...(state.proProfile ?? {}),
    [field]: value
  };
}

function proProfileDraft(): ProProfilePayload {
  const profile = {
    ...emptyProProfile(),
    ...(state.proProfile ?? {})
  };
  return {
    name: profile.name.trim(),
    organization: profile.organization.trim(),
    email: profile.email.trim(),
    country: profile.country.trim(),
    intended_use: profile.intended_use.trim(),
    verification_status: "pending",
    approved_at: null,
    server_verification_id: null
  };
}

function emptyProProfile(): ProProfilePayload {
  return {
    name: "",
    organization: "",
    email: "",
    country: "",
    intended_use: "",
    verification_status: "not_requested",
    approved_at: null,
    server_verification_id: null,
    can_enable_pro_projects: false
  };
}

function verificationStatusLabel(status: ProProfilePayload["verification_status"]): string {
  switch (status) {
    case "approved":
      return "Approved";
    case "pending":
      return "Pending";
    case "rejected":
      return "Rejected";
    default:
      return "Not requested";
  }
}

function homeReportPath(): string | null {
  return reportPath("rawcd-home-report");
}

function proAuditReportPath(): string | null {
  return reportPath("rawcd-pro-audit");
}

function reportPath(suffix: string): string | null {
  const firstOutput = state.job?.outputs[0];
  if (!firstOutput) return null;
  const slash = firstOutput.lastIndexOf("/");
  const dot = firstOutput.lastIndexOf(".");
  const base = dot > slash ? firstOutput.slice(0, dot) : firstOutput;
  return `${base}.${suffix}.json`;
}

async function openReportFolder(report: Record<string, unknown> | null) {
  const jsonPath = String(report?.json_save_path ?? "");
  if (!jsonPath) return;
  const slash = jsonPath.lastIndexOf("/");
  const folder = slash >= 0 ? jsonPath.slice(0, slash) : state.outputDir;
  try {
    await client.openOutputFolder(folder || state.outputDir);
  } catch (error) {
    pushLog(`Open report failed: ${errorMessage(error)}`);
    render();
  }
}

function timelineDurationSeconds(): number {
  const timeline = state.job?.report.timeline as Record<string, unknown> | undefined;
  const duration = Number(timeline?.duration_seconds ?? 0);
  return Number.isFinite(duration) ? duration : 0;
}

function markerClass(stateName: string): string {
  switch (stateName) {
    case "damaged":
    case "missing":
    case "interpolated":
    case "generated":
    case "enhanced":
    case "skipped":
      return stateName;
    default:
      return "original";
  }
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
