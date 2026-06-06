from __future__ import annotations

import os
import subprocess  # nosec B404
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from zipfile import ZipFile


RIFE_VERSION = "20221029"
RIFE_LINUX_PACKAGE = f"rife-ncnn-vulkan-{RIFE_VERSION}-ubuntu"
RIFE_LINUX_URL = (
    "https://github.com/nihui/rife-ncnn-vulkan/releases/download/"
    f"{RIFE_VERSION}/{RIFE_LINUX_PACKAGE}.zip"
)


class Downloader(Protocol):
    def download(self, url: str, destination: Path) -> None:
        ...


class UrlLibDownloader:
    def download(self, url: str, destination: Path) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "github.com":
            raise ValueError("Only GitHub HTTPS release URLs are allowed.")
        urllib.request.urlretrieve(url, destination)  # nosec B310


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603


@dataclass
class RifeInstaller:
    install_dir: Path
    downloader: Downloader | None = None
    url: str = RIFE_LINUX_URL
    package_name: str = RIFE_LINUX_PACKAGE

    def ensure_installed(self) -> Path:
        binary = self.install_dir / self.package_name / "rife-ncnn-vulkan"
        if binary.exists():
            self._make_executable(binary)
            return binary

        self.install_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.install_dir / f"{self.package_name}.zip"
        (self.downloader or UrlLibDownloader()).download(self.url, archive_path)
        with ZipFile(archive_path) as archive:
            archive.extractall(self.install_dir)
        archive_path.unlink(missing_ok=True)

        if not binary.exists():
            raise RuntimeError(f"RIFE binary was not found after extraction: {binary}")
        self._make_executable(binary)
        return binary

    def _make_executable(self, binary: Path) -> None:
        binary.chmod(binary.stat().st_mode | 0o755)


@dataclass(frozen=True)
class RifeFrameInterpolator:
    binary_path: Path
    runner: CommandRunner | None = None

    def build_command(
        self,
        previous_frame: Path,
        next_frame: Path,
        output_frame: Path,
    ) -> list[str]:
        return [
            os.fspath(self.binary_path),
            "-0",
            os.fspath(previous_frame),
            "-1",
            os.fspath(next_frame),
            "-o",
            os.fspath(output_frame),
        ]

    def interpolate(
        self,
        previous_frame: Path,
        next_frame: Path,
        output_frame: Path,
    ) -> None:
        runner = self.runner or SubprocessRunner()
        result = runner.run(
            self.build_command(
                previous_frame=previous_frame,
                next_frame=next_frame,
                output_frame=output_frame,
            )
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "rife-ncnn-vulkan failed")
