from pathlib import Path
from subprocess import CompletedProcess

import pytest

from rawcd.converter import MediaConverter, ProtectedMediaError
from rawcd.jobs import ConversionRequest
from rawcd.models import ExportProfile, ProviderCapability
from rawcd.repair import FrameIssue
from rawcd.repair_pipeline import RepairProvider


class FakeRunner:
    def __init__(self, responses: list[CompletedProcess[str]]) -> None:
        self.responses = responses
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return self.responses.pop(0)


def completed(
    command: list[str],
    stdout: str = "",
    stderr: str = "",
) -> CompletedProcess[str]:
    return CompletedProcess(command, 0, stdout=stdout, stderr=stderr)


def failed(command: list[str], stderr: str) -> CompletedProcess[str]:
    return CompletedProcess(command, 1, stdout="", stderr=stderr)


def probe_payload(duration: float = 12.5, frame_rate: str = "25/1") -> str:
    return (
        '{"format":{"duration":"'
        + str(duration)
        + '"},"streams":[{"index":0,"codec_type":"video","codec_name":"mpeg2video",'
        + '"width":720,"height":576,"r_frame_rate":"'
        + frame_rate
        + '"}]}'
    )


def test_converter_writes_one_mp4_per_source_and_report(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload()),
            completed(["ffmpeg"], stderr="[freezedetect] freeze_duration: 0.0"),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/DISC/MPEGAV/AVSEQ01.DAT")],
            output_dir=tmp_path,
            ai_repair=False,
        ),
        cancel_requested=lambda: False,
    )

    assert result["outputs"] == [tmp_path / "AVSEQ01.mp4"]
    assert result["warnings"] == []
    assert result["report"]["clips"] == 1
    assert result["report"]["repair"]["mode"] == "smart"
    assert result["report"]["timeline"]["states"]["damaged"] == 0
    assert result["report"]["timeline"]["range_counts"]["damaged"] == 0
    assert result["report"]["timeline"]["frame_counts"]["damaged"] == 0
    assert result["report"]["timeline"]["seconds"]["damaged"] == 0.0
    assert result["report"]["timeline"]["ranges"] == []
    assert runner.commands[0][-1] == str(tmp_path / "AVSEQ01.mp4")
    assert runner.commands[1][:4] == ["ffprobe", "-v", "error", "-print_format"]
    assert runner.commands[2][:4] == ["ffmpeg", "-hide_banner", "-i", str(tmp_path / "AVSEQ01.mp4")]


def test_converter_uses_requested_archival_export_profile(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload()),
            completed(["ffmpeg"], stderr=""),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/DISC/VIDEO_TS/VTS_01_1.VOB")],
            output_dir=tmp_path,
            export_profile=ExportProfile.PRORES_422_HQ,
        ),
        cancel_requested=lambda: False,
    )

    assert result["outputs"] == [tmp_path / "VTS_01_1.mov"]
    assert result["report"]["export_profile"] == "prores_422_hq"
    assert "prores_ks" in runner.commands[0]
    assert runner.commands[0][-1] == str(tmp_path / "VTS_01_1.mov")


def test_converter_extracts_wav_audio_when_requested(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload()),
            completed(["ffmpeg"], stderr=""),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/DISC/VIDEO_TS/VTS_01_1.VOB")],
            output_dir=tmp_path,
            export_profile=ExportProfile.PRORES_422_HQ,
            extract_wav_audio=True,
        ),
        cancel_requested=lambda: False,
    )

    assert result["outputs"] == [
        tmp_path / "VTS_01_1.mov",
        tmp_path / "VTS_01_1.wav",
    ]
    assert result["report"]["clips"] == 1
    assert runner.commands[1][-1] == str(tmp_path / "VTS_01_1.wav")
    assert "pcm_s24le" in runner.commands[1]


def test_converter_emits_preview_image_and_frame_progress_when_callback_is_present(
    tmp_path: Path,
) -> None:
    class PreviewRunner(FakeRunner):
        def run(self, command: list[str]) -> CompletedProcess[str]:
            if command[-1].endswith(".rawcd-preview.jpg"):
                Path(command[-1]).write_bytes(b"jpeg")
            return super().run(command)

    runner = PreviewRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(duration=4.0, frame_rate="25/1")),
            completed(["ffmpeg"], stderr=""),
        ]
    )
    previews: list[tuple[int, float, str, Path | None]] = []
    converter = MediaConverter(runner=runner)

    converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/DISC/MPEGAV/AVSEQ01.DAT")],
            output_dir=tmp_path,
            preview_callback=lambda frame, timestamp, operation, image: previews.append(
                (frame, timestamp, operation, image)
            ),
        ),
        cancel_requested=lambda: False,
    )

    assert previews[1] == (
        0,
        0.0,
        "Recovering original frame",
        tmp_path / "AVSEQ01.rawcd-preview.jpg",
    )
    assert previews[2] == (
        100,
        4.0,
        "Recovering original frame",
        tmp_path / "AVSEQ01.rawcd-preview.jpg",
    )


