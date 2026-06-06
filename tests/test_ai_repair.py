from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from rawcd.ai_repair import RifeFrameInterpolator, RifeInstaller, UrlLibDownloader


class FakeDownloader:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.urls: list[str] = []

    def download(self, url: str, destination: Path) -> None:
        self.urls.append(url)
        destination.write_bytes(self.archive)


def make_rife_archive() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("rife-ncnn-vulkan-20221029-ubuntu/rife-ncnn-vulkan", "#!/bin/sh\n")
        archive.writestr("rife-ncnn-vulkan-20221029-ubuntu/models/rife-v4/flownet.param", "model")
    return buffer.getvalue()


def test_installer_downloads_and_extracts_linux_rife_binary(tmp_path: Path) -> None:
    downloader = FakeDownloader(make_rife_archive())
    installer = RifeInstaller(install_dir=tmp_path, downloader=downloader)

    binary = installer.ensure_installed()

    assert binary == tmp_path / "rife-ncnn-vulkan-20221029-ubuntu" / "rife-ncnn-vulkan"
    assert binary.exists()
    assert binary.stat().st_mode & 0o111
    assert downloader.urls == [
        "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-ubuntu.zip"
    ]


def test_interpolator_builds_rife_command() -> None:
    interpolator = RifeFrameInterpolator(binary_path=Path("/opt/rife/rife-ncnn-vulkan"))

    command = interpolator.build_command(
        previous_frame=Path("/tmp/a.png"),
        next_frame=Path("/tmp/b.png"),
        output_frame=Path("/tmp/out.png"),
    )

    assert command == [
        "/opt/rife/rife-ncnn-vulkan",
        "-0",
        "/tmp/a.png",
        "-1",
        "/tmp/b.png",
        "-o",
        "/tmp/out.png",
    ]


def test_downloader_rejects_non_https_or_non_github_urls(tmp_path: Path) -> None:
    downloader = UrlLibDownloader()

    with pytest.raises(ValueError, match="Only GitHub HTTPS release URLs"):
        downloader.download("file:///tmp/rife.zip", tmp_path / "rife.zip")

    with pytest.raises(ValueError, match="Only GitHub HTTPS release URLs"):
        downloader.download("https://example.com/rife.zip", tmp_path / "rife.zip")
