from pathlib import Path

from rawcd.exporter import (
    build_export_command,
    build_wav_audio_command,
    get_export_profile_spec,
    output_extension,
)
from rawcd.models import ExportProfile, RestoreMode


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
    assert get_export_profile_spec(ExportProfile.PRORES_422_HQ).implemented is True
    assert get_export_profile_spec(ExportProfile.DNXHR_HQX).implemented is True
    assert get_export_profile_spec(ExportProfile.FFV1_MKV).implemented is True


def test_enhanced_home_export_adds_repair_filters() -> None:
    command = build_export_command(
        Path("/disc/clip.dat"),
        Path("/out/clip.mp4"),
        ExportProfile.HOME_MP4,
        restore_mode=RestoreMode.ENHANCED,
    )

    assert command[command.index("-vf") + 1] == "yadif,hqdn3d"


def test_prores_422_hq_export_command_preserves_metadata() -> None:
    command = build_export_command(
        Path("/disc/clip.vob"),
        Path("/out/clip.mov"),
        ExportProfile.PRORES_422_HQ,
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        "/disc/clip.vob",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c:v",
        "prores_ks",
        "-profile:v",
        "3",
        "-pix_fmt",
        "yuv422p10le",
        "-c:a",
        "pcm_s24le",
        "/out/clip.mov",
    ]


def test_dnxhr_hqx_export_command_preserves_metadata() -> None:
    command = build_export_command(
        Path("/disc/clip.vob"),
        Path("/out/clip.mov"),
        ExportProfile.DNXHR_HQX,
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        "/disc/clip.vob",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c:v",
        "dnxhd",
        "-profile:v",
        "dnxhr_hqx",
        "-pix_fmt",
        "yuv422p10le",
        "-c:a",
        "pcm_s24le",
        "/out/clip.mov",
    ]


def test_ffv1_mkv_export_command_preserves_metadata() -> None:
    command = build_export_command(
        Path("/disc/clip.vob"),
        Path("/out/clip.mkv"),
        ExportProfile.FFV1_MKV,
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        "/disc/clip.vob",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
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
        "/out/clip.mkv",
    ]


def test_wav_audio_extraction_command_preserves_audio_metadata() -> None:
    command = build_wav_audio_command(
        Path("/disc/clip.vob"),
        Path("/out/clip.wav"),
    )

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        "/disc/clip.vob",
        "-map",
        "0:a:0",
        "-vn",
        "-map_metadata",
        "0",
        "-c:a",
        "pcm_s24le",
        "/out/clip.wav",
    ]
