from pathlib import Path
from subprocess import CompletedProcess

import pytest

from rawcd.converter import MediaConverter, ProtectedMediaError
from rawcd.jobs import ConversionRequest
from rawcd.models import ProviderCapability
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
            completed(["ffprobe"], stdout=probe_payload()),
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
    }
    assert any("skipped frame range" in warning for warning in result["warnings"])


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
    assert any("generated frame range" in warning for warning in result["warnings"])
