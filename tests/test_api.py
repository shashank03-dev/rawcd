from pathlib import Path

from fastapi.testclient import TestClient

from rawcd.api import create_app
from rawcd.devices import OpticalDevice
from rawcd.jobs import ConversionRequest, JobManager


def test_scan_devices_endpoint_returns_optical_drives(tmp_path: Path) -> None:
    class Scanner:
        def scan(self) -> list[OpticalDevice]:
            return [
                OpticalDevice(
                    device_path="/dev/sr0",
                    model="USB DVD RW",
                    mount_path=str(tmp_path),
                    is_usb=True,
                    has_media=True,
                )
            ]

    app = create_app(scanner=Scanner())
    client = TestClient(app)

    response = client.get("/scan_devices")

    assert response.status_code == 200
    assert response.json() == [
        {
            "device_path": "/dev/sr0",
            "model": "USB DVD RW",
            "mount_path": str(tmp_path),
            "is_usb": True,
            "has_media": True,
        }
    ]


def test_inspect_disc_endpoint_returns_detected_sources(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"sample")
    client = TestClient(create_app())

    response = client.post("/inspect_disc", json={"path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["disc_type"] == "data_video"
    assert payload["label"] == "Data video disc"
    assert payload["playable_sources"] == [
        {"path": str(video), "kind": "video_file", "label": "clip"}
    ]


def test_conversion_job_endpoints_return_status(tmp_path: Path) -> None:
    output = tmp_path / "clip.mp4"

    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        return {"outputs": [output], "report": {"clips": 1}, "warnings": []}

    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager))

    started = client.post(
        "/start_conversion",
        json={
            "source_paths": ["/media/disc/clip.dat"],
            "output_dir": str(tmp_path),
            "ai_repair": True,
        },
    )

    assert started.status_code == 200
    job_id = started.json()["job_id"]
    assert started.json()["status"] == "completed"

    status = client.get(f"/get_job_status/{job_id}")
    assert status.status_code == 200
    assert status.json()["outputs"] == [str(output)]
    assert status.json()["report"] == {"clips": 1}


def test_start_conversion_expands_user_output_path(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, ConversionRequest] = {}

    def converter(request: ConversionRequest, _cancel_requested) -> dict:
        captured["request"] = request
        return {"outputs": [], "report": {"clips": 0}, "warnings": []}

    monkeypatch.setenv("HOME", str(tmp_path))
    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/start_conversion",
        json={
            "source_paths": ["~/disc/clip.dat"],
            "output_dir": "~/Videos/RawCD",
            "ai_repair": False,
        },
    )

    assert response.status_code == 200
    assert captured["request"].source_paths == [tmp_path / "disc" / "clip.dat"]
    assert captured["request"].output_dir == tmp_path / "Videos" / "RawCD"
