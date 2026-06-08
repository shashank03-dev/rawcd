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
      preserve_quality: true,
      recovery_mode: "maximum",
      restore_mode: "enhanced"
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
            preserve_quality: true,
            recovery_mode: "maximum",
            restore_mode: "enhanced"
          }
        }
      ]
    ]);
  });

  it("keeps recovery and restore modes optional for legacy conversion requests", async () => {
    const calls: Array<[string, unknown]> = [];
    const client = createEngineClient({
      invoke: async (command, args) => {
        calls.push([command, args]);
        return { job_id: "job-legacy", status: "running" };
      }
    });

    await client.startConversion({
      source_paths: ["/disc/clip.dat"],
      output_dir: "~/Videos",
      ai_repair: false,
      preserve_quality: true
    });

    expect(calls[0]).toEqual([
      "start_conversion",
      {
        request: {
          source_paths: ["/disc/clip.dat"],
          output_dir: "~/Videos",
          ai_repair: false,
          preserve_quality: true
        }
      }
    ]);
  });

  it("maps provider registry commands to Tauri commands", async () => {
    const calls: Array<[string, unknown]> = [];
    const client = createEngineClient({
      invoke: async (command, args) => {
        calls.push([command, args]);
        if (command === "list_providers") return [];
        if (command === "test_provider") return { status: "available" };
        return { id: "topaz-api", settings: { api_key_configured: true, api_key: null } };
      }
    });

    await client.listProviders();
    await client.testProvider("topaz-api");
    await client.configureProvider("topaz-api", {
      enabled: true,
      api_key: "secret",
      base_url: null
    });

    expect(calls).toEqual([
      ["list_providers", undefined],
      ["test_provider", { providerId: "topaz-api" }],
      [
        "configure_provider",
        {
          providerId: "topaz-api",
          request: { enabled: true, api_key: "secret", base_url: null }
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

  it("maps HTTP provider commands to engine endpoints", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetchImpl = async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return {
        ok: true,
        json: async () => ({ status: "available" })
      } as Response;
    };

    const invoke = createHttpEngineInvoke("http://127.0.0.1:8765", fetchImpl);
    await invoke("test_provider", { providerId: "local-ffmpeg" });
    await invoke("configure_provider", {
      providerId: "topaz-api",
      request: { api_key: "secret" }
    });

    expect(calls).toEqual([
      [
        "http://127.0.0.1:8765/providers/local-ffmpeg/test",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        }
      ],
      [
        "http://127.0.0.1:8765/providers/topaz-api/configure",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: "secret" })
        }
      ]
    ]);
  });
});
