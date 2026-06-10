import { describe, expect, it } from "vitest";

import {
  defaultRestoreControls,
  formatProgress,
  mountedDevices,
  previewOperationLabel,
  proControlsAvailable,
  statusTone,
  timelineMarkers
} from "./appState";

describe("app state helpers", () => {
  it("filters devices to mounted media only", () => {
    expect(
      mountedDevices([
        { device_path: "/dev/sr0", has_media: true, mount_path: "/media/DISC" },
        { device_path: "/dev/sr1", has_media: false, mount_path: null }
      ])
    ).toEqual([{ device_path: "/dev/sr0", has_media: true, mount_path: "/media/DISC" }]);
  });

  it("formats progress for stable display", () => {
    expect(formatProgress(0)).toBe("0%");
    expect(formatProgress(0.426)).toBe("43%");
    expect(formatProgress(1)).toBe("100%");
  });

  it("maps job status to UI tone", () => {
    expect(statusTone("completed")).toBe("good");
    expect(statusTone("failed")).toBe("bad");
    expect(statusTone("running")).toBe("active");
  });

  it("defaults Home Restore to maximum recovery and faithful restore", () => {
    expect(defaultRestoreControls()).toEqual({
      lane: "home",
      recoveryMode: "maximum",
      restoreMode: "faithful"
    });
  });

  it("maps preview operations to stable user-facing labels", () => {
    expect(previewOperationLabel("recovering")).toBe("Recovering original frame");
    expect(previewOperationLabel("interpolating")).toBe("Interpolating missing frames");
    expect(previewOperationLabel("reconstructing")).toBe("AI reconstructing damaged section");
    expect(previewOperationLabel("enhancing")).toBe("Enhancing restored section");
    expect(previewOperationLabel("exporting")).toBe("Exporting final video");
  });

  it("extracts timeline markers from report ranges", () => {
    expect(
      timelineMarkers({
        timeline: {
          ranges: [
            { start_seconds: 1, end_seconds: 2, state: "damaged" },
            { start_seconds: 3, end_seconds: 3.5, state: "interpolated" }
          ]
        }
      })
    ).toEqual([
      { start: 1, end: 2, state: "damaged" },
      { start: 3, end: 3.5, state: "interpolated" }
    ]);
  });

  it("hides Pro controls until verification is approved", () => {
    expect(proControlsAvailable({ verification_status: "pending" })).toBe(false);
    expect(proControlsAvailable({ verification_status: "approved" })).toBe(true);
  });
});
