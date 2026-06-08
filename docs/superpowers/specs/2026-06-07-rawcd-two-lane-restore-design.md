# RawCD Two-Lane Restore Design

## Purpose

RawCD should become an end-to-end optical media restoration product for normal users and verified professional users. The main user promise is simple: insert an old personal disc, recover as much original video as possible, repair damaged sections automatically, preview progress frame by frame, and export usable video files with a clear report.

The product must not feel like FFmpeg with a skin. It should feel like a memory rescue desk for families and a controlled restoration workstation for studios.

## Product Lanes

### Home Restore

Home Restore is for families, collectors, and non-technical users restoring personal media: wedding DVDs, school functions, old home videos, camera DVDs, VCDs, and data-video discs.

Home Restore defaults to maximum recovery. The app scans the external USB optical drive, inspects the disc, creates a recovery source when needed, extracts playable titles or clips, repairs damaged frames automatically, shows live preview, and exports MP4 files.

The default output mode is Faithful Restore. It preserves the source look, timing, resolution, grain, and color as much as possible while repairing damage. Enhanced Restore is an explicit option for users who want denoise, upscale, sharpen, stabilization, or color improvement.

### Studio / Pro Restore

Studio / Pro Restore is for directors, production houses, archives, and rights holders. It uses the same core engine but adds verified access, project metadata, rights confirmation, batch restoration, advanced provider routing, archival formats, and audit reports.

Pro access requires background and organization details before enabling commercial or movie restoration workflows. Each Pro project must record project name, organization, rights confirmation, source media description, selected providers, export settings, and repair audit data.

## Rights And Safety

RawCD is not a piracy tool. Home Restore must refuse protected commercial discs and explain the reason in plain language. Studio / Pro Restore may support commercial restoration only through a verified rights workflow. RawCD should not bundle DRM-bypass tooling or advertise circumvention.

Protected-media detection should produce a clear result:

- Home user: "This disc appears protected. RawCD restores personal media and cannot process protected commercial discs."
- Pro user without verification: "Commercial restoration requires verified rights-holder access."
- Verified Pro user: route through authorized-source workflows only.

## Recovery Flow

RawCD supports two recovery levels.

Quick Convert is the initial path for readable discs. It extracts detected sources and converts them with minimal setup.

Maximum Recovery is the default for old or damaged discs. It should create or reuse a recovery image where possible, retry bad reads aggressively, preserve partial results, and continue downstream extraction from the best available source.

If data recovery cannot read some sections, RawCD still exports recoverable content and records damage. Future capture-card fallback can be added for discs that play in standalone DVD players but fail in data extraction.

## Frame Timeline

Every output video should have a frame timeline. Each frame or frame range must have a provenance state:

- original: frame recovered directly from source media
- damaged: source frame decoded but has freeze, corruption, heavy artifacts, or missing macroblocks
- missing: source frame could not be recovered
- interpolated: generated between neighboring original frames
- generated: reconstructed from model inference when source data was missing or unusable
- enhanced: original or repaired frame was denoised, upscaled, stabilized, sharpened, or color-adjusted
- skipped: frame could not be recovered or reconstructed safely

The UI can summarize this for normal users, but the engine must keep the underlying states.

## Repair And Enhancement

Automatic repair is the default. RawCD should repair small damaged ranges without asking the user to make technical decisions. The UI should show live progress and preview frames so the user feels the work is actually happening.

Faithful Restore repairs damage while preserving the original character. Enhanced Restore applies optional improvements such as denoise, deinterlace, artifact cleanup, upscale, stabilization, sharpening, and color correction.

Large generated sections must be labeled clearly in the report. RawCD should not pretend generated frames are original frames.

## Enhancement Provider Layer

RawCD needs interchangeable providers instead of one hard-coded AI path.

Open Local providers cover free/local tools such as FFmpeg filters, OpenCV/VapourSynth filters, RIFE-style interpolation, FILM-style interpolation, and Real-ESRGAN-style upscaling.

Managed Local providers are tools RawCD can install, configure, test, and run for the user when licensing permits.

Ollama providers support local model discovery, health checks, image/vision-capable models, and experimental image-generation paths where available. Ollama should be one provider, not the whole architecture.

Topaz is an optional premium provider. RawCD can detect a licensed Topaz Video installation, invoke official CLI workflows where available, or connect to Topaz API with the user's key. RawCD must not copy or reverse-engineer Topaz models.

