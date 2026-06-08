from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path
from typing import Callable
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


TOPAZ_CLI_CAPABILITIES = (
    ProviderCapability.INTERPOLATION,
    ProviderCapability.UPSCALE,
    ProviderCapability.STABILIZATION,
    ProviderCapability.ARTIFACT_CLEANUP,
    ProviderCapability.DENOISE,
    ProviderCapability.DEINTERLACE,
)

DEFAULT_TOPAZ_CLI_PATHS = (
    Path("/usr/local/bin/topaz-video-ai"),
    Path("/usr/bin/topaz-video-ai"),
    Path("/opt/Topaz Video AI/topaz-video-ai"),
    Path("/Applications/Topaz Video AI.app/Contents/MacOS/topaz-video-ai"),
)

_CAPABILITY_FLAGS = {
    ProviderCapability.INTERPOLATION: "--interpolate",
    ProviderCapability.UPSCALE: "--upscale",
    ProviderCapability.STABILIZATION: "--stabilize",
    ProviderCapability.ARTIFACT_CLEANUP: "--artifact-cleanup",
    ProviderCapability.DENOISE: "--denoise",
    ProviderCapability.DEINTERLACE: "--deinterlace",
}


class TopazCliProvider:
    id = "topaz-cli"
    label = "Topaz Video AI CLI"
    kind = ProviderKind.TOPAZ

    def __init__(
        self,
        cli_path: Path | None = None,
        known_paths: tuple[Path, ...] = DEFAULT_TOPAZ_CLI_PATHS,
        exists: Callable[[Path], bool] | None = None,
        runner: CommandRunner | None = None,
        supported_capabilities: tuple[ProviderCapability, ...] | None = None,
    ) -> None:
        self._configured_cli_path = cli_path
        self._known_paths = known_paths
        self._exists = exists or Path.exists
        self._runner = runner or SubprocessCommandRunner()
        self._supported_capabilities = supported_capabilities

    @property
    def capabilities(self) -> tuple[ProviderCapability, ...]:
        if self.detect_cli_path() is None:
            return ()
        if self._supported_capabilities is not None:
            return tuple(ProviderCapability(cap) for cap in self._supported_capabilities)
        return TOPAZ_CLI_CAPABILITIES

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def detect_cli_path(self) -> Path | None:
        if self._configured_cli_path is not None and self._exists(
            self._configured_cli_path
        ):
            return self._configured_cli_path

        for path in self._known_paths:
            if self._exists(path):
                return path
        return None

    def health_check(self) -> ProviderHealth:
        cli_path = self.detect_cli_path()
        if cli_path is None:
            return ProviderHealth.license_required(
                "Topaz Video AI CLI is not installed or configured.",
            )

        try:
            result = self._runner.run([str(cli_path), "--version"])
        except FileNotFoundError:
            return ProviderHealth.license_required(
                "Topaz Video AI CLI is not installed or configured.",
                details={"cli_path": str(cli_path)},
            )
        except subprocess.TimeoutExpired:
            return ProviderHealth.unavailable(
                "Topaz CLI health check timed out.",
                details={"cli_path": str(cli_path)},
            )

        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        lowered = output.lower()
        if _looks_like_auth_failure(lowered):
            return ProviderHealth.license_required(
                "Topaz CLI requires license activation. Please authenticate before use.",
                details={"cli_path": str(cli_path)},
            )

        if result.returncode != 0:
            return ProviderHealth.unavailable(
                "Topaz CLI health check failed.",
                details={
                    "cli_path": str(cli_path),
                    "returncode": str(result.returncode),
                },
            )

        first_line = output.splitlines()[0] if output.splitlines() else ""
        details = {"cli_path": str(cli_path)}
        if first_line:
            details["version"] = first_line
        return ProviderHealth.available(
            "Topaz CLI is available.",
            details=details,
        )

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        capability = ProviderCapability(capability)
        if capability not in self.capabilities:
            raise ValueError(f"{capability.value} is not supported by {self.id}")
        return ProviderEstimate(
            capability=capability,
            cost="paid",
            execution="local",
            speed="unknown",
            notes=("Requires user-installed Topaz Video AI and a valid license.",),
        )

    def build_enhancement_command(
        self,
        capability: ProviderCapability,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        capability = ProviderCapability(capability)
        cli_path = self.detect_cli_path()
        if cli_path is None:
            raise ValueError("Topaz CLI path is not configured or installed")
        if capability not in self.capabilities:
            raise ValueError(f"{capability.value} is not supported by {self.id}")

        return [
            str(cli_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            _CAPABILITY_FLAGS[capability],
        ]


class TopazApiProvider:
    id = "topaz-api"
    label = "Topaz API"
    kind = ProviderKind.TOPAZ
    capabilities = TOPAZ_CLI_CAPABILITIES

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth.license_required(
                "Topaz API key is not configured.",
            )
        return ProviderHealth.available("Topaz API credentials are configured.")

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        capability = ProviderCapability(capability)
        if capability not in self.capabilities:
            raise ValueError(f"{capability.value} is not supported by {self.id}")
        return ProviderEstimate(
            capability=capability,
            cost="paid",
            execution="cloud_api",
            speed="unknown",
            notes=("Requires user-provided Topaz API credentials.",),
        )


def _looks_like_auth_failure(output: str) -> bool:
    markers = (
        "not authenticated",
        "not authorized",
        "license required",
        "license activation",
        "please sign in",
        "login required",
    )
    return any(marker in output for marker in markers)


__all__ = [
    "DEFAULT_TOPAZ_CLI_PATHS",
    "TOPAZ_CLI_CAPABILITIES",
    "CommandRunner",
    "SubprocessCommandRunner",
    "TopazApiProvider",
    "TopazCliProvider",
]
