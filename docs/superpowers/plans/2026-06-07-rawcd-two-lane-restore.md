# RawCD Two-Lane Restoration Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build RawCD into a modular two-lane optical media restoration platform with Home Restore, Studio / Pro Restore, maximum recovery, frame-level repair, live preview, and interchangeable enhancement providers.

**Architecture:** Keep the current Tauri + FastAPI + Python engine shape, but refactor conversion into reusable recovery, parsing, timeline, repair, provider, export, and report boundaries. Each phase produces working software and tests before the next phase starts.

**Tech Stack:** Python 3.10+, FastAPI, pytest, FFmpeg/FFprobe, Tauri 2, TypeScript, Vite, Vitest, optional local tools such as ddrescue-style rescue utilities, RIFE/FILM/Real-ESRGAN adapters, Ollama, and optional Topaz CLI/API adapters.

---

## Build Strategy

Build this in six phases. Do not jump to AI repair before the recovery and timeline foundations exist. The product needs a reliable source-of-truth pipeline before it can safely automate reconstruction.

Each phase has:

- a narrow product goal
- exact module boundaries
- test targets
- UI/API surface
- manual verification
- exit criteria

Recommended execution order:

1. Phase 1: Core engine refactor
2. Phase 2: Maximum recovery source
3. Phase 3: Frame timeline and automatic repair decisions
4. Phase 4: Enhancement provider layer
5. Phase 5: Home Restore UX and live preview
6. Phase 6: Studio / Pro workflow and archival exports

## Target File Structure

Create these Python modules over the phases:

- `rawcd/models.py`: shared dataclasses/enums for sources, recovery, frames, providers, exports, and reports
- `rawcd/recovery.py`: recovery work source creation, retry strategy, external rescue-tool adapter
- `rawcd/source.py`: source selection between mounted paths, recovered images, and future capture sources
- `rawcd/parser.py`: richer disc parsing and protected-media classification
- `rawcd/extraction.py`: title/clip extraction planning and FFmpeg command generation
- `rawcd/timeline.py`: frame provenance timeline and damaged-range tracking
- `rawcd/damage.py`: freeze, corruption, missing-frame, and artifact detection
- `rawcd/providers/base.py`: provider capabilities and adapter protocol
- `rawcd/providers/local.py`: FFmpeg/OpenCV/local model provider stubs
- `rawcd/providers/ollama.py`: Ollama health, model list, and capability detection
- `rawcd/providers/topaz.py`: optional Topaz CLI/API adapter
- `rawcd/providers/cloud.py`: generic user API-key provider registry
- `rawcd/repair_pipeline.py`: repair decision engine and provider routing
- `rawcd/exporter.py`: Home MP4 and Pro archival export profiles
- `rawcd/reports.py`: Home summary and Pro audit report generation
- `rawcd/settings.py`: local settings, provider keys, Pro status, and hardware profile

Modify these existing files gradually:

- `rawcd/disc.py`: keep compatibility, then delegate to `rawcd/parser.py`
- `rawcd/converter.py`: shrink into a compatibility wrapper around extraction/export/repair
- `rawcd/jobs.py`: add richer job stages, preview events, pause/resume later
- `rawcd/api.py`: add endpoints for recovery, providers, preview, reports, and Pro workflow
- `src/engineClient.ts`: add matching TypeScript types and API methods
- `src/appState.ts`: add state helpers for modes, providers, frames, and reports
- `src/main.ts`: split later if it grows too large; keep early changes conservative
- `src/styles.css`: add timeline, preview, provider, and Pro workflow surfaces

## Phase 1: Core Engine Refactor

**Product goal:** Keep current conversion behavior working while introducing stable engine boundaries for future recovery and repair.

**Why first:** The current `MediaConverter` mixes output naming, conversion, freeze detection, warnings, and repair hooks. Maximum recovery and AI repair will be hard to add safely until source, extraction, timeline, repair, export, and report concepts are explicit.

### Task 1.1: Add shared engine models

**Files:**

