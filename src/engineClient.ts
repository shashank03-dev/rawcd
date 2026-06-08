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
    cancelJob: (jobId: string) =>
      invoke<{ cancelled: boolean }>("cancel_job", { jobId }),
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
    case "cancel_job":
      return post(`/cancel_job/${String(payload.jobId)}`, {});
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
