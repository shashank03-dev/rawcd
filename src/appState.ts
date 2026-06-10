import type { JobStatusPayload, OpticalDevice } from "./engineClient";

export type StatusTone = "idle" | "active" | "good" | "bad" | "muted";
export type RestoreLane = "home" | "pro";
export type RecoveryMode = "quick" | "maximum";
export type RestoreMode = "faithful" | "enhanced";

export type RestoreControls = {
  lane: RestoreLane;
  recoveryMode: RecoveryMode;
  restoreMode: RestoreMode;
};

export type TimelineMarker = {
  start: number;
  end: number;
  state: string;
};

export function mountedDevices(devices: OpticalDevice[]): OpticalDevice[] {
  return devices.filter((device) => device.has_media && Boolean(device.mount_path));
}

export function formatProgress(progress: number): string {
  const bounded = Math.max(0, Math.min(1, progress));
  return `${Math.round(bounded * 100)}%`;
}

export function statusTone(status: JobStatusPayload["status"] | "idle"): StatusTone {
  switch (status) {
    case "completed":
      return "good";
    case "failed":
    case "canceled":
      return "bad";
    case "pending":
    case "running":
      return "active";
    case "idle":
      return "idle";
    default:
      return "muted";
  }
}

export function defaultRestoreControls(): RestoreControls {
  return {
    lane: "home",
    recoveryMode: "maximum",
    restoreMode: "faithful"
  };
}

export function previewOperationLabel(operation: string): string {
  switch (operation) {
    case "recovering":
      return "Recovering original frame";
    case "interpolating":
      return "Interpolating missing frames";
    case "reconstructing":
      return "AI reconstructing damaged section";
    case "enhancing":
      return "Enhancing restored section";
    case "exporting":
      return "Exporting final video";
    default:
      return operation || "Recovering original frame";
  }
}

export function timelineMarkers(report: Record<string, unknown> | undefined): TimelineMarker[] {
  const timeline = report?.timeline as { ranges?: unknown[] } | undefined;
  if (!timeline || !Array.isArray(timeline.ranges)) return [];
  return timeline.ranges
    .map((range) => {
      const item = range as Record<string, unknown>;
      return {
        start: Number(item.start_seconds ?? 0),
        end: Number(item.end_seconds ?? item.start_seconds ?? 0),
        state: String(item.state ?? "original")
      };
    })
    .filter((marker) => Number.isFinite(marker.start) && Number.isFinite(marker.end));
}

export function proControlsAvailable(profile: { verification_status?: string } | null): boolean {
  return profile?.verification_status === "approved";
}
