import { describe, expect, it } from "vitest";

import { formatProgress, mountedDevices, statusTone } from "./appState";

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
});
