from pathlib import Path

from rawcd.disc import SourceKind
from rawcd.parser import DiscParser, DiscType


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample")
    return path


def test_parser_detects_personal_dvd_video_layout(tmp_path: Path) -> None:
    touch(tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO")
    vob = touch(tmp_path / "VIDEO_TS" / "VTS_01_1.VOB")

    result = DiscParser().parse(tmp_path)

    assert result.disc_type is DiscType.DVD_VIDEO
    assert result.label == "DVD-Video"
    assert [(source.kind, source.path) for source in result.playable_sources] == [
        (SourceKind.DVD_TITLE_SET, vob)
    ]
    assert result.warnings == []


def test_parser_detects_vcd_layout(tmp_path: Path) -> None:
    dat = touch(tmp_path / "MPEGAV" / "AVSEQ01.DAT")

    result = DiscParser().parse(tmp_path)

    assert result.disc_type is DiscType.VCD
    assert result.label == "VCD/SVCD"
    assert [(source.kind, source.path) for source in result.playable_sources] == [
        (SourceKind.VCD_TRACK, dat)
    ]


def test_parser_detects_data_video_disc(tmp_path: Path) -> None:
    video = touch(tmp_path / "clips" / "family.mov")

    result = DiscParser().parse(tmp_path)

    assert result.disc_type is DiscType.DATA_VIDEO
    assert result.label == "Data video disc"
    assert [(source.kind, source.path) for source in result.playable_sources] == [
        (SourceKind.VIDEO_FILE, video)
    ]


def test_parser_detects_data_disc_without_supported_video(tmp_path: Path) -> None:
    touch(tmp_path / "README.txt")

    result = DiscParser().parse(tmp_path)

    assert result.disc_type is DiscType.DATA_DISC
    assert result.playable_sources == []
    assert result.warnings == [
        "No supported video files were found on this data disc."
    ]


def test_parser_reports_missing_path_as_unknown(tmp_path: Path) -> None:
    result = DiscParser().parse(tmp_path / "missing")

    assert result.disc_type is DiscType.UNKNOWN
    assert result.playable_sources == []
    assert result.warnings == ["Path not found: " + str(tmp_path / "missing")]


def test_parser_detects_protected_media_markers() -> None:
    result = DiscParser().parse_tool_output(
        Path("/media/MOVIE"),
        "libdvdread: Encrypted DVD support unavailable; CSS authentication failed",
    )

    assert result.disc_type is DiscType.PROTECTED_MEDIA
    assert result.label == "Protected media"
    assert result.playable_sources == []
    assert result.warnings == [
        "This disc appears protected. RawCD restores personal media and cannot process protected commercial discs."
    ]


def test_parser_detects_known_protection_layout_signs(tmp_path: Path) -> None:
    touch(tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO")
    touch(tmp_path / "VIDEO_TS" / "VTS_01_1.VOB")
    touch(tmp_path / "VIDEO_TS" / "CSS.KEY")

    result = DiscParser().parse(tmp_path)

    assert result.disc_type is DiscType.PROTECTED_MEDIA
    assert result.playable_sources == []
    assert result.warnings == [
        "This disc appears protected. RawCD restores personal media and cannot process protected commercial discs."
    ]