Cloud/API providers allow advanced users to connect their own API keys for image or video restoration providers. Keys must be stored locally and tested before use.

The provider layer should expose capabilities, not brand-specific assumptions: interpolation, inpainting, denoise, deinterlace, upscale, stabilization, color correction, artifact cleanup, and preview rendering.

## Core Architecture

Device Layer scans USB optical drives, mount status, drive health, and manual source paths.

Rescue Layer performs maximum recovery, creates recovery images or work sources, records bad reads, and supports resume.

Disc Parser identifies DVD-Video, VCD/SVCD, data-video, CD-ROM/data, unknown discs, and protected media.

Extraction Layer extracts titles, clips, audio, subtitles, and chapter metadata from the best available source.

Frame Timeline maps frame provenance, damaged ranges, missing ranges, repair decisions, and output frame lineage.

Repair Layer runs freeze detection, corruption detection, interpolation, inpainting/generation, denoise, deinterlace, upscale, stabilization, and color correction.

Model Provider Layer connects local tools, managed models, Ollama, Topaz, and cloud/API providers through capability-based adapters.

Job Orchestrator runs long jobs, cancellation, pause/resume, progress, preview updates, and logs.

Export Layer creates MP4 outputs for Home Restore and archival/intermediate formats for Studio / Pro Restore.

Report Layer creates readable Home summaries and detailed Pro audit reports.

## User Experience

Home Restore should have a clear flow:

1. Connect external USB CD/DVD drive.
2. Insert personal disc.
3. Scan and select source.
4. Choose Faithful Restore or Enhanced Restore.
5. Start Maximum Recovery.
6. Watch frame-by-frame preview and timeline markers.
7. Receive final video and report.

The interface should avoid technical overload. It can show technical details inside expandable sections.

Studio / Pro Restore should expose advanced controls only after verification. It should support project setup, batch sources, provider choice, archival export presets, rights metadata, and audit reports.

## Existing Codebase Fit

RawCD already has a useful base:

- `rawcd/devices.py` scans Linux optical devices with `lsblk`.
- `rawcd/disc.py` classifies DVD-Video, VCD/SVCD, and data-video layouts.
- `rawcd/converter.py` converts detected sources to MP4 and runs freeze detection.
- `rawcd/jobs.py` runs asynchronous conversion jobs.
- `rawcd/api.py` exposes the Python engine through FastAPI.
- `src/main.ts` provides the Tauri/Vite UI.

The next implementation should not replace everything at once. It should refactor the current conversion path into reusable modules, then add recovery, frame timeline, providers, preview, and Pro controls step by step.

## Implementation Phases

The implementation should be split into six phases:

1. Refactor the current engine into reusable recovery-oriented boundaries.
2. Add maximum recovery work sources and richer disc parsing.
3. Add frame timeline, damage detection, and automatic repair decisions.
4. Add enhancement provider adapters, including local/open providers and optional Topaz/Ollama/cloud configuration.
5. Add user-friendly live preview and Home Restore workflow.
6. Add Studio / Pro verification, rights workflow, archival exports, and audit reports.

Each phase must be independently testable.

## Non-Goals For The First Build

The first build will not guarantee perfect recovery of physically unreadable media.

The first build will not bypass DRM or copy protection.

The first build will not clone proprietary Topaz internals.

The first build will not require cloud AI to complete a normal Home Restore job.

The first build will not ship with every possible AI model. It will ship a provider framework and a curated starting set.

## Research Notes

Ollama supports vision input and has experimental image generation support through OpenAI-compatible endpoints. Because the image generation endpoint is experimental, RawCD should use Ollama through an adapter and keep alternative providers available.

Topaz Video exposes public CLI and API workflows for enhancement, upscaling, interpolation, and stabilization. RawCD can integrate with official user-owned Topaz access but must not copy its proprietary internals.

Open research and open tooling can cover important restoration categories: RIFE/FILM-style frame interpolation, Real-ESRGAN-style upscaling, FFmpeg/VapourSynth/OpenCV filtering, and traditional deinterlacing/stabilization.

## Success Criteria

Home users can restore an old personal disc without using a terminal.

The system clearly separates original, repaired, interpolated, generated, enhanced, and skipped frames.

Maximum Recovery can preserve partial results and resume long work.

Enhanced Restore is optional and never silently changes a faithful output.

Provider adapters can be added without changing the recovery pipeline.

Protected media is detected and refused in Home Restore.

Studio / Pro Restore is gated behind verification and records rights metadata.
