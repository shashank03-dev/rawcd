from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from rawcd.models import ProviderKind
from rawcd.providers.base import EnhancementProvider, ProviderHealth
from rawcd.providers.cloud import CloudApiProvider
from rawcd.providers.local import LocalFfmpegProvider
from rawcd.providers.ollama import OllamaProvider
from rawcd.providers.topaz import TopazApiProvider, TopazCliProvider
from rawcd.repair_pipeline import RepairProvider


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
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as settings_file:
            payload = json.load(settings_file)
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "providers": {
                provider_id: asdict(provider_settings)
                for provider_id, provider_settings in sorted(settings.items())
            }
        }
        temp_path = self.path.with_name(f".{self.path.name}.tmp")
        fd = os.open(
            temp_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as settings_file:
            json.dump(payload, settings_file, indent=2, sort_keys=True)
            settings_file.write("\n")
        os.replace(temp_path, self.path)
        os.chmod(self.path, 0o600)


class ProviderRegistry:
    def __init__(
        self,
        settings_store: ProviderSettingsStore | None = None,
        providers: Iterable[EnhancementProvider] | None = None,
    ) -> None:
        self.settings_store = settings_store or ProviderSettingsStore()
        self._providers = (
            {provider.id: provider for provider in providers}
            if providers is not None
            else None
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
        return self._serialize_provider(self._require_provider(provider_id))

    def repair_providers(self) -> tuple[RepairProvider, ...]:
        repair_capabilities = {
            "interpolation",
            "inpainting",
        }
        providers: list[RepairProvider] = []
        for provider in self._provider_map().values():
            settings = self.settings_store.get(provider.id)
            if not settings.enabled:
                continue
            capabilities = frozenset(
                capability
                for capability in provider.capabilities
                if capability.value in repair_capabilities
            )
            if capabilities:
                providers.append(RepairProvider(id=provider.id, capabilities=capabilities))
        return tuple(providers)

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
        if self._providers is not None:
            return self._providers
        return _default_provider_map(self.settings_store)


def default_settings_path() -> Path:
    config_root = os.environ.get("XDG_CONFIG_HOME")
    if config_root:
        root = Path(config_root)
    else:
        root = Path.home() / ".config"
    return root / "rawcd" / "providers.json"


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

    providers: tuple[EnhancementProvider, ...] = (
        LocalFfmpegProvider(),
        OllamaProvider(base_url=ollama_settings.base_url or "http://127.0.0.1:11434"),
        TopazCliProvider(cli_path=topaz_cli_path),
        TopazApiProvider(api_key=topaz_api_settings.api_key),
        CloudApiProvider(
            api_key=cloud_api_settings.api_key,
            base_url=cloud_api_settings.base_url,
        ),
    )
    return {provider.id: provider for provider in providers}


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
    "ProviderRegistry",
    "ProviderSettings",
    "ProviderSettingsStore",
    "default_settings_path",
    "redact_provider_settings",
]