def test_converter_rejects_protected_media_without_bypass(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            failed(["ffmpeg"], "libdvdread: Encrypted DVD support unavailable"),
        ]
    )
    converter = MediaConverter(runner=runner)

    with pytest.raises(ProtectedMediaError, match="protected or encrypted"):
        converter.convert(
            ConversionRequest(
                source_paths=[Path("/media/DISC/VIDEO_TS/VTS_01_1.VOB")],
                output_dir=tmp_path,
            ),
            cancel_requested=lambda: False,
        )


def test_converter_calls_ai_repairer_only_for_detected_damage(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(frame_rate="5/1")),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 1
                [freezedetect] freeze_duration: 0.7
                [freezedetect] freeze_end: 1.7
                """,
            ),
        ]
    )

    class Repairer:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, list[FrameIssue]]] = []

        def repair(self, video_path: Path, issues: list[FrameIssue], _cancel_requested) -> dict:
            self.calls.append((video_path, issues))
            return {"frames_regenerated": 1, "tool": "rife-ncnn-vulkan"}

    repairer = Repairer()
    converter = MediaConverter(runner=runner, frame_repairer=repairer)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/disc/bad-freeze.vob")],
            output_dir=tmp_path,
            ai_repair=True,
        ),
        cancel_requested=lambda: False,
    )

    assert repairer.calls[0][0] == tmp_path / "bad-freeze.mp4"
    assert len(repairer.calls[0][1]) == 1
    assert result["report"]["repair"]["frames_regenerated"] == 1
    assert result["report"]["repair"]["tool"] == "rife-ncnn-vulkan"
    assert result["report"]["timeline"]["states"]["interpolated"] == 1
    assert result["report"]["timeline"]["ranges"][0]["state"] == "interpolated"


def test_converter_reports_skipped_timeline_ranges_when_repair_is_unavailable(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload()),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 4
                [freezedetect] freeze_duration: 1.0
                [freezedetect] freeze_end: 5
                """,
            ),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/disc/bad-freeze.vob")],
            output_dir=tmp_path,
            ai_repair=True,
        ),
        cancel_requested=lambda: False,
    )

    assert result["report"]["timeline"]["states"]["skipped"] == 1
    assert result["report"]["timeline"]["range_counts"]["skipped"] == 1
    assert result["report"]["timeline"]["frame_counts"]["skipped"] > 0
    assert result["report"]["timeline"]["seconds"]["skipped"] == 1.0
    assert result["report"]["timeline"]["ranges"][0] == {
        "start_seconds": 4.0,
        "end_seconds": 5.0,
        "state": "skipped",
        "reason": "repair unavailable",
        "action": "skipped",
        "required_capability": "inpainting",
        "provider_id": None,
        "preview_recommended": False,
        "report_label_required": False,
    }
    assert any("skipped frame range" in warning for warning in result["warnings"])


def test_converter_normalizes_conversion_decode_warnings_with_freezedetect_damage(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            completed(
                ["ffmpeg"],
                stderr="[mpeg2video] error while decoding MB 20 14 pts_time:7.04",
            ),
            completed(["ffprobe"], stdout=probe_payload(frame_rate="25/1")),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 7.0
                [freezedetect] freeze_duration: 0.6
                [freezedetect] freeze_end: 7.6
                """,
            ),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/disc/decode-warning.vob")],
            output_dir=tmp_path,
            ai_repair=False,
        ),
        cancel_requested=lambda: False,
    )

    ranges = result["report"]["timeline"]["ranges"]
    assert ranges == [
        {
            "start_seconds": 7.0,
            "end_seconds": 7.6,
            "state": "damaged",
            "reason": "freezedetect, decode_warning",
        }
    ]
    assert result["report"]["timeline"]["frame_counts"]["damaged"] == 15


def test_converter_routes_repair_decisions_using_real_frame_count(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(frame_rate="10/1")),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 4.0
                [freezedetect] freeze_duration: 0.6
                [freezedetect] freeze_end: 4.6
                """,
            ),
        ]
    )

    class Repairer:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, list[FrameIssue]]] = []

        def repair(self, video_path: Path, issues: list[FrameIssue], _cancel_requested) -> dict:
            self.calls.append((video_path, issues))
            return {"frames_regenerated": 6, "tool": "rife"}

    repairer = Repairer()
    converter = MediaConverter(
        runner=runner,
        frame_repairer=repairer,
        repair_providers=(
            RepairProvider(
                id="rife",
                capabilities=frozenset({ProviderCapability.INTERPOLATION}),
            ),
        ),
    )

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/disc/medium-gap.vob")],
            output_dir=tmp_path,
            ai_repair=True,
        ),
        cancel_requested=lambda: False,
    )

    assert repairer.calls == []
    assert result["report"]["timeline"]["ranges"][0]["state"] == "skipped"
    assert result["report"]["timeline"]["ranges"][0]["action"] == "skipped"
    assert result["report"]["timeline"]["ranges"][0]["required_capability"] == "inpainting"
    assert any("No provider supports inpainting" in warning for warning in result["warnings"])
    assert not any("no repair adapter is configured" in warning for warning in result["warnings"])


