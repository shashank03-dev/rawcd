from __future__ import annotations

import json
import subprocess  # nosec B404
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OpticalDevice:
    device_path: str
    model: str | None
    mount_path: str | None
    is_usb: bool
    has_media: bool


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603


class OpticalDriveScanner:
    COMMAND = ["lsblk", "-J", "-o", "NAME,TYPE,MODEL,TRAN,MOUNTPOINTS"]

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def scan(self) -> list[OpticalDevice]:
        result = self._runner.run(self.COMMAND)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "lsblk failed")

        payload = json.loads(result.stdout)
        devices = []
        for entry in self._walk_devices(payload.get("blockdevices", [])):
            if not self._is_optical(entry):
                continue
            mount_path = self._first_mountpoint(entry.get("mountpoints"))
            devices.append(
                OpticalDevice(
                    device_path=f"/dev/{entry['name']}",
                    model=entry.get("model"),
                    mount_path=mount_path,
                    is_usb=entry.get("tran") == "usb",
                    has_media=mount_path is not None,
                )
            )
        return devices

    def _walk_devices(self, entries: list[dict]) -> list[dict]:
        flattened: list[dict] = []
        for entry in entries:
            flattened.append(entry)
            flattened.extend(self._walk_devices(entry.get("children", [])))
        return flattened

    def _is_optical(self, entry: dict) -> bool:
        name = str(entry.get("name", ""))
        return entry.get("type") == "rom" or name.startswith("sr")

    def _first_mountpoint(self, mountpoints: object) -> str | None:
        if isinstance(mountpoints, list):
            return next((item for item in mountpoints if item), None)
        if isinstance(mountpoints, str) and mountpoints:
            return mountpoints
        return None
