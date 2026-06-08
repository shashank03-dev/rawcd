from pathlib import Path
from subprocess import CompletedProcess

from rawcd.disc import DiscClassifier, DiscType, SourceKind
from rawcd.parser import DiscType as ParserDiscType


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample")
    return path


def test_classifies_dvd_video_from_video_ts_layout(tmp_path: Path) -> None:
    touch(tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO")
    vob = touch(tmp_path / "VIDEO_TS" / "VTS_01_1.VOB")

    result = DiscClassifier().classify(tmp_path)

    assert result.disc_type is DiscType.DVD_VIDEO
    assert result.label == "DVD-Video"
    assert [(source.kind, source.path) for source in result.playable_sources] == [
        (SourceKind.DVD_TITLE_SET, vob)
    ]
    assert result.warnings == []


def test_classifies_vcd_from_mpegav_dat_files(tmp_path: Path) -> None:
    dat = touch(tmp_path / "MPEGAV" / "AVSEQ01.DAT")

    result = DiscClassifier().classify(tmp_path)

    assert result.disc_type is DiscType.VCD
    assert result.label == "VCD/SVCD"
    assert [(source.kind, source.path) for source in result.playable_sources] == [
        (SourceKind.VCD_TRACK, dat)
    ]


def test_classifies_data_disc_video_files_in_stable_order(tmp_path: Path) -> None:
    avi = touch(tmp_path / "family" / "clip-b.avi")
    mp4 = touch(tmp_path / "clip-a.mp4")
    touch(tmp_path / "notes.txt")

    result = DiscClassifier().classify(tmp_path)

    assert result.disc_type is DiscType.DATA_VIDEO
    assert result.label == "Data video disc"
    assert [(source.kind, source.path) for source in result.playable_sources] == [
        (SourceKind.VIDEO_FILE, mp4),
        (SourceKind.VIDEO_FILE, avi),
    ]


def test_data_disc_without_video_has_actionable_warning(tmp_path: Path) -> None:
    touch(tmp_path / "README.txt")

    result = DiscClassifier().classify(tmp_path)

    assert result.disc_type is DiscType.DATA_DISC
    assert result.playable_sources == []
    assert result.warnings == [
        "No supported video files were found on this data disc."
    ]


def test_disc_module_reexports_parser_disc_type_for_compatibility() -> None:
    assert DiscType is ParserDiscType


def test_classifier_uses_tool_output_to_detect_protected_dvd(tmp_path: Path) -> None:
    touch(tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO")
    touch(tmp_path / "VIDEO_TS" / "VTS_01_1.VOB")

    class ProtectedProbe:
        def run(self, command: list[str]) -> CompletedProcess[str]:
            return CompletedProcess(
                command,
                1,
                stdout="",
                stderr="libdvdread: Encrypted DVD support unavailable",
            )

    result = DiscClassifier(probe_runner=ProtectedProbe()).classify(tmp_path)

    assert result.disc_type is DiscType.PROTECTED_MEDIA
    assert result.playable_sources == []
