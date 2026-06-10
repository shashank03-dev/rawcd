from datetime import datetime, timezone
from pathlib import Path

from rawcd.models import (
    ProProfile,
    ProviderCapability,
    ProviderKind,
    ProVerificationStatus,
)
from rawcd.settings import (
    ProProfileSettingsStore,
    ProviderSettings,
    ProviderRegistry,
    ProviderSettingsStore,
    default_settings_path,
    pro_projects_enabled,
    redact_provider_settings,
)
from rawcd.providers.base import ProviderEstimate, ProviderHealth, ProviderInfo
from rawcd.providers.ollama import OllamaProvider
from rawcd.repair_pipeline import RepairDecisionEngine, RepairGap


def test_default_settings_path_uses_xdg_config_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    assert default_settings_path() == tmp_path / "config" / "rawcd" / "providers.json"


def test_provider_settings_store_persists_provider_configuration(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "rawcd" / "providers.json")

    configured = store.configure(
        "topaz-api",
        {
            "enabled": True,
            "api_key": "topaz-secret",
            "base_url": "https://api.topazlabs.com",
            "extra": {"quality": "high"},
        },
    )
    reloaded = ProviderSettingsStore(tmp_path / "rawcd" / "providers.json")

    assert configured == ProviderSettings(
        provider_id="topaz-api",
        enabled=True,
        api_key="topaz-secret",
        base_url="https://api.topazlabs.com",
        executable_path=None,
        extra={"quality": "high"},
    )
    assert reloaded.get("topaz-api") == configured
    assert oct((tmp_path / "rawcd" / "providers.json").stat().st_mode & 0o777) == "0o600"


def test_pro_profile_settings_store_persists_local_profile_and_preserves_providers(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "rawcd" / "providers.json"
    provider_store = ProviderSettingsStore(settings_path)
    provider_store.configure("topaz-api", {"enabled": True})
    approved_at = datetime(2026, 6, 7, 12, 30, tzinfo=timezone.utc)
    profile = ProProfile(
        name="Asha Rao",
        organization="Archive House",
        email="asha@example.test",
        country="IN",
        intended_use="Commercial film restoration",
        verification_status=ProVerificationStatus.APPROVED,
        approved_at=approved_at,
        server_verification_id="future-server-check-123",
    )

    saved = ProProfileSettingsStore(settings_path).save(profile)

    assert saved == profile
    assert ProProfileSettingsStore(settings_path).get() == profile
    assert ProviderSettingsStore(settings_path).get("topaz-api").enabled is True
    assert oct(settings_path.stat().st_mode & 0o777) == "0o600"


def test_provider_updates_preserve_stored_pro_profile(tmp_path: Path) -> None:
    settings_path = tmp_path / "rawcd" / "providers.json"
    profile = ProProfile(
        name="Asha Rao",
        organization="Archive House",
        email="asha@example.test",
        country="IN",
        intended_use="Commercial film restoration",
        verification_status=ProVerificationStatus.PENDING,
    )
    ProProfileSettingsStore(settings_path).save(profile)

    ProviderSettingsStore(settings_path).configure("cloud-api", {"enabled": True})

    assert ProProfileSettingsStore(settings_path).get() == profile


def test_only_approved_pro_profiles_can_enable_pro_projects() -> None:
    assert pro_projects_enabled(None) is False
    for status in (
        ProVerificationStatus.NOT_REQUESTED,
        ProVerificationStatus.PENDING,
        ProVerificationStatus.REJECTED,
    ):
        profile = ProProfile(
            name="Asha Rao",
            organization="Archive House",
            email="asha@example.test",
            country="IN",
            intended_use="Commercial film restoration",
            verification_status=status,
        )
        assert pro_projects_enabled(profile) is False

    approved = ProProfile(
        name="Asha Rao",
        organization="Archive House",
        email="asha@example.test",
        country="IN",
        intended_use="Commercial film restoration",
        verification_status=ProVerificationStatus.APPROVED,
    )

    assert pro_projects_enabled(approved) is True


def test_provider_settings_redacts_api_keys_in_serialized_responses() -> None:
    settings = ProviderSettings(
        provider_id="cloud-provider",
        enabled=True,
        api_key="raw-secret",
        base_url="https://example.test",
    )

    assert redact_provider_settings(settings) == {
        "provider_id": "cloud-provider",
        "enabled": True,
        "api_key_configured": True,
        "api_key": None,
        "base_url": "https://example.test",
        "executable_path": None,
        "extra": {},
    }


def test_provider_settings_redaction_does_not_claim_empty_api_key() -> None:
    settings = ProviderSettings(provider_id="local")

    assert redact_provider_settings(settings)["api_key_configured"] is False


def test_provider_settings_redacts_secrets_nested_in_extra() -> None:
    settings = ProviderSettings(
        provider_id="cloud",
        extra={
            "quality": "high",
            "api_key": "nested-secret",
            "auth": {"refresh_token": "token-secret", "region": "local"},
        },
    )

    assert redact_provider_settings(settings)["extra"] == {
        "quality": "high",
        "api_key": None,
        "auth": {"refresh_token": None, "region": "local"},
    }


class RepairCapableProvider:
    id = "repair-provider"
    label = "Repair Provider"
    kind = ProviderKind.CLOUD
    capabilities = (ProviderCapability.INTERPOLATION, ProviderCapability.DENOISE)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth.available("ready")

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        return ProviderEstimate(
            capability=capability,
            cost="paid",
            execution="cloud_api",
            speed="unknown",
        )


def test_provider_registry_exposes_enabled_repair_capable_providers(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "providers.json")
    store.configure("repair-provider", {"enabled": True})
    registry = ProviderRegistry(settings_store=store, providers=(RepairCapableProvider(),))

    assert registry.repair_providers()[0].id == "repair-provider"
    assert registry.repair_providers()[0].capabilities == frozenset(
        {ProviderCapability.INTERPOLATION}
    )


def test_captured_repair_providers_reflect_later_configuration(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "providers.json")
    registry = ProviderRegistry(settings_store=store, providers=(RepairCapableProvider(),))
    repair_providers = registry.repair_providers()
    engine = RepairDecisionEngine()
    gap = RepairGap(start_seconds=1.0, end_seconds=1.1, missing_frames=1)

    assert engine.decide(gap, repair_providers).provider_id is None

    registry.configure_provider("repair-provider", {"enabled": True})

    assert engine.decide(gap, repair_providers).provider_id == "repair-provider"


class FakeOllamaHttpClient:
    def get_json(self, url: str) -> dict[str, object]:
        assert url == "http://127.0.0.1:11434/api/tags"
        return {
            "models": [
                {
                    "name": "rawcd-inpainter:latest",
                    "capabilities": ["inpainting"],
                }
            ]
        }


def test_enabled_ollama_participates_in_repair_routing_after_health_check(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "providers.json")
    store.configure("ollama", {"enabled": True})
    registry = ProviderRegistry(
        settings_store=store,
        providers=(OllamaProvider(http_client=FakeOllamaHttpClient()),),
    )

    registry.test_provider("ollama")

    decision = RepairDecisionEngine().decide(
        RepairGap(start_seconds=1.0, end_seconds=1.8, missing_frames=10),
        registry.repair_providers(),
    )
    assert decision.provider_id == "ollama"
