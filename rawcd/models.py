from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from math import isfinite
from pathlib import Path


class RestoreLane(str, Enum):
    HOME = "home"
    PRO = "pro"


class RestoreMode(str, Enum):
    FAITHFUL = "faithful"
    ENHANCED = "enhanced"


class RecoveryMode(str, Enum):
    QUICK = "quick"
    MAXIMUM = "maximum"


class SourceState(str, Enum):
    MOUNTED = "mounted"
    RECOVERED_IMAGE = "recovered_image"
    DIRECT_FILE = "direct_file"
    UNAVAILABLE = "unavailable"


class FrameState(str, Enum):
    ORIGINAL = "original"
    DAMAGED = "damaged"
    MISSING = "missing"
    INTERPOLATED = "interpolated"
    GENERATED = "generated"
    ENHANCED = "enhanced"
    SKIPPED = "skipped"


class ProviderKind(str, Enum):
    OPEN_LOCAL = "open_local"
    MANAGED_LOCAL = "managed_local"
    OLLAMA = "ollama"
    TOPAZ = "topaz"
    CLOUD = "cloud"


class ProviderCapability(str, Enum):
    INTERPOLATION = "interpolation"
    INPAINTING = "inpainting"
    DENOISE = "denoise"
    DEINTERLACE = "deinterlace"
    UPSCALE = "upscale"
    STABILIZATION = "stabilization"
    COLOR_CORRECTION = "color_correction"
    ARTIFACT_CLEANUP = "artifact_cleanup"
    PREVIEW_RENDER = "preview_render"


class ExportProfile(str, Enum):
    HOME_MP4 = "home_mp4"
    PRORES_422_HQ = "prores_422_hq"
    DNXHR_HQX = "dnxhr_hqx"
    FFV1_MKV = "ffv1_mkv"


@dataclass(frozen=True)
class RestoreSource:
    path: Path
    state: SourceState
    label: str | None = None
    recovery_mode: RecoveryMode = RecoveryMode.QUICK


@dataclass(frozen=True)
class FrameRange:
    start_seconds: float
    end_seconds: float
    state: FrameState
    reason: str = ""

    def __post_init__(self) -> None:
        if not isfinite(self.start_seconds) or not isfinite(self.end_seconds):
            raise ValueError("frame range timestamps must be finite")
        if self.start_seconds < 0:
            raise ValueError("start_seconds must be greater than or equal to zero")
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")


@dataclass(frozen=True)
class FrameTimeline:
    ranges: tuple[FrameRange, ...] = field(default_factory=tuple)
    duration_seconds: float | None = None
    frame_rate: str | None = None


@dataclass(frozen=True)
class RestoreReport:
    lane: RestoreLane = RestoreLane.HOME
    mode: RestoreMode = RestoreMode.FAITHFUL
    recovery_mode: RecoveryMode = RecoveryMode.QUICK
    clips: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    timeline: FrameTimeline = field(default_factory=FrameTimeline)


__all__ = [
    "ExportProfile",
    "FrameRange",
    "FrameState",
    "FrameTimeline",
    "ProviderCapability",
    "ProviderKind",
    "RecoveryMode",
    "RestoreLane",
    "RestoreMode",
    "RestoreReport",
    "RestoreSource",
    "SourceState",
]
