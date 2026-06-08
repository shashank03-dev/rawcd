from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path
from typing import Protocol

from rawcd.models import ProviderCapability
from rawcd.models import ProviderKind
from rawcd.providers.base import ProviderEstimate
from rawcd.providers.base import ProviderHealth
from rawcd.providers.base import ProviderInfo


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessCommandRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # nosec B603
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )


class LocalFfmpegProvider:
    id = "local-ffmpeg"
    label = "Local FFmpeg"
    kind = ProviderKind.OPEN_LOCAL
    capabilities = (
        ProviderCapability.DEINTERLACE,
        ProviderCapability.DENOISE,
        ProviderCapability.ARTIFACT_CLEANUP,
        ProviderCapability.PREVIEW_RENDER,
    )

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        runner: CommandRunner | None = None,
    ) -> None:
        self._ffmpeg_binary = ffmpeg_binary
        self._runner = runner or SubprocessCommandRunner()

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        command = [self._ffmpeg_binary, "-version"]
        try:
            result = self._runner.run(command)
        except FileNotFoundError:
            return ProviderHealth.unavailable(
                "ffmpeg is not installed or is not on PATH.",
            )
        except subprocess.TimeoutExpired:
            return ProviderHealth.unavailable("ffmpeg health check timed out.")

        first_line = (result.stdout or result.stderr).splitlines()
        version = first_line[0] if first_line else ""
        if result.returncode == 0:
            details = {"version": version} if version else {}
            return ProviderHealth.available("ffmpeg is available.", details=details)

        return ProviderHealth.unavailable(
            "ffmpeg health check failed.",
            details={"returncode": str(result.returncode), "version": version},
        )

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        capability = ProviderCapability(capability)
        if capability not in self.capabilities:
            raise ValueError(f"{capability.value} is not supported by {self.id}")
        return ProviderEstimate(
            capability=capability,
            cost="free",
            execution="local",
            speed="unknown",
            notes=(
                "FFmpeg command generation only; runtime depends on input and host CPU.",
            ),
        )

    def build_deinterlace_command(
        self,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        return self._build_filter_command(
            input_path,
            output_path,
            "yadif=mode=send_frame:parity=auto:deint=all",
        )

    def build_denoise_command(
        self,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        return self._build_filter_command(
            input_path,
            output_path,
            "hqdn3d=1.5:1.5:6:6",
        )

    def build_artifact_cleanup_command(
        self,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        return self._build_filter_command(
            input_path,
            output_path,
            "hqdn3d=1.2:1.2:4:4,deblock=filter=strong",
        )

    def build_preview_command(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float = 0.0,
        duration_seconds: float = 5.0,
        width: int = 640,
    ) -> list[str]:
        if start_seconds < 0:
            raise ValueError("start_seconds must be greater than or equal to zero")
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")
        if width <= 0:
            raise ValueError("width must be greater than zero")

        return [
            self._ffmpeg_binary,
            "-hide_banner",
            "-y",
            "-ss",
            str(start_seconds),
            "-t",
            str(duration_seconds),
            "-i",
            str(input_path),
            "-vf",
            f"scale={width}:-2",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            str(output_path),
        ]

    def _build_filter_command(
        self,
        input_path: Path,
        output_path: Path,
        video_filter: str,
    ) -> list[str]:
        return [
            self._ffmpeg_binary,
            "-hide_banner",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "copy",
            str(output_path),
        ]


__all__ = [
    "CommandRunner",
    "LocalFfmpegProvider",
    "SubprocessCommandRunner",
]
