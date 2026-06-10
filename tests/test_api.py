from pathlib import Path

from fastapi.testclient import TestClient

import rawcd.api as rawcd_api
from rawcd.api import create_app
from rawcd.devices import OpticalDevice
from rawcd.jobs import ConversionRequest, JobManager, JobPreview
from rawcd.models import (
    ExportProfile,
    ProProfile,
    ProVerificationStatus,
    RecoveryMode,
    RestoreLane,
    RestoreMode,
    RightsDeclaration,
)
from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderEstimate, ProviderHealth, ProviderInfo
from rawcd.recovery import DdrescueAdapter, RecoveryPlanner
from rawcd.repair_pipeline import RepairDecisionEngine, RepairGap
from rawcd.settings import ProProfileSettingsStore, ProviderRegistry, ProviderSettingsStore


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
    assert status.json()["report"]["clips"] == 1
    assert status.json()["report"]["timeline"] == {
        "states": {"original": 1},
        "ranges": [],
    }
    assert status.json()["report"]["home_report"]["json_save_path"] == str(
        tmp_path / "clip.rawcd-home-report.json"
    )

    preview = client.get(f"/get_job_preview/{job_id}")
    assert preview.status_code == 200
    assert preview.json() == {
        "job_id": job_id,
        "current_frame": 0,
        "current_timestamp": 0.0,
        "current_operation": "Exporting final video",
        "preview_image_path": None,
    }


def test_job_preview_endpoint_returns_404_for_unknown_job() -> None:
    client = TestClient(create_app())

    response = client.get("/get_job_preview/not-a-job")

    assert response.status_code == 404


def test_job_preview_endpoint_returns_loadable_preview_image_url(tmp_path: Path) -> None:
    manager = JobManager(
        converter=lambda *_: {"outputs": [], "report": {}, "warnings": []},
        run_inline=True,
    )
    job = manager.create_pending_job(
        ConversionRequest(source_paths=[tmp_path / "clip.vob"], output_dir=tmp_path)
    )
    image = tmp_path / "preview.jpg"
    image.write_bytes(b"jpeg")
    job.preview = JobPreview(job_id=job.job_id, preview_image_path=image)
    client = TestClient(create_app(job_manager=manager))

    preview = client.get(f"/get_job_preview/{job.job_id}")
    image_response = client.get(f"/preview_image/{job.job_id}")

    assert preview.status_code == 200
    assert preview.json()["preview_image_path"] == (
        f"http://127.0.0.1:8765/preview_image/{job.job_id}"
    )
    assert image_response.status_code == 200
    assert image_response.content == b"jpeg"


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
    assert captured["request"].export_profile.value == "home_mp4"
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


def test_start_conversion_accepts_explicit_export_profile(
    tmp_path: Path,
) -> None:
    captured: dict[str, ConversionRequest] = {}

    def converter(request: ConversionRequest, _cancel_requested) -> dict:
        captured["request"] = request
        return {"outputs": [], "report": {"clips": 0}, "warnings": []}

    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/start_conversion",
        json={
            "source_paths": ["/media/OLD_DISC/clip.vob"],
            "output_dir": str(tmp_path),
            "ai_repair": False,
            "export_profile": "home_mp4",
        },
    )

    assert response.status_code == 200
    assert captured["request"].export_profile.value == "home_mp4"


def test_start_conversion_rejects_archival_export_without_pro_lane(
    tmp_path: Path,
) -> None:
    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        raise AssertionError("converter should not run for unauthorized archival export")

    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/start_conversion",
        json={
            "source_paths": ["/media/OLD_DISC/clip.vob"],
            "output_dir": str(tmp_path),
            "ai_repair": False,
            "export_profile": "prores_422_hq",
        },
    )

    assert response.status_code == 403
    assert "rights declaration" in response.text.lower()