- Create: `rawcd/models.py`
- Test: `tests/test_models.py`

- [ ] Define enums and dataclasses for `RestoreLane`, `RestoreMode`, `RecoveryMode`, `SourceState`, `FrameState`, `ProviderKind`, `ProviderCapability`, `RestoreSource`, `FrameRange`, `FrameTimeline`, `RestoreReport`, and `ExportProfile`.
- [ ] Write tests that assert enum values are stable strings used by the API.
- [ ] Run: `pytest tests/test_models.py -v`
- [ ] Expected: tests pass.
- [ ] Commit: `git add rawcd/models.py tests/test_models.py && git commit -m "feat: add shared restoration models"`

Minimum API values to include:

```python
class RestoreLane(str, Enum):
    HOME = "home"
    PRO = "pro"

class RestoreMode(str, Enum):
    FAITHFUL = "faithful"
    ENHANCED = "enhanced"

class RecoveryMode(str, Enum):
    QUICK = "quick"
    MAXIMUM = "maximum"

class FrameState(str, Enum):
    ORIGINAL = "original"
    DAMAGED = "damaged"
    MISSING = "missing"
    INTERPOLATED = "interpolated"
    GENERATED = "generated"
    ENHANCED = "enhanced"
    SKIPPED = "skipped"
```

### Task 1.2: Introduce source planning

**Files:**

- Create: `rawcd/source.py`
- Test: `tests/test_source.py`
- Modify: `rawcd/jobs.py`

- [ ] Add a `SourcePlan` dataclass that can represent a mounted path today and recovered image paths later.
- [ ] Add `create_source_plan(input_path: Path, recovery_mode: RecoveryMode)`.
- [ ] Keep existing `ConversionRequest.source_paths` working to avoid breaking UI.
- [ ] Write tests for quick mounted source and maximum recovery requested source.
- [ ] Run: `pytest tests/test_source.py tests/test_jobs.py -v`
- [ ] Expected: tests pass.
- [ ] Commit: `git add rawcd/source.py rawcd/jobs.py tests/test_source.py && git commit -m "feat: add restore source planning"`

### Task 1.3: Split export command generation from conversion

**Files:**

- Create: `rawcd/exporter.py`
- Test: `tests/test_exporter.py`
- Modify: `rawcd/ffmpeg_tools.py`
- Modify: `rawcd/converter.py`

- [ ] Move MP4 profile decisions into `ExportProfile`.
- [ ] Preserve existing H.264/AAC output as the Home MP4 profile.
- [ ] Add enum-backed profiles for `HOME_MP4`, `PRORES_422_HQ`, `DNXHR_HQX`, and `FFV1_MKV`.
- [ ] Keep `build_mp4_command()` as a compatibility wrapper.
- [ ] Write tests proving the Home MP4 command remains compatible with current behavior.
- [ ] Run: `pytest tests/test_exporter.py tests/test_converter.py tests/test_ffmpeg_tools.py -v`
- [ ] Expected: tests pass.
- [ ] Commit: `git add rawcd/exporter.py rawcd/ffmpeg_tools.py rawcd/converter.py tests/test_exporter.py && git commit -m "refactor: isolate export profiles"`

### Phase 1 Verification

- [ ] Run: `pytest -q`
- [ ] Run: `npm test`
- [ ] Run: `npm run build`
- [ ] Manual: start engine and confirm current scan, inspect, and Convert to MP4 still work on sample data or existing fixtures.

**Exit criteria:** Existing RawCD functionality still works, and future phases can consume shared models/source/export modules without editing conversion internals directly.

## Phase 2: Maximum Recovery Source

**Product goal:** Add a first version of Maximum Recovery that creates a durable work source and records recovery health before extraction.

**Why second:** Old disc restoration starts with recovering source data. AI repair cannot reconstruct what the engine never tracked.

### Task 2.1: Add recovery job model and status

**Files:**

- Modify: `rawcd/models.py`
- Create: `rawcd/recovery.py`
- Test: `tests/test_recovery.py`

