from __future__ import annotations

import hashlib
import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Protocol

from rawcd.models import (
    RecoveryAttempt,
    RecoveryMode,
    RecoveryResult,
    RecoverySeverity,
)


class RescueToolRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessRescueToolRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603


class DdrescueAdapter:
    tool_name = "ddrescue"

    def __init__(self, runner: RescueToolRunner | None = None) -> None:
        self._runner = runner or SubprocessRescueToolRunner()

    def build_command(
        self,
        input_path: Path,
        image_path: Path,
        map_path: Path,
        retry_count: int,
    ) -> list[str]:
        if retry_count < 0:
            raise ValueError("retry_count must be greater than or equal to zero")
        return [
            self.tool_name,
            "--force",
            f"--retry-passes={retry_count}",
            str(input_path),
            str(image_path),
            str(map_path),
        ]

    def run(
        self,
        input_path: Path,
        image_path: Path,
        map_path: Path,
        retry_count: int,
    ) -> tuple[RecoveryAttempt, bool]:
        command = self.build_command(input_path, image_path, map_path, retry_count)
        try:
            result = self._runner.run(command)
        except FileNotFoundError as exc:
            return (
                RecoveryAttempt(
                    tool=self.tool_name,
                    command=tuple(command),
                    retry_count=retry_count,
                    image_path=image_path,
                    map_path=map_path,
                    error=str(exc),
                    warnings=(
                        "ddrescue is not installed; using the direct source instead of a recovered image.",
                    ),
                ),
                False,
            )

        return (
            RecoveryAttempt(
                tool=self.tool_name,
                command=tuple(command),
                retry_count=retry_count,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                image_path=image_path,
                map_path=map_path,
            ),
            result.returncode == 0,
        )


class RecoveryPlanner:
    def __init__(
        self,
        rescue_adapter: DdrescueAdapter | None = None,
        retry_count: int = 3,
    ) -> None:
        if retry_count < 0:
            raise ValueError("retry_count must be greater than or equal to zero")
        self._rescue_adapter = rescue_adapter
        self._retry_count = retry_count

    def plan(
        self,
        input_path: Path,
        output_dir: Path,
        mode: RecoveryMode,
    ) -> RecoveryResult:
        recovery_mode = RecoveryMode(mode)
        if recovery_mode == RecoveryMode.QUICK:
            return RecoveryResult(
                input_path=input_path,
                mode=recovery_mode,
                source_path=input_path,
            )

        work_dir = output_dir / ".rawcd-work" / stable_work_name(input_path)
        work_dir.mkdir(parents=True, exist_ok=True)
        image_path = work_dir / "source.img"
        map_path = work_dir / "source.map"

        if self._rescue_adapter is None:
            return RecoveryResult(
                input_path=input_path,
                mode=recovery_mode,
                source_path=input_path,
                work_dir=work_dir,
                image_path=image_path,
                map_path=map_path,
                retry_count=self._retry_count,
                warnings=(
                    "Maximum recovery requested, but no rescue adapter is configured; using the direct source.",
                ),
                severity=RecoverySeverity.WARNING,
            )

        attempt, recovered = self._rescue_adapter.run(
            input_path,
            image_path,
            map_path,
            self._retry_count,
        )
        warnings = attempt.warnings
        if recovered:
            source_path = image_path
            severity = RecoverySeverity.INFO
        else:
            source_path = input_path
            severity = (
                RecoverySeverity.WARNING
                if attempt.returncode is None
                else RecoverySeverity.ERROR
            )
            if not warnings:
                warnings = (
                    "Maximum recovery failed; using the direct source instead of a recovered image.",
                )

        return RecoveryResult(
            input_path=input_path,
            mode=recovery_mode,
            source_path=source_path,
            work_dir=work_dir,
            image_path=image_path,
            map_path=map_path,
            retry_count=self._retry_count,
            attempts=(attempt,),
            warnings=warnings,
            severity=severity,
        )


def stable_work_name(input_path: Path) -> str:
    raw = input_path.name or str(input_path)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    digest = hashlib.sha256(str(input_path).encode("utf-8")).hexdigest()[:12]
    return f"{slug or 'source'}-{digest}"


__all__ = [
    "DdrescueAdapter",
    "RecoveryPlanner",
    "RescueToolRunner",
    "SubprocessRescueToolRunner",
    "stable_work_name",
]
