from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoStream:
    index: int
    codec_name: str
    width: int | None
    height: int | None
    frame_rate: str | None


@dataclass(frozen=True)
class AudioStream:
    index: int
    codec_name: str
    channels: int | None


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float | None
    primary_video: VideoStream
    primary_audio: AudioStream | None


def parse_ffprobe_json(payload: str) -> MediaProbe:
    data = json.loads(payload)
    streams = data.get("streams", [])
    video_stream = next(
        stream for stream in streams if stream.get("codec_type") == "video"
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )

    duration = data.get("format", {}).get("duration")
    return MediaProbe(
        duration_seconds=float(duration) if duration is not None else None,
        primary_video=VideoStream(
            index=int(video_stream["index"]),
            codec_name=str(video_stream.get("codec_name", "unknown")),
            width=video_stream.get("width"),
            height=video_stream.get("height"),
            frame_rate=video_stream.get("r_frame_rate"),
        ),
        primary_audio=(
            AudioStream(
                index=int(audio_stream["index"]),
                codec_name=str(audio_stream.get("codec_name", "unknown")),
                channels=audio_stream.get("channels"),
            )
            if audio_stream is not None
            else None
        ),
    )


def build_mp4_command(input_path: Path, output_path: Path) -> list[str]:
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


def build_freezedetect_command(input_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(input_path),
        "-vf",
        "freezedetect=n=-60dB:d=0.5",
        "-f",
        "null",
        "-",
    ]


def is_protected_media_error(stderr: str) -> bool:
    lowered = stderr.lower()
    markers = [
        "encrypted dvd support unavailable",
        "css authentication failed",
        "copy protection",
        "encrypted",
    ]
    return any(marker in lowered for marker in markers)
