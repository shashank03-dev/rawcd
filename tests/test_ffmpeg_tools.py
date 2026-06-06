import json
from pathlib import Path

from rawcd.ffmpeg_tools import (
    build_mp4_command,
    is_protected_media_error,
    parse_ffprobe_json,
)
from rawcd.repair import FrameIssueKind, parse_freezedetect_output


def test_parse_ffprobe_json_extracts_duration_and_primary_streams() -> None:
    payload = {
        "format": {"duration": "72.125"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 576, "r_frame_rate": "25/1"},
            {"index": 1, "codec_type": "audio", "codec_name": "mp2", "channels": 2},
        ],
    }

    probe = parse_ffprobe_json(json.dumps(payload))

    assert probe.duration_seconds == 72.125
    assert probe.primary_video.codec_name == "mpeg2video"
    assert probe.primary_video.width == 720
    assert probe.primary_video.height == 576
    assert probe.primary_video.frame_rate == "25/1"
    assert probe.primary_audio is not None
    assert probe.primary_audio.codec_name == "mp2"


def test_build_mp4_command_preserves_main_video_and_optional_audio() -> None:
    command = build_mp4_command(Path("/disc/clip.dat"), Path("/out/clip.mp4"))

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


def test_detects_protected_media_errors_from_tool_output() -> None:
    assert is_protected_media_error("libdvdread: Encrypted DVD support unavailable")
    assert is_protected_media_error("CSS authentication failed")
    assert not is_protected_media_error("Invalid data found when processing input")


def test_parse_freezedetect_output_returns_damaged_time_ranges() -> None:
    stderr = """
    [freezedetect @ 0x123] freeze_start: 10.48
    [freezedetect @ 0x123] freeze_duration: 1.12
    [freezedetect @ 0x123] freeze_end: 11.60
    [freezedetect @ 0x123] freeze_start: 20
    [freezedetect @ 0x123] freeze_duration: 0.24
    [freezedetect @ 0x123] freeze_end: 20.24
    """

    issues = parse_freezedetect_output(stderr, minimum_duration=0.5)

    assert len(issues) == 1
    assert issues[0].kind is FrameIssueKind.FROZEN_RANGE
    assert issues[0].start_seconds == 10.48
    assert issues[0].end_seconds == 11.60
    assert issues[0].duration_seconds == 1.12