- [ ] Add `RecoveryAttempt`, `RecoveryResult`, and `RecoverySeverity`.
- [ ] Implement `RecoveryPlanner.plan(input_path, output_dir, mode)` returning a quick passthrough plan or maximum recovery plan.
- [ ] For maximum mode, create a deterministic work directory name under the selected output directory, such as `.rawcd-work/<disc-label-or-hash>/`.
- [ ] Tests should assert maximum mode produces a work directory and quick mode does not.
- [ ] Run: `pytest tests/test_recovery.py -v`
- [ ] Commit: `git add rawcd/models.py rawcd/recovery.py tests/test_recovery.py && git commit -m "feat: add recovery planning"`

### Task 2.2: Add external rescue-tool adapter

**Files:**

- Modify: `rawcd/recovery.py`
- Test: `tests/test_recovery.py`

- [ ] Add a `RescueToolRunner` protocol with `run(command: list[str])`.
- [ ] Add a `DdrescueAdapter` that builds commands but can be tested without running the real tool.
- [ ] Detect missing rescue tool and fall back to direct source mode with a warning.
- [ ] Record retry count, image path, map/log path, and warnings in `RecoveryResult`.
- [ ] Run: `pytest tests/test_recovery.py -v`
- [ ] Commit: `git add rawcd/recovery.py tests/test_recovery.py && git commit -m "feat: add maximum recovery adapter"`

### Task 2.3: Expand disc parser

**Files:**

- Create: `rawcd/parser.py`
- Modify: `rawcd/disc.py`
- Test: `tests/test_parser.py`
- Modify: `tests/test_disc_detection.py`

- [ ] Move classification into `DiscParser`.
- [ ] Keep `DiscClassifier.classify()` delegating to the parser for compatibility.
- [ ] Add result categories for `dvd_video`, `vcd`, `data_video`, `data_disc`, `protected_media`, and `unknown`.
- [ ] Detect likely protected DVD markers from FFmpeg/FFprobe stderr and known layout signs without attempting bypass.
- [ ] Tests should cover personal DVD layout, VCD layout, data video, data disc with no video, missing path, and protected-media marker parsing.
- [ ] Run: `pytest tests/test_parser.py tests/test_disc_detection.py -v`
- [ ] Commit: `git add rawcd/parser.py rawcd/disc.py tests/test_parser.py tests/test_disc_detection.py && git commit -m "feat: add richer disc parsing"`

### Task 2.4: API support for recovery mode

**Files:**

- Modify: `rawcd/api.py`
- Modify: `rawcd/jobs.py`
- Modify: `src/engineClient.ts`
- Test: `tests/test_api.py`
- Test: `src/engineClient.test.ts`

- [ ] Extend start conversion request with `recovery_mode: "quick" | "maximum"` and `restore_mode: "faithful" | "enhanced"`.
- [ ] Default old clients to `quick` and `faithful`.
- [ ] Serialize recovery warnings in job status.
- [ ] Write Python API tests for default compatibility and explicit maximum mode.
- [ ] Write TypeScript client tests for the request shape.
- [ ] Run: `pytest tests/test_api.py -v && npm test`
- [ ] Commit: `git add rawcd/api.py rawcd/jobs.py src/engineClient.ts tests/test_api.py src/engineClient.test.ts && git commit -m "feat: expose recovery mode in API"`

### Phase 2 Verification

- [ ] Run: `pytest -q`
- [ ] Run: `npm test`
- [ ] Manual: use a mounted sample path and start a Quick job.
- [ ] Manual: start a Maximum job without rescue tooling installed and confirm the app warns but still attempts direct extraction.

**Exit criteria:** RawCD can represent quick vs maximum recovery, create a work source plan, and warn clearly when deep rescue tooling is unavailable.

## Phase 3: Frame Timeline And Automatic Repair

**Product goal:** Track every damaged or repaired section with frame provenance and make automatic repair decisions.

**Why third:** The user wants automatic frame repair plus preview. The system needs a timeline before preview or model routing can be meaningful.

