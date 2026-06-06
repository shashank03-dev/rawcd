from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DiscType(str, Enum):
    DVD_VIDEO = "dvd_video"
    VCD = "vcd"
    DATA_VIDEO = "data_video"
    UNKNOWN = "unknown"


class SourceKind(str, Enum):
    DVD_TITLE_SET = "dvd_title_set"
    VCD_TRACK = "vcd_track"
    VIDEO_FILE = "video_file"


@dataclass(frozen=True)
class PlayableSource:
    path: Path
    kind: SourceKind
    label: str


@dataclass(frozen=True)
class DiscInspection:
    disc_type: DiscType
    label: str
    playable_sources: list[PlayableSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DiscClassifier:
    VIDEO_EXTENSIONS = {
        ".3gp",
        ".avi",
        ".dat",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".mts",
        ".vob",
        ".webm",
        ".wmv",
    }

    def classify(self, root: Path) -> DiscInspection:
        disc_root = Path(root)
        dvd_sources = self._find_dvd_sources(disc_root)
        if dvd_sources:
            return DiscInspection(
                disc_type=DiscType.DVD_VIDEO,
                label="DVD-Video",
                playable_sources=dvd_sources,
            )

        vcd_sources = self._find_vcd_sources(disc_root)
        if vcd_sources:
            return DiscInspection(
                disc_type=DiscType.VCD,
                label="VCD/SVCD",
                playable_sources=vcd_sources,
            )

        video_sources = self._find_data_video_sources(disc_root)
        if video_sources:
            return DiscInspection(
                disc_type=DiscType.DATA_VIDEO,
                label="Data video disc",
                playable_sources=video_sources,
            )

        return DiscInspection(
            disc_type=DiscType.UNKNOWN,
            label="Unknown disc",
            warnings=[
                "No DVD-Video, VCD/SVCD, or supported video files were found."
            ],
        )

    def _find_dvd_sources(self, root: Path) -> list[PlayableSource]:
        video_ts = self._case_insensitive_child(root, "VIDEO_TS")
        if video_ts is None or not video_ts.is_dir():
            return []

        ifo = self._case_insensitive_child(video_ts, "VIDEO_TS.IFO")
        vobs = sorted(
            path
            for path in video_ts.iterdir()
            if path.is_file() and path.suffix.upper() == ".VOB"
        )
        if ifo is None or not vobs:
            return []

        return [
            PlayableSource(path=vob, kind=SourceKind.DVD_TITLE_SET, label=vob.stem)
            for vob in vobs
        ]

    def _find_vcd_sources(self, root: Path) -> list[PlayableSource]:
        sources: list[Path] = []
        for dirname, extensions in {
            "MPEGAV": {".DAT"},
            "MPEG2": {".MPG", ".MPEG"},
        }.items():
            directory = self._case_insensitive_child(root, dirname)
            if directory is None or not directory.is_dir():
                continue
            sources.extend(
                sorted(
                    path
                    for path in directory.iterdir()
                    if path.is_file() and path.suffix.upper() in extensions
                )
            )

        return [
            PlayableSource(path=source, kind=SourceKind.VCD_TRACK, label=source.stem)
            for source in sources
        ]

    def _find_data_video_sources(self, root: Path) -> list[PlayableSource]:
        video_ts = self._case_insensitive_child(root, "VIDEO_TS")
        ignored = {video_ts.resolve()} if video_ts is not None and video_ts.exists() else set()

        sources = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.VIDEO_EXTENSIONS:
                continue
            if any(parent.resolve() in ignored for parent in path.parents):
                continue
            sources.append(
                PlayableSource(path=path, kind=SourceKind.VIDEO_FILE, label=path.stem)
            )
        return sources

    def _case_insensitive_child(self, root: Path, name: str) -> Path | None:
        if not root.exists():
            return None
        expected = name.upper()
        for child in root.iterdir():
            if child.name.upper() == expected:
                return child
        return None
