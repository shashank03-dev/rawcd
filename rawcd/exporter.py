from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rawcd.models import ExportProfile


@dataclass(frozen=True)
class ExportProfileSpec:
    profile: ExportProfile
    label: str
    extension: str
    implemented: bool


EXPORT_PROFILE_SPECS: dict[ExportProfile, ExportProfileSpec] = {
    ExportProfile.HOME_MP4: ExportProfileSpec(
        profile=ExportProfile.HOME_MP4,
        label="Home MP4",
        extension=".mp4",
        implemented=True,
    ),
    ExportProfile.PRORES_422_HQ: ExportProfileSpec(
        profile=ExportProfile.PRORES_422_HQ,
        label="ProRes 422 HQ",
        extension=".mov",
        implemented=False,
    ),
    ExportProfile.DNXHR_HQX: ExportProfileSpec(
        profile=ExportProfile.DNXHR_HQX,
        label="DNxHR HQX",
        extension=".mov",
        implemented=False,
    ),
    ExportProfile.FFV1_MKV: ExportProfileSpec(
        profile=ExportProfile.FFV1_MKV,
        label="FFV1 Matroska",
        extension=".mkv",
        implemented=False,
    ),
}


def get_export_profile_spec(profile: ExportProfile) -> ExportProfileSpec:
    return EXPORT_PROFILE_SPECS[profile]


def output_extension(profile: ExportProfile) -> str:
    return get_export_profile_spec(profile).extension


def build_export_command(
    input_path: Path,
    output_path: Path,
    profile: ExportProfile,
) -> list[str]:
    if profile is ExportProfile.HOME_MP4:
        return build_home_mp4_command(input_path, output_path)

    spec = get_export_profile_spec(profile)
    raise NotImplementedError(
        f"{spec.label} command generation is planned for the Pro export phase."
    )


def build_home_mp4_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


__all__ = [
    "EXPORT_PROFILE_SPECS",
    "ExportProfileSpec",
    "build_export_command",
    "build_home_mp4_command",
    "get_export_profile_spec",
    "output_extension",
]