### Task 3.1: Add frame timeline model

**Files:**

- Create: `rawcd/timeline.py`
- Test: `tests/test_timeline.py`

- [ ] Implement `FrameTimeline` creation from duration, frame rate, and known damaged ranges.
- [ ] Add methods: `mark_range(start_seconds, end_seconds, state, reason)` and `summary()`.
- [ ] Summary should count original, damaged, missing, interpolated, generated, enhanced, and skipped ranges.
- [ ] Tests should cover overlapping ranges and stable summary output.
- [ ] Run: `pytest tests/test_timeline.py -v`
- [ ] Commit: `git add rawcd/timeline.py tests/test_timeline.py && git commit -m "feat: add frame timeline"`

### Task 3.2: Add damage detection module

**Files:**

- Create: `rawcd/damage.py`
- Modify: `rawcd/repair.py`
- Test: `tests/test_damage.py`
- Modify: `tests/test_ai_repair.py`

- [ ] Keep existing freeze parser.
- [ ] Add `DamageDetector` that can combine freeze ranges, FFmpeg decode warnings, and missing-frame markers into normalized damaged ranges.
- [ ] Include severity: `minor`, `moderate`, `major`.
- [ ] Tests should cover freeze-only input and decode-warning input.
- [ ] Run: `pytest tests/test_damage.py tests/test_ai_repair.py -v`
- [ ] Commit: `git add rawcd/damage.py rawcd/repair.py tests/test_damage.py tests/test_ai_repair.py && git commit -m "feat: normalize frame damage detection"`

### Task 3.3: Add repair decision engine

**Files:**

- Create: `rawcd/repair_pipeline.py`
- Test: `tests/test_repair_pipeline.py`

- [ ] Implement repair decisions based on gap size and available capabilities.
- [ ] Decision rules:
  - 1 to 5 missing frames: auto interpolate.
  - 6 to 48 missing frames: auto repair and mark preview recommended.
  - More than 2 seconds missing: mark creative reconstruction and require report labeling.
  - If no provider supports the needed capability: mark skipped with warning.
- [ ] Tests should assert decisions for tiny gap, medium gap, large gap, and no provider.
- [ ] Run: `pytest tests/test_repair_pipeline.py -v`
- [ ] Commit: `git add rawcd/repair_pipeline.py tests/test_repair_pipeline.py && git commit -m "feat: add automatic repair decisions"`

### Task 3.4: Wire timeline summary into conversion result

**Files:**

- Modify: `rawcd/converter.py`
- Modify: `rawcd/jobs.py`
- Modify: `rawcd/api.py`
- Test: `tests/test_converter.py`
- Test: `tests/test_jobs.py`
- Test: `tests/test_api.py`

- [ ] Add timeline summary to job report under `report["timeline"]`.
- [ ] Keep existing `report["repair"]` fields.
- [ ] Add warnings when generated or skipped frames exist.
- [ ] Tests should confirm old outputs still serialize and new timeline fields exist.
- [ ] Run: `pytest tests/test_converter.py tests/test_jobs.py tests/test_api.py -v`
- [ ] Commit: `git add rawcd/converter.py rawcd/jobs.py rawcd/api.py tests/test_converter.py tests/test_jobs.py tests/test_api.py && git commit -m "feat: report frame timeline summary"`

### Phase 3 Verification

- [ ] Run: `pytest -q`
- [ ] Use synthetic FFmpeg stderr fixture with freeze ranges.
- [ ] Confirm job status includes timeline summary.

**Exit criteria:** RawCD can explain how much output is original, damaged, interpolated, generated, enhanced, or skipped before the UI preview exists.

## Phase 4: Enhancement Provider Layer

**Product goal:** Add provider adapters for local/free tools, Ollama, optional Topaz, and future cloud providers without coupling the repair pipeline to one vendor.

**Why fourth:** Provider routing should consume timeline and repair decisions. It should not own the recovery pipeline.

### Task 4.1: Add provider base protocol

**Files:**

