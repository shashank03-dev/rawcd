<p align="center">
  <img src="src-tauri/icons/icon.png" alt="RawCD mark" width="96" height="96">
</p>

<h1 align="center">RawCD</h1>

<p align="center">
  A Linux-first restoration desk for converting personal, unprotected CD/DVD video media into MP4 files.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-2f6f4e">
  <img alt="Tauri" src="https://img.shields.io/badge/Tauri-2.11-2f6f4e">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Ubuntu%2022.04-2f6f4e">
  <img alt="Scope" src="https://img.shields.io/badge/Scope-Personal%20Media%20Use-2f6f4e">
</p>

## What RawCD Does

RawCD turns a USB CD/DVD drive and a personal disc archive into a local conversion workflow. It inspects the mounted disc, identifies playable clips, converts each source to MP4, and records what repair work was attempted.

It is intentionally scoped to personal, unprotected media. RawCD does not bypass DVD encryption, copy protection, or access controls.

## Interface Direction

RawCD uses a typographic restoration-lab design: pure white workspace, moss-green primary actions, correction-color state marks, and a compact clip ledger. The interface is built for repeatable work, not marketing spectacle.

| Surface | Purpose |
| --- | --- |
| Source proof | Scan Linux optical drives and inspect mounted media paths. |
| Clip ledger | Review detected video sources before conversion. |
| Repair controls | Enable AI repair and preserve-quality output settings. |
| Engine ledger | Track scan, inspection, conversion, warnings, and output paths. |

## Conversion Pipeline

```mermaid
flowchart LR
  A["USB CD/DVD drive"] --> B["Disc classifier"]
  B --> C["DVD-Video, VCD/SVCD, or data video"]
  C --> D["FFmpeg MP4 conversion"]
  D --> E["Freeze detection"]
  E --> F["Optional RIFE repair adapter"]
  F --> G["MP4 output and report"]
  E --> G
```

## Features

| Area | Current capability |
| --- | --- |
| Device scanning | Uses `lsblk` to find Linux optical drives and mounted media. |
| Disc inspection | Detects DVD-Video, VCD/SVCD, and data-video layouts. |
| Conversion | Creates one high-quality H.264/AAC MP4 per detected source. |
| Audio | Preserves the primary audio stream when present. |
| Protection handling | Refuses protected or encrypted discs with a clear message. |
| Repair analysis | Runs FFmpeg `freezedetect` to find frozen ranges. |
| AI repair adapter | Provides installer-managed `rife-ncnn-vulkan` support for interpolation workflows. |
| Desktop package | Builds a Tauri `.deb` package for Ubuntu-compatible Linux desktops. |

## Architecture

```text
RawCD
├── src/                 TypeScript UI and Tauri command client
├── src-tauri/           Tauri shell, Rust command bridge, desktop packaging
├── rawcd/               Python media engine, API, FFmpeg, repair adapters
├── tests/               Python unit and integration-style tests
├── PRODUCT.md           Product register and strategic design context
└── DESIGN.md            Visual system and UI design contract
```

The Tauri shell launches the local Python engine on `127.0.0.1:8765`, then proxies desktop commands through the engine API.

## Requirements

- Ubuntu 22.04 or compatible Linux desktop.
- USB CD/DVD drive for real-disc validation.
- `ffmpeg` and `ffprobe` on `PATH`.
- Python 3.10 or newer.
- Node.js 20.19+ or 22.12+.
- npm.
- Rust and Cargo.
- Tauri Linux build dependencies.

## Prior Setup

RawCD is currently easiest to run from source on Ubuntu or another Debian-based Linux desktop. The desktop app starts a local Python engine on `127.0.0.1:8765`, so the Python package and media tools must be available on the same machine.

Install system, media, and Tauri Linux packages:

```bash
sudo apt update
sudo apt install \
  ffmpeg \
  python3 \
  python3-venv \
  python3-pip \
  nodejs \
  npm \
  cargo \
  libwebkit2gtk-4.1-dev \
  build-essential \
  curl \
  wget \
  file \
  libxdo-dev \
  libssl-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev
```

