from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from rawcd.models import (
    ProProfile,
    ProviderCapability,
    ProviderKind,
    ProVerificationStatus,
)
from rawcd.providers.base import EnhancementProvider, ProviderHealth
from rawcd.providers.cloud import CloudApiProvider
from rawcd.providers.local import LocalFfmpegProvider
from rawcd.providers.ollama import OllamaProvider
from rawcd.providers.topaz import TopazApiProvider, TopazCliProvider
from rawcd.repair_pipeline import RepairProvider

_REPAIR_CAPABILITY_VALUES = frozenset({"interpolation", "inpainting"})


@dataclass(frozen=True)
class ProviderSettings:
    provider_id: str
    enabled: bool = False
    api_key: str | None = None
    base_url: str | None = None
    executable_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def get(self, provider_id: str) -> ProviderSettings:
        return self.all().get(provider_id, ProviderSettings(provider_id=provider_id))

    def all(self) -> dict[str, ProviderSettings]:
        payload = _read_settings_payload(self.path)
        providers = payload.get("providers", {})
        return {
            provider_id: ProviderSettings(
                provider_id=provider_id,
                enabled=bool(data.get("enabled", False)),
                api_key=data.get("api_key"),
                base_url=data.get("base_url"),
                executable_path=data.get("executable_path"),
                extra=dict(data.get("extra", {})),
            )
            for provider_id, data in providers.items()
        }

    def configure(self, provider_id: str, updates: dict[str, Any]) -> ProviderSettings:
        current = self.all()
        previous = current.get(provider_id, ProviderSettings(provider_id=provider_id))
        configured = ProviderSettings(
            provider_id=provider_id,
            enabled=bool(updates.get("enabled", previous.enabled)),
            api_key=updates.get("api_key", previous.api_key),
            base_url=updates.get("base_url", previous.base_url),
            executable_path=updates.get("executable_path", previous.executable_path),
            extra=dict(updates.get("extra", previous.extra)),
        )
        current[provider_id] = configured
        self._write(current)
        return configured

    def _write(self, settings: dict[str, ProviderSettings]) -> None:
        payload = _read_settings_payload(self.path)
        payload = {
            **payload,
            "providers": {
                provider_id: asdict(provider_settings)
                for provider_id, provider_settings in sorted(settings.items())
            },
        }
        _write_settings_payload(self.path, payload)


class ProProfileSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def get(self) -> ProProfile | None:
        payload = _read_settings_payload(self.path)
        profile = payload.get("pro_profile")
        if not isinstance(profile, dict):
            return None
        return _pro_profile_from_settings(profile)

    def save(self, profile: ProProfile) -> ProProfile:
        payload = _read_settings_payload(self.path)
        payload["pro_profile"] = _pro_profile_to_settings(profile)
        _write_settings_payload(self.path, payload)
        return profile

    def can_enable_pro_projects(self) -> bool:
        return pro_projects_enabled(self.get())