- Create: `rawcd/providers/__init__.py`
- Create: `rawcd/providers/base.py`
- Test: `tests/test_providers_base.py`

- [ ] Define `ProviderCapability` values: `interpolation`, `inpainting`, `denoise`, `deinterlace`, `upscale`, `stabilization`, `color_correction`, `artifact_cleanup`, `preview_render`.
- [ ] Define `ProviderInfo`, `ProviderHealth`, and `EnhancementProvider` protocol.
- [ ] Providers must expose `id`, `label`, `kind`, `capabilities`, `health_check()`, and `estimate()`.
- [ ] Tests should assert capability serialization and health states.
- [ ] Run: `pytest tests/test_providers_base.py -v`
- [ ] Commit: `git add rawcd/providers tests/test_providers_base.py && git commit -m "feat: add enhancement provider protocol"`

### Task 4.2: Add local/open provider adapter

**Files:**

- Create: `rawcd/providers/local.py`
- Test: `tests/test_providers_local.py`

- [ ] Implement `LocalFfmpegProvider` for deinterlace, denoise, artifact cleanup, and preview rendering.
- [ ] Implement command builders only; do not require GPU models in tests.
- [ ] Add capability-based estimates: free cost, local execution, speed unknown unless benchmarked.
- [ ] Tests should assert command generation and provider health when `ffmpeg` is present or absent.
- [ ] Run: `pytest tests/test_providers_local.py -v`
- [ ] Commit: `git add rawcd/providers/local.py tests/test_providers_local.py && git commit -m "feat: add local enhancement provider"`

### Task 4.3: Add Ollama provider adapter

**Files:**

- Create: `rawcd/providers/ollama.py`
- Test: `tests/test_providers_ollama.py`

- [ ] Add configurable base URL, defaulting to `http://127.0.0.1:11434`.
- [ ] Implement health check against Ollama API.
- [ ] Implement model listing and capability inference from model metadata where available.
- [ ] Do not assume every Ollama model can generate or edit frames.
- [ ] Tests should use fake HTTP responses for offline operation.
- [ ] Run: `pytest tests/test_providers_ollama.py -v`
- [ ] Commit: `git add rawcd/providers/ollama.py tests/test_providers_ollama.py && git commit -m "feat: add ollama provider discovery"`

### Task 4.4: Add optional Topaz provider adapter

**Files:**

- Create: `rawcd/providers/topaz.py`
- Test: `tests/test_providers_topaz.py`

- [ ] Detect Topaz CLI through configured path or known install paths.
- [ ] Expose capabilities: interpolation, upscale, stabilization, artifact cleanup, denoise, deinterlace when supported by user installation.
- [ ] Add API-key mode for Topaz API as a separate provider config.
- [ ] Show license-required health result when not installed or not authenticated.
- [ ] Do not bundle or download Topaz.
- [ ] Tests should use fake filesystem and fake command runner.
- [ ] Run: `pytest tests/test_providers_topaz.py -v`
- [ ] Commit: `git add rawcd/providers/topaz.py tests/test_providers_topaz.py && git commit -m "feat: add optional topaz provider"`

### Task 4.5: Add provider registry and settings

**Files:**

- Create: `rawcd/settings.py`
- Modify: `rawcd/api.py`
- Modify: `src/engineClient.ts`
- Test: `tests/test_settings.py`
- Test: `tests/test_api.py`
- Test: `src/engineClient.test.ts`

- [ ] Store provider settings in a local JSON file under the user's config directory.
- [ ] Never write raw API keys into reports or logs.
- [ ] Add API endpoints:
  - `GET /providers`
  - `POST /providers/{provider_id}/test`
  - `POST /providers/{provider_id}/configure`
- [ ] TypeScript client should expose `listProviders`, `testProvider`, and `configureProvider`.
- [ ] Tests should assert API keys are redacted in serialized provider responses.
- [ ] Run: `pytest tests/test_settings.py tests/test_api.py -v && npm test`
- [ ] Commit: `git add rawcd/settings.py rawcd/api.py src/engineClient.ts tests/test_settings.py tests/test_api.py src/engineClient.test.ts && git commit -m "feat: add provider registry settings"`