The Tauri packages match the [official Tauri Linux prerequisites](https://v2.tauri.app/start/prerequisites/).

If your distribution provides an older Node.js package, install a current Node.js runtime with your preferred version manager before running `npm install`. Ubuntu 22.04's default `nodejs` package is usually too old for this project. If `cargo --version` is also too old, install Rust with `rustup` or another current Rust toolchain manager.

Install project dependencies from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
npm install
```

Check that the required tools are available:

```bash
python3 --version
node --version
npm --version
cargo --version
ffmpeg -version
ffprobe -version
```

Prepare a disc before launching RawCD:

1. Connect a USB CD/DVD drive.
2. Insert a personal, unprotected disc.
3. Mount the disc through your file manager, or mount it from the terminal:

```bash
lsblk -o NAME,TYPE,RM,MODEL,MOUNTPOINTS
udisksctl mount -b /dev/sr0
```

Replace `/dev/sr0` if your optical drive uses a different device path.

## User Manual

Run the full desktop app from the repository root:

```bash
source .venv/bin/activate
npm run tauri -- dev
```

The Tauri shell opens the RawCD window, starts the local engine if it is not already running, and connects the interface to the engine API.

Use RawCD in this order:

1. Insert and mount the disc.
2. Select **Scan drives**. RawCD reads Linux optical-drive data through `lsblk`.
3. Choose the detected mounted source. If the drive is not listed, enter the mount point in **Manual mount path**, for example `/media/user/MY_DISC`.
4. Select **Inspect media**. RawCD classifies the disc as DVD-Video, VCD/SVCD, data video, or unknown.
5. Review the clip ledger. RawCD lists each playable source it found before conversion starts.
6. Choose the output folder. The default is `~/Videos/RawCD`.
7. Leave **Preserve source resolution and high-quality H.264/AAC output** enabled for normal use.
8. Leave **Use AI repair** enabled if you want RawCD to attempt configured repair support for damaged or frozen ranges. If no repair adapter is configured, RawCD still reports freeze warnings.
9. Select **Convert to MP4**.
10. Watch the progress bar and engine ledger for status, warnings, output paths, and errors.
11. Use **Cancel** to request cancellation while a job is running.
12. Use **Open output** after a completed job to open the output folder.

The output is one MP4 file per detected source. RawCD creates unique filenames if the output folder already contains a file with the same name.

## Preview Without Desktop Shell

For a browser-only preview, run the engine and Vite in separate terminals.

Terminal 1:

```bash
source .venv/bin/activate
python3 -m rawcd.server --host 127.0.0.1 --port 8765
```

Terminal 2:

```bash
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:1420/
```

In browser preview mode, **Open output** does not launch the file manager because that action is only available inside the Tauri desktop shell.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| No drive appears after scanning | Confirm the disc is mounted and visible in `lsblk -o NAME,TYPE,MODEL,MOUNTPOINTS`. |
| Manual path fails | Confirm the path exists and points to the mounted disc root, not the device path. |
| Conversion fails immediately | Confirm `ffmpeg` and `ffprobe` are installed and available on `PATH`. |
| Protected-media error | RawCD does not bypass encryption, CSS, DRM, or copy protection. Use only personal, unprotected media. |
| Browser preview cannot connect | Start `python3 -m rawcd.server --host 127.0.0.1 --port 8765` before opening the Vite URL. |
| Desktop app cannot start engine | Activate the Python environment and confirm `python3 -m rawcd.server` works from the repository root. |
| AI repair warning appears | The default engine can detect frozen ranges, but a RIFE repair adapter must be configured before frames can be regenerated. |

## What RawCD Lacks Today

- RawCD does not bypass DVD encryption, CSS, DRM, region controls, or copy protection.
- RawCD does not mount discs by itself. The operating system must mount the disc first.
- RawCD does not repair unreadable sectors or physically damaged media. It depends on the drive, operating system, and FFmpeg being able to read the source.
- The current conversion model creates MP4 files from detected sources. It does not preserve DVD menus, chapters, subtitle tracks, alternate audio tracks, or title navigation.
- DVD handling is file-oriented. It does not yet combine multi-file DVD title sets into one title-aware output.
- The AI repair path is not a complete one-click restoration system yet. Freeze detection is present, and RIFE support exists as an adapter, but the default desktop engine does not configure full frame-regeneration workflow automatically.
- The app is Linux-first. macOS and Windows packages are not provided.
- The generated Debian package is suitable for local packaging checks, but the app is not yet a fully self-contained installer for a clean machine because the Python engine and external media tools still need setup.
- Real USB-drive acceptance testing still requires a USB optical drive and an unprotected personal disc.

## Development

Run the test suite:

```bash
pytest -q
npm test
cargo test --manifest-path src-tauri/Cargo.toml
```

Build the web UI:

```bash
npm run build
```

Build the Linux desktop package:

```bash
npm run tauri build
```

The generated Debian package is written to:

```text
src-tauri/target/release/bundle/deb/RawCD_0.1.0_amd64.deb
```

## Running the Engine Directly

```bash
python3 -m rawcd.server --host 127.0.0.1 --port 8765
```

Useful API endpoints:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Engine readiness check. |
| `/scan_devices` | GET | List optical drives and mounted media. |
| `/inspect_disc` | POST | Classify a mounted disc path. |
| `/start_conversion` | POST | Start an MP4 conversion job. |
| `/get_job_status/{job_id}` | GET | Read progress, warnings, outputs, and report data. |
| `/cancel_job/{job_id}` | POST | Request cancellation. |

Example inspection request:

```bash
curl -X POST http://127.0.0.1:8765/inspect_disc \
  -H "Content-Type: application/json" \
  -d '{"path":"/media/user/MY_DISC"}'
```

## Security Posture

RawCD is a local-first desktop app. The engine binds to loopback only by default and the UI is designed for personal media workflows.

Important boundaries:

- No DRM bypass.
- No remote upload path.
- No cloud processing.
- No credentials required.
- No privileged system writes beyond normal user-selected output folders.
- AI repair tooling is downloaded only when the repair adapter is used.

## Verification Status

The repository includes automated coverage for:

- Disc classification.
- FFmpeg command construction and protected-media error handling.
- Job lifecycle states.
- Device scanner parsing.
- FastAPI endpoint behavior.
- RIFE installer and interpolation command construction.
- Tauri bridge utility behavior.
- Frontend command-client and state helpers.

Real USB-drive acceptance testing still requires a USB optical drive and an unprotected personal disc.
