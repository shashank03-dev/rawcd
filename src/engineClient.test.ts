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
      restore_mode: "enhanced",
      export_profile: "prores_422_hq"
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
            restore_mode: "enhanced",
            export_profile: "prores_422_hq"
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

  it("maps Pro profile, rights, and report commands to Tauri commands", async () => {
    const calls: Array<[string, unknown]> = [];
    const client = createEngineClient({
      invoke: async (command, args) => {
        calls.push([command, args]);
        if (command === "get_pro_profile") return { verification_status: "pending" };
        if (command === "save_pro_profile") return { verification_status: "approved" };
        if (command === "validate_rights") return { allowed: true };
        return { json_save_path: "/tmp/report.json" };
      }
    });

    await client.getProProfile();
    await client.saveProProfile({
      name: "Asha Rao",
      organization: "Archive House",
      email: "asha@example.test",
      country: "IN",
      intended_use: "Commercial film restoration",
      verification_status: "pending"
    });
    await client.validateRights({
      lane: "pro",
      commercial_use: true,
      protected_media: true,
      rights_declaration: {
        project_name: "Restored Feature",
        organization: "Archive House",
        source_title: "Original Camera DVD",
        rights_basis: "rights_holder",
        permission_reference: "contract-2026-001"
      }
    });
    await client.writeHomeReport({
      report_path: "/tmp/report.json",
      recovered_clips: 1,
      output_files: ["/tmp/clip.mp4"],
      warnings: []
    });
    await client.writeProReport({
      job_id: "job-pro",
      json_path: "/tmp/audit.json",
      warnings: []
    });

    expect(calls.map(([command]) => command)).toEqual([
      "get_pro_profile",
      "save_pro_profile",
      "validate_rights",
      "write_home_report",
      "write_pro_report"
    ]);
  });

  it("maps job preview to the Tauri get_job_preview command", async () => {
    const calls: Array<[string, unknown]> = [];
    const client = createEngineClient({
      invoke: async (command, args) => {
        calls.push([command, args]);
        return {
          job_id: "job-1",
          current_frame: 42,
          current_timestamp: 1.68,
          current_operation: "Interpolating missing frames",
          preview_image_path: "/tmp/preview.jpg"
        };
      }
    });

    const preview = await client.getJobPreview("job-1");

    expect(preview.current_operation).toBe("Interpolating missing frames");
    expect(calls).toEqual([["get_job_preview", { jobId: "job-1" }]]);
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

  it("maps HTTP job preview command to engine endpoint", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetchImpl = async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return {
        ok: true,
        json: async () => ({ current_operation: "Exporting final video" })
      } as Response;
    };

    const invoke = createHttpEngineInvoke("http://127.0.0.1:8765", fetchImpl);
    const preview = await invoke("get_job_preview", { jobId: "job-1" });

    expect(preview).toEqual({ current_operation: "Exporting final video" });
    expect(calls).toEqual([
      ["http://127.0.0.1:8765/get_job_preview/job-1", undefined]
    ]);
  });

  it("maps HTTP Pro and report commands to engine endpoints", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetchImpl = async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return {
        ok: true,
        json: async () => ({ ok: true })
      } as Response;
    };
    const invoke = createHttpEngineInvoke("http://127.0.0.1:8765", fetchImpl);

    await invoke("get_pro_profile");
    await invoke("save_pro_profile", { request: { name: "Asha" } });
    await invoke("validate_rights", { request: { lane: "home" } });
    await invoke("write_home_report", { request: { report_path: "/tmp/r.json" } });
    await invoke("write_pro_report", { request: { job_id: "job-pro", json_path: "/tmp/a.json" } });

    expect(calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:8765/pro/profile",
      "http://127.0.0.1:8765/pro/profile",
      "http://127.0.0.1:8765/rights/validate",
      "http://127.0.0.1:8765/reports/home",
      "http://127.0.0.1:8765/reports/pro"
    ]);
  });
});
