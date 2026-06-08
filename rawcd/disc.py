from __future__ import annotations

from pathlib import Path
import subprocess  # nosec B404
from typing import Protocol

from rawcd.ffmpeg_tools import is_protected_media_error
from rawcd.parser import (
    DiscInspection,
    DiscParser,
    DiscType,
    PlayableSource,
    SourceKind,
)


class ProtectionProbeRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessProtectionProbeRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603


class DiscClassifier:
    VIDEO_EXTENSIONS = DiscParser.VIDEO_EXTENSIONS

    def __init__(
        self,
        parser: DiscParser | None = None,
        probe_runner: ProtectionProbeRunner | None = None,
    ) -> None:
        self._parser = parser or DiscParser()
        self._probe_runner = probe_runner or SubprocessProtectionProbeRunner()

    def classify(self, root: Path) -> DiscInspection:
        result = self._parser.parse(root)
        if result.disc_type is DiscType.DVD_VIDEO and result.playable_sources:
            stderr = self._probe_source(result.playable_sources[0].path)
            if is_protected_media_error(stderr):
                return self._parser.parse_tool_output(root, stderr)
        return result

    def _probe_source(self, source_path: Path) -> str:
        command = [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(source_path),
        ]
        try:
            result = self._probe_runner.run(command)
        except FileNotFoundError:
            return ""
        return result.stderr


__all__ = [
    "DiscClassifier",
    "DiscInspection",
    "DiscParser",
    "DiscType",
    "PlayableSource",
    "ProtectionProbeRunner",
    "SourceKind",
]
