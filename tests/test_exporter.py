from pathlib import Path

import pytest

from rawcd.exporter import (
    build_export_command,
    get_export_profile_spec,
    output_extension,
)
from rawcd.models import ExportProfile


def test_home_mp4_export_command_preserves_current_h264_aac_behavior() -> None:
    command = build_export_command(
        Path("/disc/clip.dat"),
        Path("/out/clip.mp4"),
        ExportProfile.HOME_MP4,
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        "/disc/clip.dat",
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
        "/out/clip.mp4",
    ]


def test_export_profiles_are_registered_with_output_extensions() -> None:
    assert output_extension(ExportProfile.HOME_MP4) == ".mp4"
    assert output_extension(ExportProfile.PRORES_422_HQ) == ".mov"
    assert output_extension(ExportProfile.DNXHR_HQX) == ".mov"
    assert output_extension(ExportProfile.FFV1_MKV) == ".mkv"

    assert get_export_profile_spec(ExportProfile.HOME_MP4).implemented is True
    assert get_export_profile_spec(ExportProfile.PRORES_422_HQ).profile is (
        ExportProfile.PRORES_422_HQ
    )


def test_pro_export_commands_are_reserved_for_later_phase() -> None:
    with pytest.raises(NotImplementedError, match="ProRes 422 HQ"):
        build_export_command(
            Path("/disc/clip.vob"),
            Path("/out/clip.mov"),
            ExportProfile.PRORES_422_HQ,
        )
