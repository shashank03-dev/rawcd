import { invoke as tauriInvoke } from "@tauri-apps/api/core";

export type OpticalDevice = {
  device_path: string;
  model?: string | null;
  mount_path?: string | null;
  is_usb?: boolean;
  has_media: boolean;
};

export type PlayableSource = {
  path: string;
  kind: string;
  label: string;
};

export type DiscInspection = {
  disc_type: string;
  label: string;
  playable_sources: PlayableSource[];
  warnings: string[];
};

export type StartConversionRequest = {
  source_paths: string[];
  output_dir: string;
  ai_repair: boolean;
  preserve_quality: boolean;
  recovery_mode?: "quick" | "maximum";
  restore_mode?: "faithful" | "enhanced";
  export_profile?: "home_mp4" | "prores_422_hq" | "dnxhr_hqx" | "ffv1_mkv";
  lane?: "home" | "pro";
  rights_declaration?: RightsDeclarationPayload | null;
  protected_media?: boolean;
  commercial_use?: boolean;
  extract_wav_audio?: boolean;
};

export type JobStatusPayload = {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed" | "canceled";
  stage: string;
  progress: number;
  outputs: string[];
  warnings: string[];
  recovery_warnings?: string[];
  report: Record<string, unknown>;
  error?: string | null;
};

export type JobPreviewPayload = {
  job_id: string;
  current_frame: number;
  current_timestamp: number;
  current_operation: string;
  preview_image_path?: string | null;
};

export type ProviderSettingsPayload = {
  provider_id: string;
  enabled: boolean;
  api_key_configured: boolean;
  api_key: null;
  base_url?: string | null;
  executable_path?: string | null;
  extra: Record<string, unknown>;
};

export type ProviderPayload = {
  id: string;
  label: string;
  kind: string;
  capabilities: string[];
  settings: ProviderSettingsPayload;
};

export type ProviderHealthPayload = {
  status: "available" | "unavailable" | "degraded" | "license_required";
  message: string;
  details: Record<string, string>;
};

export type ConfigureProviderRequest = {
  enabled?: boolean | null;
  api_key?: string | null;
  base_url?: string | null;
  executable_path?: string | null;
  extra?: Record<string, unknown> | null;
};

export type ProProfilePayload = {
  name: string;
  organization: string;
  email: string;
  country: string;
  intended_use: string;
  verification_status: "not_requested" | "pending" | "approved" | "rejected";
  approved_at?: string | null;
  server_verification_id?: string | null;
  can_enable_pro_projects?: boolean;
};

export type RightsDeclarationPayload = {
  project_name: string;
  organization: string;
  source_title: string;
  rights_basis: string;
  permission_reference: string;
  declared_at?: string | null;
};

export type ValidateRightsRequest = {
  lane: "home" | "pro";
  rights_declaration?: RightsDeclarationPayload | null;
  protected_media?: boolean;
  commercial_use?: boolean;
};

export type RightsValidationPayload = {
  allowed: boolean;
  reason: string;
  declaration?: RightsDeclarationPayload | null;
};

export type HomeReportRequest = {
  report_path: string;
  recovered_clips: number;
  output_files: string[];
  damaged_sections?: Array<Record<string, unknown>>;
  reconstructed_sections?: Array<Record<string, unknown>>;
  skipped_sections?: Array<Record<string, unknown>>;
  provider_used?: string | null;
  warnings?: string[];
};

export type ProAuditReportRequest = {
  job_id: string;
  json_path: string;
  operator_notes?: string;
  warnings?: string[];
  markdown_path?: string | null;
};

type Invoke = <T>(command: string, args?: unknown) => Promise<T>;

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export function createEngineClient(options?: { invoke?: Invoke }) {
  const invoke = options?.invoke ?? defaultInvoke;
  return {
    scanDevices: () => invoke<OpticalDevice[]>("scan_devices"),
    inspectDisc: (path: string) =>
      invoke<DiscInspection>("inspect_disc", { request: { path } }),
    startConversion: (request: StartConversionRequest) =>
      invoke<JobStatusPayload>("start_conversion", { request }),
    getJobStatus: (jobId: string) =>
      invoke<JobStatusPayload>("get_job_status", { jobId }),
    getJobPreview: (jobId: string) =>
      invoke<JobPreviewPayload>("get_job_preview", { jobId }),
    cancelJob: (jobId: string) =>
      invoke<{ cancelled: boolean }>("cancel_job", { jobId }),
    listProviders: () => invoke<ProviderPayload[]>("list_providers"),
    testProvider: (providerId: string) =>
      invoke<ProviderHealthPayload>("test_provider", { providerId }),
    configureProvider: (providerId: string, request: ConfigureProviderRequest) =>
      invoke<ProviderPayload>("configure_provider", { providerId, request }),
    getProProfile: () => invoke<ProProfilePayload>("get_pro_profile"),
    saveProProfile: (request: ProProfilePayload) =>
      invoke<ProProfilePayload>("save_pro_profile", { request }),
    validateRights: (request: ValidateRightsRequest) =>
      invoke<RightsValidationPayload>("validate_rights", { request }),
    writeHomeReport: (request: HomeReportRequest) =>
      invoke<Record<string, unknown>>("write_home_report", { request }),
    writeProReport: (request: ProAuditReportRequest) =>
      invoke<Record<string, unknown>>("write_pro_report", { request }),
    openOutputFolder: (path: string) =>
      invoke<{ opened: boolean }>("open_output_folder", { path })
  };
}

function defaultInvoke<T>(command: string, args?: unknown): Promise<T> {
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    return tauriInvoke<T>(command, args as Record<string, unknown> | undefined);
  }
  return createHttpEngineInvoke()(command, args);
}

export function createHttpEngineInvoke(
  baseUrl = "http://127.0.0.1:8765",
  fetchImpl: FetchLike = fetch
): Invoke {
  return async <T>(command: string, args?: unknown): Promise<T> => {
    if (command === "open_output_folder") {
      return { opened: false } as T;
    }

    const { path, init } = httpRequestForCommand(command, args);
    const response = await fetchImpl(`${baseUrl.replace(/\/$/, "")}${path}`, init);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return (await response.json()) as T;
  };
}

function httpRequestForCommand(
  command: string,
  args: unknown
): { path: string; init?: RequestInit } {
  const payload = (args ?? {}) as Record<string, unknown>;
  switch (command) {
    case "scan_devices":
      return { path: "/scan_devices" };
    case "inspect_disc":
      return post("/inspect_disc", payload.request);
    case "start_conversion":
      return post("/start_conversion", payload.request);
    case "get_job_status":
      return { path: `/get_job_status/${String(payload.jobId)}` };
    case "get_job_preview":
      return { path: `/get_job_preview/${String(payload.jobId)}` };
    case "cancel_job":
      return post(`/cancel_job/${String(payload.jobId)}`, {});
    case "list_providers":
      return { path: "/providers" };
    case "test_provider":
      return post(`/providers/${String(payload.providerId)}/test`, {});
    case "configure_provider":
      return post(`/providers/${String(payload.providerId)}/configure`, payload.request);
    case "get_pro_profile":
      return { path: "/pro/profile" };
    case "save_pro_profile":
      return post("/pro/profile", payload.request);
    case "validate_rights":
      return post("/rights/validate", payload.request);
    case "write_home_report":
      return post("/reports/home", payload.request);
    case "write_pro_report":
      return post("/reports/pro", payload.request);
    default:
      throw new Error(`Unsupported engine command: ${command}`);
  }
}

function post(path: string, body: unknown): { path: string; init: RequestInit } {
  return {
    path,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }
  };
}