def test_start_conversion_rejects_unapproved_pro_restore(
    tmp_path: Path,
) -> None:
    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        raise AssertionError("converter should not run for unapproved Pro restore")

    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/start_conversion",
        json={
            "lane": "pro",
            "source_paths": ["/media/OLD_DISC/clip.vob"],
            "output_dir": str(tmp_path),
            "ai_repair": False,
            "export_profile": "prores_422_hq",
            "commercial_use": True,
            "rights_declaration": {
                "project_name": "Restored Feature",
                "organization": "Archive House",
                "source_title": "Original Camera DVD",
                "rights_basis": "rights_holder",
                "permission_reference": "contract-2026-001",
            },
        },
    )

    assert response.status_code == 403
    assert "verified rights-holder access" in response.text.lower()


def test_start_conversion_accepts_approved_pro_restore_with_rights(
    tmp_path: Path,
) -> None:
    captured: dict[str, ConversionRequest] = {}

    def converter(request: ConversionRequest, _cancel_requested) -> dict:
        captured["request"] = request
        return {"outputs": [], "report": {"clips": 0}, "warnings": []}

    settings_path = tmp_path / "settings.json"
    ProProfileSettingsStore(settings_path).save(
        ProProfile(
            name="Asha Rao",
            organization="Archive House",
            email="asha@example.test",
            country="IN",
            intended_use="Commercial film restoration",
            verification_status=ProVerificationStatus.APPROVED,
        )
    )
    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(
        create_app(
            job_manager=manager,
            provider_registry=ProviderRegistry(
                settings_store=ProviderSettingsStore(settings_path),
                providers=(FakeProvider(),),
            ),
        )
    )

    response = client.post(
        "/start_conversion",
        json={
            "lane": "pro",
            "source_paths": ["/media/OLD_DISC/clip.vob"],
            "output_dir": str(tmp_path),
            "ai_repair": False,
            "export_profile": "prores_422_hq",
            "extract_wav_audio": True,
            "commercial_use": True,
            "rights_declaration": {
                "project_name": "Restored Feature",
                "organization": "Archive House",
                "source_title": "Original Camera DVD",
                "rights_basis": "rights_holder",
                "permission_reference": "contract-2026-001",
            },
        },
    )

    assert response.status_code == 200
    assert captured["request"].lane.value == "pro"
    assert captured["request"].export_profile.value == "prores_422_hq"
    assert captured["request"].extract_wav_audio is True
    assert captured["request"].rights_declaration is not None


def test_start_conversion_refuses_detected_protected_home_source(
    tmp_path: Path,
) -> None:
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    (video_ts / "VIDEO_TS.IFO").write_bytes(b"sample")
    source = video_ts / "VTS_01_1.VOB"
    source.write_bytes(b"sample")
    (video_ts / "CSS.KEY").write_bytes(b"protected marker")

    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        raise AssertionError("converter should not run for protected Home media")

    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/start_conversion",
        json={
            "source_paths": [str(source)],
            "output_dir": str(tmp_path / "out"),
            "ai_repair": False,
        },
    )

    assert response.status_code == 403
    assert "protected commercial discs" in response.text.lower()


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


class RepairRoutingProvider:
    id = "repair-routing-provider"
    label = "Repair Routing Provider"
    kind = ProviderKind.CLOUD
    capabilities = (ProviderCapability.INTERPOLATION,)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth.available("repair routing provider ready")

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        return ProviderEstimate(
            capability=capability,
            cost="paid",
            execution="cloud_api",
            speed="unknown",
        )


