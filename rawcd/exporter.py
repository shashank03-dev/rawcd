from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rawcd.models import ExportProfile, RestoreMode


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
        implemented=True,
    ),
    ExportProfile.DNXHR_HQX: ExportProfileSpec(
        profile=ExportProfile.DNXHR_HQX,
        label="DNxHR HQX",
        extension=".mov",
        implemented=True,
    ),
    ExportProfile.FFV1_MKV: ExportProfileSpec(
        profile=ExportProfile.FFV1_MKV,
        label="FFV1 Matroska",
        extension=".mkv",
        implemented=True,
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
    restore_mode: RestoreMode = RestoreMode.FAITHFUL,
) -> list[str]:
    profile = ExportProfile(profile)
    if profile is ExportProfile.HOME_MP4:
        return build_home_mp4_command(input_path, output_path, restore_mode=restore_mode)
    if profile is ExportProfile.PRORES_422_HQ:
        return _build_prores_422_hq_command(input_path, output_path)
    if profile is ExportProfile.DNXHR_HQX:
        return _build_dnxhr_hqx_command(input_path, output_path)
    if profile is ExportProfile.FFV1_MKV:
        return _build_ffv1_mkv_command(input_path, output_path)

    spec = get_export_profile_spec(profile)
    raise NotImplementedError(
        f"{spec.label} command generation is planned for the Pro export phase."
    )


def build_home_mp4_command(
    input_path: Path,
    output_path: Path,
    restore_mode: RestoreMode = RestoreMode.FAITHFUL,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
    ]
    if RestoreMode(restore_mode) is RestoreMode.ENHANCED:
        command.extend(["-vf", "yadif,hqdn3d"])
    command.extend(
        [
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
    )
    return command


def build_wav_audio_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-vn",
        "-map_metadata",
        "0",
        "-c:a",
        "pcm_s24le",
        str(output_path),
    ]


def build_preview_image_command(
    input_path: Path,
    output_path: Path,
    timestamp_seconds: float = 0.0,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        f"{max(0.0, timestamp_seconds):.3f}",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output_path),
    ]


def _archival_input_command(input_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
    ]


def _build_prores_422_hq_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        *_archival_input_command(input_path),
        "-c:v",
        "prores_ks",
        "-profile:v",
        "3",
        "-pix_fmt",
        "yuv422p10le",
        "-c:a",
        "pcm_s24le",
        str(output_path),
    ]


def _build_dnxhr_hqx_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        *_archival_input_command(input_path),
        "-c:v",
        "dnxhd",
        "-profile:v",
        "dnxhr_hqx",
        "-pix_fmt",
        "yuv422p10le",
        "-c:a",
        "pcm_s24le",
        str(output_path),
    ]


def _build_ffv1_mkv_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        *_archival_input_command(input_path),
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
        "-slicecrc",
        "1",
        "-c:a",
        "flac",
        str(output_path),
    ]


__all__ = [
    "EXPORT_PROFILE_SPECS",
    "ExportProfileSpec",
    "build_export_command",
    "build_home_mp4_command",
    "build_preview_image_command",
    "build_wav_audio_command",
    "get_export_profile_spec",
    "output_extension",
]
