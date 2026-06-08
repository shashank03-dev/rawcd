from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderHealthStatus
from rawcd.providers.local import LocalFfmpegProvider


class FakeCommandRunner:
    def __init__(self, result: CompletedProcess[str] | None = None) -> None:
        self.result = result or CompletedProcess(
            ["ffmpeg", "-version"],
            0,
            stdout="ffmpeg version 6.1",
            stderr="",
        )
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return self.result


class MissingCommandRunner:
    def run(self, command: list[str]) -> CompletedProcess[str]:
        raise FileNotFoundError(command[0])


class TimeoutCommandRunner:
    def run(self, command: list[str]) -> CompletedProcess[str]:
        raise TimeoutExpired(command, timeout=10)


def test_local_ffmpeg_provider_declares_open_local_capabilities() -> None:
    provider = LocalFfmpegProvider()

    assert provider.id == "local-ffmpeg"
    assert provider.label == "Local FFmpeg"
    assert provider.kind is ProviderKind.OPEN_LOCAL
    assert provider.capabilities == (
        ProviderCapability.DEINTERLACE,
        ProviderCapability.DENOISE,
        ProviderCapability.ARTIFACT_CLEANUP,
        ProviderCapability.PREVIEW_RENDER,
    )
    assert provider.info().to_dict() == {
        "id": "local-ffmpeg",
        "label": "Local FFmpeg",
        "kind": "open_local",
        "capabilities": [
            "deinterlace",
            "denoise",
            "artifact_cleanup",
            "preview_render",
        ],
    }


def test_deinterlace_command_uses_yadif_without_running_ffmpeg() -> None:
    command = LocalFfmpegProvider().build_deinterlace_command(
        Path("/disc/interlaced.vob"),
        Path("/out/progressive.mp4"),
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        "/disc/interlaced.vob",
        "-vf",
        "yadif=mode=send_frame:parity=auto:deint=all",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "/out/progressive.mp4",
    ]


def test_denoise_and_artifact_cleanup_commands_use_distinct_filters() -> None:
    provider = LocalFfmpegProvider()

    denoise = provider.build_denoise_command(Path("/in.vob"), Path("/denoise.mp4"))
    cleanup = provider.build_artifact_cleanup_command(
        Path("/in.vob"),
        Path("/cleanup.mp4"),
    )

    assert denoise[denoise.index("-vf") + 1] == "hqdn3d=1.5:1.5:6:6"
    assert cleanup[cleanup.index("-vf") + 1] == (
        "hqdn3d=1.2:1.2:4:4,deblock=filter=strong"
    )


def test_preview_render_command_builds_short_scaled_clip() -> None:
    command = LocalFfmpegProvider().build_preview_command(
        Path("/disc/clip.vob"),
        Path("/out/preview.mp4"),
        start_seconds=12.5,
        duration_seconds=3.0,
        width=640,
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        "12.5",
        "-t",
        "3.0",
        "-i",
        "/disc/clip.vob",
        "-vf",
        "scale=640:-2",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "/out/preview.mp4",
    ]


def test_local_ffmpeg_estimates_are_free_local_and_unknown_speed() -> None:
    estimate = LocalFfmpegProvider().estimate(ProviderCapability.DENOISE)

    assert estimate.to_dict() == {
        "capability": "denoise",
        "cost": "free",
        "execution": "local",
        "speed": "unknown",
        "notes": ["FFmpeg command generation only; runtime depends on input and host CPU."],
    }
    with pytest.raises(ValueError, match="upscale"):
        LocalFfmpegProvider().estimate(ProviderCapability.UPSCALE)


def test_local_ffmpeg_health_is_available_when_ffmpeg_runs() -> None:
    runner = FakeCommandRunner()

    health = LocalFfmpegProvider(runner=runner).health_check()

    assert runner.commands == [["ffmpeg", "-version"]]
    assert health.status is ProviderHealthStatus.AVAILABLE
    assert health.details == {"version": "ffmpeg version 6.1"}


def test_local_ffmpeg_health_is_unavailable_when_binary_is_missing() -> None:
    health = LocalFfmpegProvider(runner=MissingCommandRunner()).health_check()

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert "ffmpeg is not installed" in health.message


def test_local_ffmpeg_health_is_unavailable_when_check_times_out() -> None:
    health = LocalFfmpegProvider(runner=TimeoutCommandRunner()).health_check()

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert "timed out" in health.message