### Phase 4 Verification

- [ ] Run: `pytest -q`
- [ ] Run: `npm test`
- [ ] Manual: call `GET /providers` and confirm local provider appears.
- [ ] Manual: test Topaz provider on a machine without Topaz and confirm it reports "license or install required" without crashing.
- [ ] Manual: test Ollama provider when Ollama is not running and confirm it reports unavailable cleanly.

**Exit criteria:** Repair decisions can choose providers by capability, and the app can show local/free, Ollama, Topaz, and cloud/API options without hard-coding one model.

## Phase 5: Home Restore UX And Live Preview

**Product goal:** Turn the engine into a normal-user product flow: scan, choose faithful/enhanced, run maximum recovery, preview frame progress, export video, read simple report.

**Why fifth:** The UX should sit on stable engine APIs, not fake progress.

### Task 5.1: Add restore-mode UI controls

**Files:**

- Modify: `src/main.ts`
- Modify: `src/appState.ts`
- Modify: `src/styles.css`
- Test: `src/appState.test.ts`

- [ ] Add state for `recoveryMode` and `restoreMode`.
- [ ] Default to `maximum` recovery and `faithful` restore.
- [ ] Add UI control labels:
  - `Faithful Restore`
  - `Enhanced Restore`
  - `Maximum Recovery`
- [ ] Keep advanced provider settings behind expandable controls.
- [ ] Tests should assert defaults.
- [ ] Run: `npm test`
- [ ] Commit: `git add src/main.ts src/appState.ts src/styles.css src/appState.test.ts && git commit -m "feat: add restore mode controls"`

### Task 5.2: Add timeline preview data endpoint

**Files:**

- Modify: `rawcd/jobs.py`
- Modify: `rawcd/api.py`
- Modify: `src/engineClient.ts`
- Test: `tests/test_jobs.py`
- Test: `tests/test_api.py`
- Test: `src/engineClient.test.ts`

- [ ] Store preview state on jobs: current frame number, current timestamp, current operation, preview image path when available.
- [ ] Add `GET /get_job_preview/{job_id}`.
- [ ] Add TypeScript `getJobPreview(jobId)`.
- [ ] Tests should cover unknown job and running job preview serialization.
- [ ] Run: `pytest tests/test_jobs.py tests/test_api.py -v && npm test`
- [ ] Commit: `git add rawcd/jobs.py rawcd/api.py src/engineClient.ts tests/test_jobs.py tests/test_api.py src/engineClient.test.ts && git commit -m "feat: expose job preview state"`

### Task 5.3: Add live preview panel

**Files:**

- Modify: `src/main.ts`
- Modify: `src/styles.css`
- Test: `src/appState.test.ts`

- [ ] Show preview section during running jobs.
- [ ] Display operation text:
  - `Recovering original frame`
  - `Interpolating missing frames`
  - `AI reconstructing damaged section`
  - `Enhancing restored section`
  - `Exporting final video`
- [ ] Show timeline markers using frame states from report/preview.
- [ ] Do not show technical provider logs by default.
- [ ] Run: `npm test && npm run build`
- [ ] Commit: `git add src/main.ts src/styles.css src/appState.test.ts && git commit -m "feat: add live restore preview"`

### Task 5.4: Add Home report UI

**Files:**

- Create: `rawcd/reports.py`
- Modify: `rawcd/converter.py`
- Modify: `rawcd/api.py`
- Modify: `src/main.ts`
- Test: `tests/test_reports.py`
- Test: `tests/test_converter.py`

- [ ] Generate Home report fields: recovered clips, output files, damaged sections, reconstructed sections, skipped sections, provider used, and plain-language warnings.
- [ ] Add output path for a JSON report next to the video output.
- [ ] UI should show a simple summary and link/open action.
- [ ] Run: `pytest tests/test_reports.py tests/test_converter.py tests/test_api.py -v && npm test`
- [ ] Commit: `git add rawcd/reports.py rawcd/converter.py rawcd/api.py src/main.ts tests/test_reports.py tests/test_converter.py && git commit -m "feat: add home restoration report"`

