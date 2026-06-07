from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Callable, Protocol

from rawcd.exporter import build_export_command, output_extension
from rawcd.ffmpeg_tools import (
    build_freezedetect_command,
    is_protected_media_error,
)
from rawcd.jobs import ConversionRequest
from rawcd.models import ExportProfile
from rawcd.repair import FrameIssue, parse_freezedetect_output


class ProtectedMediaError(RuntimeError):
    pass


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class FrameRepairer(Protocol):
    def repair(
        self,
        video_path: Path,
        issues: list[FrameIssue],
        cancel_requested: Callable[[], bool],
    ) -> dict:
        ...


class SubprocessRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603


class MediaConverter:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        frame_repairer: FrameRepairer | None = None,
    ) -> None:
        self._runner = runner or SubprocessRunner()
        self._frame_repairer = frame_repairer

    def convert(
        self,
        request: ConversionRequest,
        cancel_requested: Callable[[], bool],
    ) -> dict:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []
        warnings: list[str] = []
        repair_report = {
            "mode": "smart",
            "ai_enabled": request.ai_repair,
            "damaged_ranges": 0,
            "frames_regenerated": 0,
        }

        for source_path in request.source_paths:
            if cancel_requested():
                raise RuntimeError("conversion canceled")

            export_profile = ExportProfile.HOME_MP4
            output_path = self._unique_output_path(
                source_path,
                request.output_dir,
                outputs,
                output_extension(export_profile),
            )
            result = self._runner.run(
                build_export_command(source_path, output_path, export_profile)
            )
            if result.returncode != 0:
                self._raise_for_failure(result.stderr)

            outputs.append(output_path)

            repair_result = self._runner.run(build_freezedetect_command(output_path))
            if repair_result.returncode == 0:
                issues = parse_freezedetect_output(repair_result.stderr)
                repair_report["damaged_ranges"] += len(issues)
                if issues and not request.ai_repair:
                    warnings.append(
                        f"{output_path.name} contains {len(issues)} frozen range(s); "
                        "enable AI repair to regenerate them."
                    )
                elif issues and self._frame_repairer is None:
                    warnings.append(
                        "AI repair was requested, but no RIFE repair adapter is configured."
                    )
                elif issues and self._frame_repairer is not None:
                    repair_result_payload = self._frame_repairer.repair(
                        output_path, issues, cancel_requested
                    )
                    repair_report["frames_regenerated"] += int(
                        repair_result_payload.get("frames_regenerated", 0)
                    )
                    if "tool" in repair_result_payload:
                        repair_report["tool"] = repair_result_payload["tool"]

        return {
            "outputs": outputs,
            "warnings": warnings,
            "report": {
                "clips": len(outputs),
                "repair": repair_report,
            },
        }

    def _raise_for_failure(self, stderr: str) -> None:
        if is_protected_media_error(stderr):
            raise ProtectedMediaError(
                "This disc appears to be protected or encrypted. RawCD v1 only "
                "supports personal, unprotected media."
            )
        raise RuntimeError(stderr.strip() or "ffmpeg failed")

    def _unique_output_path(
        self,
        source_path: Path,
        output_dir: Path,
        existing_outputs: list[Path],
        extension: str = ".mp4",
    ) -> Path:
        base = self._safe_stem(source_path.stem) or "clip"
        candidate = output_dir / f"{base}{extension}"
        index = 2
        while candidate in existing_outputs or candidate.exists():
            candidate = output_dir / f"{base}-{index}{extension}"
            index += 1
        return candidate

    def _safe_stem(self, stem: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