def test_provider_configure_updates_subsequent_job_repair_routing_without_restart(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class RoutingAwareConverter:
        def __init__(self, repair_providers) -> None:
            self.repair_providers = tuple(repair_providers)

        def convert(self, _request: ConversionRequest, _cancel_requested) -> dict:
            decision = RepairDecisionEngine().decide(
                RepairGap(start_seconds=1.0, end_seconds=1.1, missing_frames=1),
                self.repair_providers,
            )
            return {
                "outputs": [],
                "warnings": [],
                "report": {
                    "repair": {
                        "provider_id": decision.provider_id,
                        "action": decision.action.value,
                    }
                },
            }

    class InlineJobManager(JobManager):
        def __init__(self, converter) -> None:
            super().__init__(converter=converter, run_inline=True)

    monkeypatch.setattr(rawcd_api, "MediaConverter", RoutingAwareConverter)
    monkeypatch.setattr(rawcd_api, "JobManager", InlineJobManager)
    store = ProviderSettingsStore(tmp_path / "providers.json")
    registry = ProviderRegistry(
        settings_store=store,
        providers=(RepairRoutingProvider(),),
    )
    client = TestClient(rawcd_api.create_app(provider_registry=registry))

    configured = client.post(
        "/providers/repair-routing-provider/configure",
        json={"enabled": True},
    )
    response = client.post(
        "/start_conversion",
        json={
            "source_paths": ["/media/disc/clip.dat"],
            "output_dir": str(tmp_path),
            "ai_repair": True,
        },
    )

    assert configured.status_code == 200
    assert response.status_code == 200
    assert response.json()["report"]["repair"] == {
        "provider_id": "repair-routing-provider",
        "action": "auto_interpolate",
    }


def test_pro_profile_endpoints_store_and_return_redacted_status(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            provider_registry=ProviderRegistry(
                settings_store=ProviderSettingsStore(tmp_path / "settings.json"),
                providers=(FakeProvider(),),
            )
        )
    )

    saved = client.post(
        "/pro/profile",
        json={
            "name": "Asha Rao",
            "organization": "Archive House",
            "email": "asha@example.test",
            "country": "IN",
            "intended_use": "Commercial film restoration",
            "verification_status": "pending",
        },
    )
    fetched = client.get("/pro/profile")

    assert saved.status_code == 200
    assert saved.json()["verification_status"] == "pending"
    assert saved.json()["can_enable_pro_projects"] is False
    assert fetched.json()["organization"] == "Archive House"


