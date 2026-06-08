from pathlib import Path

from fastapi.testclient import TestClient

from rawcd.api import create_app
from rawcd.devices import OpticalDevice
from rawcd.jobs import ConversionRequest, JobManager
from rawcd.models import RecoveryMode, RestoreMode
from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderEstimate, ProviderHealth, ProviderInfo
from rawcd.recovery import DdrescueAdapter, RecoveryPlanner
from rawcd.settings import ProviderRegistry, ProviderSettingsStore


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
        return {
            "outputs": [output],
            "report": {"clips": 1, "timeline": {"states": {"original": 1}, "ranges": []}},
            "warnings": [],
        }

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
    assert status.json()["report"] == {
        "clips": 1,
        "timeline": {"states": {"original": 1}, "ranges": []},
    }


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
    assert captured["request"].recovery_mode is RecoveryMode.QUICK
    assert captured["request"].restore_mode is RestoreMode.FAITHFUL


def test_start_conversion_accepts_explicit_recovery_and_restore_modes(
    tmp_path: Path,
) -> None:
    captured: dict[str, ConversionRequest] = {}

    def converter(request: ConversionRequest, _cancel_requested) -> dict:
        captured["request"] = request
        return {
            "outputs": [],
            "report": {"clips": 0},
            "warnings": ["converter warning"],
        }

    class MissingRunner:
        def run(self, command: list[str]):
            raise FileNotFoundError(command[0])

    manager = JobManager(
        converter=converter,
        run_inline=True,
        recovery_planner=RecoveryPlanner(
            rescue_adapter=DdrescueAdapter(runner=MissingRunner())
        ),
    )
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/start_conversion",
        json={
            "source_paths": ["/media/OLD_DISC/clip.vob"],
            "output_dir": str(tmp_path),
            "ai_repair": False,
            "recovery_mode": "maximum",
            "restore_mode": "enhanced",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["request"].recovery_mode is RecoveryMode.MAXIMUM
    assert captured["request"].restore_mode is RestoreMode.ENHANCED
    assert payload["recovery_warnings"] == [
        "ddrescue is not installed; using the direct source instead of a recovered image."
    ]
    assert payload["warnings"] == [
        "ddrescue is not installed; using the direct source instead of a recovered image.",
        "converter warning",
    ]

    status = client.get(f"/get_job_status/{payload['job_id']}")
    assert status.status_code == 200
    assert status.json()["recovery_warnings"] == payload["recovery_warnings"]


class FakeProvider:
    id = "fake-provider"
    label = "Fake Provider"
    kind = ProviderKind.CLOUD
    capabilities = (ProviderCapability.DENOISE,)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth.available("fake provider ready")

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        return ProviderEstimate(
            capability=capability,
            cost="paid",
            execution="cloud_api",
            speed="unknown",
        )


def test_provider_list_endpoint_returns_provider_info_with_redacted_settings(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "providers.json")
    store.configure("fake-provider", {"enabled": True, "api_key": "secret"})
    registry = ProviderRegistry(settings_store=store, providers=(FakeProvider(),))
    client = TestClient(create_app(provider_registry=registry))

    response = client.get("/providers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "fake-provider",
            "label": "Fake Provider",
            "kind": "cloud",
            "capabilities": ["denoise"],
            "settings": {
                "provider_id": "fake-provider",
                "enabled": True,
                "api_key_configured": True,
                "api_key": None,
                "base_url": None,
                "executable_path": None,
                "extra": {},
            },
        }
    ]


def test_provider_test_endpoint_returns_health(tmp_path: Path) -> None:
    registry = ProviderRegistry(
        settings_store=ProviderSettingsStore(tmp_path / "providers.json"),
        providers=(FakeProvider(),),
    )
    client = TestClient(create_app(provider_registry=registry))

    response = client.post("/providers/fake-provider/test")

    assert response.status_code == 200
    assert response.json() == {
        "status": "available",
        "message": "fake provider ready",
        "details": {},
    }


def test_provider_configure_endpoint_persists_secret_but_redacts_response(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "providers.json")
    registry = ProviderRegistry(settings_store=store, providers=(FakeProvider(),))
    client = TestClient(create_app(provider_registry=registry))

    response = client.post(
        "/providers/fake-provider/configure",
        json={
            "enabled": True,
            "api_key": "new-secret",
            "base_url": "https://provider.example",
        },
    )

    assert response.status_code == 200
    assert store.get("fake-provider").api_key == "new-secret"
    assert response.json()["settings"] == {
        "provider_id": "fake-provider",
        "enabled": True,
        "api_key_configured": True,
        "api_key": None,
        "base_url": "https://provider.example",
        "executable_path": None,
        "extra": {},
    }


def test_provider_configure_endpoint_can_clear_secrets_and_urls(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "providers.json")
    store.configure(
        "fake-provider",
        {"enabled": True, "api_key": "old-secret", "base_url": "https://old.example"},
    )
    registry = ProviderRegistry(settings_store=store, providers=(FakeProvider(),))
    client = TestClient(create_app(provider_registry=registry))

    response = client.post(
        "/providers/fake-provider/configure",
        json={"api_key": None, "base_url": None},
    )

    assert response.status_code == 200
    assert store.get("fake-provider").api_key is None
    assert store.get("fake-provider").base_url is None
    assert response.json()["settings"]["api_key_configured"] is False