class ProviderRegistry:
    def __init__(
        self,
        settings_store: ProviderSettingsStore | None = None,
        providers: Iterable[EnhancementProvider] | None = None,
    ) -> None:
        self.settings_store = settings_store or ProviderSettingsStore()
        self._uses_default_provider_map = providers is None
        self._providers = (
            _default_provider_map(self.settings_store)
            if providers is None
            else {provider.id: provider for provider in providers}
        )

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            self._serialize_provider(provider)
            for provider in self._provider_map().values()
        ]

    def test_provider(self, provider_id: str) -> ProviderHealth:
        return self._require_provider(provider_id).health_check()

    def configure_provider(
        self,
        provider_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_provider(provider_id)
        self.settings_store.configure(provider_id, updates)
        if self._uses_default_provider_map:
            self._providers = _default_provider_map(self.settings_store)
        return self._serialize_provider(self._require_provider(provider_id))

    def repair_providers(self) -> tuple[RepairProvider, ...]:
        return tuple(
            _RegistryRepairProvider(self, provider.id)
            for provider in self._provider_map().values()
        )

    def _serialize_provider(self, provider: EnhancementProvider) -> dict[str, Any]:
        info = (
            provider.info().to_dict()
            if hasattr(provider, "info")
            else {
                "id": provider.id,
                "label": provider.label,
                "kind": ProviderKind(provider.kind).value,
                "capabilities": [
                    capability.value for capability in provider.capabilities
                ],
            }
        )
        info["settings"] = redact_provider_settings(
            self.settings_store.get(provider.id)
        )
        return info

    def _require_provider(self, provider_id: str) -> EnhancementProvider:
        providers = self._provider_map()
        try:
            return providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown provider id: {provider_id}") from exc

    def _provider_map(self) -> dict[str, EnhancementProvider]:
        return self._providers


class _RegistryRepairProvider:
    def __init__(self, registry: ProviderRegistry, provider_id: str) -> None:
        self._registry = registry
        self.id = provider_id

    @property
    def capabilities(self) -> frozenset[ProviderCapability]:
        settings = self._registry.settings_store.get(self.id)
        if not settings.enabled:
            return frozenset()
        provider = self._registry._provider_map().get(self.id)
        if provider is None:
            return frozenset()
        return frozenset(
            capability
            for capability in provider.capabilities
            if capability.value in _REPAIR_CAPABILITY_VALUES
        )


def default_settings_path() -> Path:
    config_root = os.environ.get("XDG_CONFIG_HOME")
    if config_root:
        root = Path(config_root)
    else:
        root = Path.home() / ".config"
    return root / "rawcd" / "providers.json"


def pro_projects_enabled(profile: ProProfile | None) -> bool:
    return (
        profile is not None
        and profile.verification_status is ProVerificationStatus.APPROVED
    )


def _read_settings_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as settings_file:
        payload = json.load(settings_file)
    return payload if isinstance(payload, dict) else {}


def _write_settings_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    fd = os.open(
        temp_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as settings_file:
        json.dump(payload, settings_file, indent=2, sort_keys=True)
        settings_file.write("\n")
    os.replace(temp_path, path)
    os.chmod(path, 0o600)


def _pro_profile_to_settings(profile: ProProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "organization": profile.organization,
        "email": profile.email,
        "country": profile.country,
        "intended_use": profile.intended_use,
        "verification_status": profile.verification_status.value,
        "approved_at": _datetime_to_settings(profile.approved_at),
        "server_verification_id": profile.server_verification_id,
    }


def _pro_profile_from_settings(data: dict[str, Any]) -> ProProfile:
    try:
        status = ProVerificationStatus(
            data.get(
                "verification_status",
                ProVerificationStatus.NOT_REQUESTED.value,
            )
        )
    except ValueError:
        status = ProVerificationStatus.NOT_REQUESTED

    return ProProfile(
        name=str(data.get("name", "")),
        organization=str(data.get("organization", "")),
        email=str(data.get("email", "")),
        country=str(data.get("country", "")),
        intended_use=str(data.get("intended_use", "")),
        verification_status=status,
        approved_at=_datetime_from_settings(data.get("approved_at")),
        server_verification_id=data.get("server_verification_id"),
    )


def _datetime_to_settings(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_settings(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _default_provider_map(
    settings_store: ProviderSettingsStore,
) -> dict[str, EnhancementProvider]:
    ollama_settings = settings_store.get("ollama")
    topaz_cli_settings = settings_store.get("topaz-cli")
    topaz_api_settings = settings_store.get("topaz-api")
    cloud_api_settings = settings_store.get("cloud-api")
    topaz_cli_path = (
        Path(topaz_cli_settings.executable_path)
        if topaz_cli_settings.executable_path
        else None
    )
    topaz_cli_capabilities = _configured_capabilities(
        topaz_cli_settings.extra.get("supported_capabilities")
    )
    cloud_capabilities = _configured_capabilities(
        cloud_api_settings.extra.get("supported_capabilities")
    )
    cloud_kwargs: dict[str, Any] = {}
    if cloud_capabilities is not None:
        cloud_kwargs["capabilities"] = cloud_capabilities

    providers: tuple[EnhancementProvider, ...] = (
        LocalFfmpegProvider(),
        OllamaProvider(base_url=ollama_settings.base_url or "http://127.0.0.1:11434"),
        TopazCliProvider(
            cli_path=topaz_cli_path,
            supported_capabilities=topaz_cli_capabilities,
        ),
        TopazApiProvider(api_key=topaz_api_settings.api_key),
        CloudApiProvider(
            api_key=cloud_api_settings.api_key,
            base_url=cloud_api_settings.base_url,
            **cloud_kwargs,
        ),
    )
    return {provider.id: provider for provider in providers}


def _configured_capabilities(value: Any) -> tuple[ProviderCapability, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list | tuple):
        return ()

    capabilities: list[ProviderCapability] = []
    for item in value:
        try:
            capability = ProviderCapability(item)
        except ValueError:
            continue
        if capability not in capabilities:
            capabilities.append(capability)
    return tuple(capabilities)


def redact_provider_settings(settings: ProviderSettings) -> dict[str, Any]:
    return {
        "provider_id": settings.provider_id,
        "enabled": settings.enabled,
        "api_key_configured": bool(settings.api_key),
        "api_key": None,
        "base_url": settings.base_url,
        "executable_path": settings.executable_path,
        "extra": _redact_secrets(settings.extra),
    }


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: None if _is_secret_key(key) else _redact_secrets(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _is_secret_key(key: object) -> bool:
    lowered = str(key).lower()
    return any(marker in lowered for marker in ("api_key", "secret", "token", "password"))


__all__ = [
    "ProProfileSettingsStore",
    "ProviderRegistry",
    "ProviderSettings",
    "ProviderSettingsStore",
    "default_settings_path",
    "pro_projects_enabled",
    "redact_provider_settings",
]
