import type { JobStatusPayload, OpticalDevice } from "./engineClient";

export type StatusTone = "idle" | "active" | "good" | "bad" | "muted";

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