def test_converter_falls_back_when_probe_reports_invalid_frame_rate(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(frame_rate="0/0")),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 1.0
                [freezedetect] freeze_duration: 0.6
                [freezedetect] freeze_end: 1.6
                """,
            ),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/disc/invalid-rate.vob")],
            output_dir=tmp_path,
            ai_repair=False,
        ),
        cancel_requested=lambda: False,
    )

    assert result["report"]["timeline"]["ranges"][0]["state"] == "damaged"
    assert result["report"]["timeline"]["frame_counts"]["damaged"] == 15


def test_converter_reports_timeline_per_output_and_keeps_aggregate_timeline(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(duration=10.0)),
            completed(["ffmpeg"], stderr=""),
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(duration=10.0)),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 2.0
                [freezedetect] freeze_duration: 1.0
                [freezedetect] freeze_end: 3.0
                """,
            ),
        ]
    )
    converter = MediaConverter(runner=runner)

    result = converter.convert(
        ConversionRequest(
            source_paths=[
                Path("/media/disc/clean.vob"),
                Path("/media/disc/damaged.vob"),
            ],
            output_dir=tmp_path,
            ai_repair=False,
        ),
        cancel_requested=lambda: False,
    )

    details = result["report"]["clips_detail"]
    assert [detail["output_path"] for detail in details] == [
        str(tmp_path / "clean.mp4"),
        str(tmp_path / "damaged.mp4"),
    ]
    assert details[0]["timeline"]["ranges"] == []
    assert details[1]["timeline"]["ranges"][0]["state"] == "damaged"
    assert result["report"]["timeline"]["range_counts"]["damaged"] == 1
    assert result["report"]["timeline"]["frame_counts"]["damaged"] == 25


def test_converter_uses_repair_decisions_for_large_generated_ranges(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
            completed(["ffprobe"], stdout=probe_payload(duration=30.0)),
            completed(
                ["ffmpeg"],
                stderr="""
                [freezedetect] freeze_start: 10
                [freezedetect] freeze_duration: 2.4
                [freezedetect] freeze_end: 12.4
                """,
            ),
        ]
    )

    class Repairer:
        def repair(self, _video_path: Path, _issues: list[FrameIssue], _cancel_requested) -> dict:
            return {"frames_regenerated": 60, "tool": "studio-provider"}

    converter = MediaConverter(
        runner=runner,
        frame_repairer=Repairer(),
        repair_providers=(
            RepairProvider(
                id="studio-provider",
                capabilities=frozenset({ProviderCapability.INPAINTING}),
            ),
        ),
    )

    result = converter.convert(
        ConversionRequest(
            source_paths=[Path("/media/disc/large-gap.vob")],
            output_dir=tmp_path,
            ai_repair=True,
        ),
        cancel_requested=lambda: False,
    )

    assert result["report"]["timeline"]["states"]["generated"] == 1
    assert result["report"]["timeline"]["ranges"][0]["state"] == "generated"
    assert result["report"]["timeline"]["ranges"][0]["action"] == "creative_reconstruction"
    assert result["report"]["timeline"]["ranges"][0]["required_capability"] == "inpainting"
    assert result["report"]["timeline"]["ranges"][0]["provider_id"] == "studio-provider"
    assert result["report"]["timeline"]["ranges"][0]["preview_recommended"] is True
    assert result["report"]["timeline"]["ranges"][0]["report_label_required"] is True
    assert any("generated frame range" in warning for warning in result["warnings"])
