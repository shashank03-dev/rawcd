from pathlib import Path
from subprocess import CompletedProcess

import pytest

from rawcd.converter import MediaConverter, ProtectedMediaError
from rawcd.jobs import ConversionRequest
from rawcd.repair import FrameIssue


class FakeRunner:
    def __init__(self, responses: list[CompletedProcess[str]]) -> None:
        self.responses = responses
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return self.responses.pop(0)


def completed(command: list[str], stderr: str = "") -> CompletedProcess[str]:
    return CompletedProcess(command, 0, stdout="", stderr=stderr)


def failed(command: list[str], stderr: str) -> CompletedProcess[str]:
    return CompletedProcess(command, 1, stdout="", stderr=stderr)


def test_converter_writes_one_mp4_per_source_and_report(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            completed(["ffmpeg"]),
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
    assert runner.commands[0][-1] == str(tmp_path / "AVSEQ01.mp4")
    assert runner.commands[1][:4] == ["ffmpeg", "-hide_banner", "-i", str(tmp_path / "AVSEQ01.mp4")]


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