### Phase 5 Verification

- [ ] Run: `pytest -q`
- [ ] Run: `npm test`
- [ ] Run: `npm run build`
- [ ] Start browser preview: `python3 -m rawcd.server --host 127.0.0.1 --port 8765` and `npm run dev -- --host 127.0.0.1`.
- [ ] Verify the first screen is the usable Home Restore workflow.
- [ ] Verify buttons and labels fit at desktop and narrow widths.

**Exit criteria:** A non-technical user can run the Home Restore path, see live progress, get output files, and understand what was original versus repaired.

## Phase 6: Studio / Pro Workflow And Archival Exports

**Product goal:** Add verified Pro workflows without weakening Home mode or creating piracy risk.

**Why sixth:** Pro mode depends on core recovery, providers, reports, and export profiles. It should be gated and auditable.

### Task 6.1: Add Pro verification model

**Files:**

- Modify: `rawcd/models.py`
- Modify: `rawcd/settings.py`
- Test: `tests/test_settings.py`

- [ ] Add `ProVerificationStatus`: `not_requested`, `pending`, `approved`, `rejected`.
- [ ] Add `ProProfile`: name, organization, email, country, intended use, verification status, approved timestamp.
- [ ] Store locally for now, with a future server verification field.
- [ ] Tests should assert unapproved users cannot enable Pro projects.
- [ ] Run: `pytest tests/test_settings.py -v`
- [ ] Commit: `git add rawcd/models.py rawcd/settings.py tests/test_settings.py && git commit -m "feat: add pro verification model"`

### Task 6.2: Add rights workflow

**Files:**

- Create: `rawcd/rights.py`
- Modify: `rawcd/api.py`
- Test: `tests/test_rights.py`
- Test: `tests/test_api.py`

- [ ] Add `RightsDeclaration`: project name, organization, source title, rights basis, permission reference, declaration timestamp.
- [ ] Require rights declaration for `RestoreLane.PRO`.
- [ ] Refuse protected-media jobs in Home mode.
- [ ] Refuse Pro commercial jobs when Pro status is not approved.
- [ ] Tests should cover Home refusal, unapproved Pro refusal, and approved Pro declaration success.
- [ ] Run: `pytest tests/test_rights.py tests/test_api.py -v`
- [ ] Commit: `git add rawcd/rights.py rawcd/api.py tests/test_rights.py tests/test_api.py && git commit -m "feat: add rights declaration workflow"`

### Task 6.3: Add archival export profiles

**Files:**

- Modify: `rawcd/exporter.py`
- Test: `tests/test_exporter.py`

- [ ] Implement Pro export commands for:
  - ProRes 422 HQ `.mov`
  - DNxHR HQX `.mov`
  - FFV1 `.mkv`
  - WAV audio extraction when requested
- [ ] Preserve metadata where possible.
- [ ] Tests should assert command shapes and output extensions.
- [ ] Run: `pytest tests/test_exporter.py -v`
- [ ] Commit: `git add rawcd/exporter.py tests/test_exporter.py && git commit -m "feat: add archival export profiles"`

### Task 6.4: Add Pro audit report

**Files:**

- Modify: `rawcd/reports.py`
- Test: `tests/test_reports.py`

- [ ] Add Pro audit report fields: rights declaration, source hash where available, recovery attempts, providers, model names, generated-frame counts, export profile, operator notes, and warnings.
- [ ] Redact API keys and secrets.
- [ ] Save as JSON and Markdown.
- [ ] Tests should assert required fields and redaction.
- [ ] Run: `pytest tests/test_reports.py -v`
- [ ] Commit: `git add rawcd/reports.py tests/test_reports.py && git commit -m "feat: add pro audit reports"`

### Task 6.5: Add Pro UI lane

**Files:**

