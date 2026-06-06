import { describe, expect, it } from "vitest";

import { createEngineClient, createHttpEngineInvoke } from "./engineClient";

describe("engine client", () => {
  it("maps scanDevices to the Tauri scan_devices command", async () => {
    const calls: Array<[string, unknown]> = [];
    const client = createEngineClient({
      invoke: async (command, args) => {
        calls.push([command, args]);
        return [{ device_path: "/dev/sr0", has_media: true }];
      }
    });

    const devices = await client.scanDevices();

    expect(calls).toEqual([["scan_devices", undefined]]);
    expect(devices).toEqual([{ device_path: "/dev/sr0", has_media: true }]);
  });

  it("starts conversion with source paths, output directory, and ai flag", async () => {
    const calls: Array<[string, unknown]> = [];
    const client = createEngineClient({
      invoke: async (command, args) => {
        calls.push([command, args]);
        return { job_id: "job-1", status: "running" };
      }
    });

    const job = await client.startConversion({
      source_paths: ["/disc/clip.dat"],
      output_dir: "~/Videos",
      ai_repair: true,
      preserve_quality: true
    });

    expect(job.job_id).toBe("job-1");
    expect(calls).toEqual([
      [
        "start_conversion",
        {
          request: {
            source_paths: ["/disc/clip.dat"],
            output_dir: "~/Videos",
            ai_repair: true,
            preserve_quality: true
          }
        }
      ]
    ]);
  });

  it("maps HTTP fallback commands to engine endpoints", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetchImpl = async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return {
        ok: true,
        json: async () => ({ label: "Data video disc" })
      } as Response;
    };

    const invoke = createHttpEngineInvoke("http://127.0.0.1:8765", fetchImpl);
    const result = await invoke("inspect_disc", { request: { path: "/media/DISC" } });

    expect(result).toEqual({ label: "Data video disc" });
    expect(calls).toEqual([
      [
        "http://127.0.0.1:8765/inspect_disc",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: "/media/DISC" })
        }
      ]
    ]);
  });
});
