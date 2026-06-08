from pathlib import Path

from rawcd.settings import (
    ProviderSettings,
    ProviderRegistry,
    ProviderSettingsStore,
    default_settings_path,
    redact_provider_settings,
)
from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderEstimate, ProviderHealth, ProviderInfo


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