- Modify: `src/main.ts`
- Modify: `src/appState.ts`
- Modify: `src/styles.css`
- Modify: `src/engineClient.ts`
- Test: `src/appState.test.ts`
- Test: `src/engineClient.test.ts`

- [ ] Add Home / Pro segmented control.
- [ ] If Pro is not approved, show verification form and do not show commercial restoration controls.
- [ ] If Pro is approved, show project setup, rights declaration, export profile selection, provider routing, and batch-ready source list.
- [ ] Keep Home mode simple.
- [ ] Run: `npm test && npm run build`
- [ ] Commit: `git add src/main.ts src/appState.ts src/styles.css src/engineClient.ts src/appState.test.ts src/engineClient.test.ts && git commit -m "feat: add pro restore workflow"`

### Phase 6 Verification

- [ ] Run: `pytest -q`
- [ ] Run: `npm test`
- [ ] Run: `npm run build`
- [ ] Manual: confirm protected-media fixture is refused in Home.
- [ ] Manual: confirm Pro controls are hidden until approval.
- [ ] Manual: confirm approved Pro project requires rights declaration before starting.
- [ ] Manual: confirm audit report contains rights and provider metadata but no secrets.

**Exit criteria:** RawCD has a credible Studio / Pro lane that supports rights-aware restoration without turning Home mode into a piracy workflow.

## Final System Verification

- [ ] Run: `pytest -q`
- [ ] Run: `npm test`
- [ ] Run: `cargo test --manifest-path src-tauri/Cargo.toml`
- [ ] Run: `npm run build`
- [ ] Run: `npm run tauri build` on an Ubuntu-compatible machine with Tauri dependencies.
- [ ] Test Home Restore with:
  - readable personal data-video fixture
  - DVD-Video fixture
  - VCD/SVCD fixture
  - missing path
  - protected-media marker fixture
  - simulated damaged-frame fixture
- [ ] Test Provider Settings with:
  - FFmpeg available
  - Ollama not running
  - Ollama running with no suitable models
  - Topaz not installed
  - fake Topaz CLI installed
  - fake API provider with redacted key
- [ ] Test Pro Restore with:
  - unverified account
  - pending account
  - approved account
  - rights declaration missing
  - rights declaration present

## Risk Register

**Physically unreadable discs:** No software can guarantee complete recovery. Mitigation: maximum retry, partial output preservation, clear damage report, future capture-card fallback.

**Model hallucination or fake memories:** Generated frames may not represent reality. Mitigation: label generated sections, default to Faithful Restore, report provenance.

**Provider licensing:** Topaz and other providers have licensing limits. Mitigation: optional adapters, user-owned licenses/API keys, no bundled proprietary models.

**DRM and protected media:** The product could be misused if boundaries are weak. Mitigation: protected-media detection, Home refusal, Pro verification, rights declaration, audit report.

**Long jobs and user trust:** Recovery can take hours. Mitigation: live preview, staged progress, resumable work directories, clear estimated work.

**Huge scope:** The whole platform is large. Mitigation: six phases, each independently shippable and testable.

## Self-Review

Spec coverage:

- Two product lanes are covered by Phases 5 and 6.
- Maximum recovery is covered by Phase 2.
- Frame-by-frame provenance and automatic repair are covered by Phase 3.
- Local/free, Ollama, Topaz, and API-key providers are covered by Phase 4.
- Live preview is covered by Phase 5.
- Rights verification and Pro access are covered by Phase 6.

Placeholder scan:

- No task depends on an undefined future module without first creating it in an earlier phase.
- Optional future capture-card fallback is intentionally excluded from this first plan.

Type consistency:

- `RestoreLane`, `RestoreMode`, `RecoveryMode`, `FrameState`, and provider capabilities are defined before later tasks use them.
- API additions are paired with TypeScript client updates and tests.

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-06-07-rawcd-two-lane-restore.md`.

Two execution options:

1. Subagent-Driven - dispatch a fresh subagent per phase/task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using checkpoints.

Recommended: Subagent-Driven for this project because each phase touches different boundaries and needs review before the next layer.