def test_pro_profile_endpoint_does_not_accept_client_side_approval(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            provider_registry=ProviderRegistry(
                settings_store=ProviderSettingsStore(tmp_path / "settings.json"),
                providers=(FakeProvider(),),
            )
        )
    )

    response = client.post(
        "/pro/profile",
        json={
            "name": "Asha Rao",
            "organization": "Archive House",
            "email": "asha@example.test",
            "country": "IN",
            "intended_use": "Commercial film restoration",
            "verification_status": "approved",
            "approved_at": "2026-06-07T12:30:00+00:00",
            "server_verification_id": "client-supplied",
        },
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == "pending"
    assert response.json()["can_enable_pro_projects"] is False
    assert response.json()["approved_at"] is None
    assert response.json()["server_verification_id"] is None


def test_pro_verification_update_requires_configured_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.json"
    client = TestClient(
        create_app(
            provider_registry=ProviderRegistry(
                settings_store=ProviderSettingsStore(settings_path),
                providers=(FakeProvider(),),
            )
        )
    )
    client.post(
        "/pro/profile",
        json={
            "name": "Asha Rao",
            "organization": "Archive House",
            "email": "asha@example.test",
            "country": "IN",
            "intended_use": "Commercial film restoration",
        },
    )

    blocked = client.post(
        "/pro/profile/verification",
        json={
            "verification_token": "wrong",
            "verification_status": "approved",
            "server_verification_id": "server-check-1",
        },
    )
    monkeypatch.setenv("RAWCD_PRO_VERIFICATION_TOKEN", "pro-secret")
    approved = client.post(
        "/pro/profile/verification",
        json={
            "verification_token": "pro-secret",
            "verification_status": "approved",
            "server_verification_id": "server-check-1",
            "approved_at": "2026-06-07T12:30:00+00:00",
        },
    )

    assert blocked.status_code == 403
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "approved"
    assert approved.json()["server_verification_id"] == "server-check-1"
    assert approved.json()["can_enable_pro_projects"] is True


def test_pro_verification_update_refuses_incomplete_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RAWCD_PRO_VERIFICATION_TOKEN", "pro-secret")
    settings_path = tmp_path / "settings.json"
    ProProfileSettingsStore(settings_path).save(
        ProProfile(
            name="Asha Rao",
            organization="",
            email="asha@example.test",
            country="IN",
            intended_use="Commercial film restoration",
            verification_status=ProVerificationStatus.PENDING,
        )
    )
    client = TestClient(
        create_app(
            provider_registry=ProviderRegistry(
                settings_store=ProviderSettingsStore(settings_path),
                providers=(FakeProvider(),),
            )
        )
    )

    response = client.post(
        "/pro/profile/verification",
        json={
            "verification_token": "pro-secret",
            "verification_status": "approved",
            "server_verification_id": "server-check-1",
        },
    )

    assert response.status_code == 400
    assert "complete pro profile" in response.text.lower()


def test_rights_validation_endpoint_refuses_unapproved_pro_project(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            provider_registry=ProviderRegistry(
                settings_store=ProviderSettingsStore(tmp_path / "settings.json"),
                providers=(FakeProvider(),),
            )
        )
    )
    client.post(
        "/pro/profile",
        json={
            "name": "Asha Rao",
            "organization": "Archive House",
            "email": "asha@example.test",
            "country": "IN",
            "intended_use": "Commercial film restoration",
            "verification_status": "pending",
        },
    )

    response = client.post(
        "/rights/validate",
        json={
            "lane": "pro",
            "commercial_use": True,
            "protected_media": True,
            "rights_declaration": {
                "project_name": "Restored Feature",
                "organization": "Archive House",
                "source_title": "Original Camera DVD",
                "rights_basis": "rights_holder",
                "permission_reference": "contract-2026-001",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert "verified rights-holder access" in response.json()["reason"].lower()


def test_home_report_endpoint_writes_report_file(tmp_path: Path) -> None:
    client = TestClient(create_app())
    report_path = tmp_path / "home-report.json"

    response = client.post(
        "/reports/home",
        json={
            "report_path": str(report_path),
            "recovered_clips": 1,
            "output_files": [str(tmp_path / "clip.mp4")],
            "damaged_sections": [],
            "reconstructed_sections": [],
            "skipped_sections": [],
            "provider_used": "local-ffmpeg",
            "warnings": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["json_save_path"] == str(report_path)
    assert report_path.exists()


def test_pro_report_endpoint_requires_completed_pro_job_and_uses_job_metadata(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    ProProfileSettingsStore(settings_path).save(
        ProProfile(
            name="Asha Rao",
            organization="Archive House",
            email="asha@example.test",
            country="IN",
            intended_use="Commercial film restoration",
            verification_status=ProVerificationStatus.APPROVED,
        )
    )
    output = tmp_path / "clip.mov"

    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        return {
            "outputs": [output],
            "report": {
                "clips": 1,
                "export_profile": "prores_422_hq",
                "repair": {"tool": "local-ffmpeg"},
                "timeline": {
                    "frame_counts": {"generated": 3, "interpolated": 2, "enhanced": 0},
                    "ranges": [
                        {
                            "start_seconds": 1.0,
                            "end_seconds": 1.2,
                            "state": "generated",
                            "provider_id": "local-ffmpeg",
                        }
                    ],
                },
            },
            "warnings": ["Generated sections are labeled separately."],
        }

    registry = ProviderRegistry(
        settings_store=ProviderSettingsStore(settings_path),
        providers=(FakeProvider(),),
    )
    manager = JobManager(converter=converter, run_inline=True)
    client = TestClient(create_app(job_manager=manager, provider_registry=registry))
    started = client.post(
        "/start_conversion",
        json={
            "lane": "pro",
            "source_paths": ["/media/OLD_DISC/clip.vob"],
            "output_dir": str(tmp_path),
            "ai_repair": True,
            "export_profile": "prores_422_hq",
            "rights_declaration": {
                "project_name": "Restored Feature",
                "organization": "Archive House",
                "source_title": "Original Camera DVD",
                "rights_basis": "rights_holder",
                "permission_reference": "contract-2026-001",
            },
        },
    )
    report_path = tmp_path / "pro-audit.json"

    response = client.post(
        "/reports/pro",
        json={
            "job_id": started.json()["job_id"],
            "json_path": str(report_path),
            "warnings": ["operator note warning"],
        },
    )

    assert started.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["rights_declaration"]["project_name"] == "Restored Feature"
    assert payload["generated_frame_counts"] == {
        "generated": 3,
        "interpolated": 2,
        "enhanced": 0,
    }
    assert payload["export_profile"] == "prores_422_hq"
    assert payload["providers"] == [
        {"provider_id": "local-ffmpeg", "source": "job_repair"}
    ]
    assert payload["warnings"] == [
        "Generated sections are labeled separately.",
        "operator note warning",
    ]
    assert report_path.exists()


def test_pro_report_endpoint_rejects_non_completed_job(tmp_path: Path) -> None:
    rights = RightsDeclaration(
        project_name="Restored Feature",
        organization="Archive House",
        source_title="Original Camera DVD",
        rights_basis="rights_holder",
        permission_reference="contract-2026-001",
    )
    manager = JobManager(
        converter=lambda *_: {"outputs": [], "report": {}, "warnings": []},
        run_inline=True,
    )
    job = manager.create_pending_job(
        ConversionRequest(
            source_paths=[Path("/media/OLD_DISC/clip.vob")],
            output_dir=tmp_path,
            lane=RestoreLane.PRO,
            export_profile=ExportProfile.PRORES_422_HQ,
            rights_declaration=rights,
        )
    )
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/reports/pro",
        json={
            "job_id": job.job_id,
            "json_path": str(tmp_path / "pro-audit.json"),
        },
    )

    assert response.status_code == 409


def test_pro_report_endpoint_rejects_non_pro_job(tmp_path: Path) -> None:
    output = tmp_path / "clip.mp4"
    manager = JobManager(
        converter=lambda *_: {
            "outputs": [output],
            "report": {"clips": 1, "timeline": {"ranges": []}},
            "warnings": [],
        },
        run_inline=True,
    )
    job = manager.start_conversion(
        ConversionRequest(
            source_paths=[Path("/media/OLD_DISC/clip.vob")],
            output_dir=tmp_path,
        )
    )
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/reports/pro",
        json={
            "job_id": job.job_id,
            "json_path": str(tmp_path / "pro-audit.json"),
        },
    )

    assert response.status_code == 403
    assert "pro restore job" in response.text.lower()


def test_pro_report_endpoint_rejects_pro_job_without_rights_declaration(
    tmp_path: Path,
) -> None:
    output = tmp_path / "clip.mov"
    manager = JobManager(
        converter=lambda *_: {
            "outputs": [output],
            "report": {"clips": 1, "timeline": {"ranges": []}},
            "warnings": [],
        },
        run_inline=True,
    )
    job = manager.start_conversion(
        ConversionRequest(
            source_paths=[Path("/media/OLD_DISC/clip.vob")],
            output_dir=tmp_path,
            lane=RestoreLane.PRO,
            export_profile=ExportProfile.PRORES_422_HQ,
        )
    )
    client = TestClient(create_app(job_manager=manager))

    response = client.post(
        "/reports/pro",
        json={
            "job_id": job.job_id,
            "json_path": str(tmp_path / "pro-audit.json"),
        },
    )

    assert response.status_code == 403
    assert "rights declaration" in response.text.lower()
