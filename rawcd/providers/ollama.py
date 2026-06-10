from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from rawcd.models import ProviderCapability
from rawcd.models import ProviderKind
from rawcd.providers.base import ProviderEstimate
from rawcd.providers.base import ProviderHealth
from rawcd.providers.base import ProviderInfo


class HttpClient(Protocol):
    def get_json(self, url: str) -> dict[str, object]:
        ...


class UrlopenHttpClient:
    def get_json(self, url: str) -> dict[str, object]:
        try:
            with urlopen(url, timeout=2.0) as response:  # nosec B310
                payload = response.read().decode("utf-8")
        except URLError as exc:
            raise ConnectionError(str(exc)) from exc
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Ollama API response must be a JSON object")
        return data


@dataclass(frozen=True)
class OllamaModelInfo:
    name: str
    metadata: dict[str, object]
    capabilities: tuple[ProviderCapability, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "capabilities": [capability.value for capability in self.capabilities],
            "metadata": dict(self.metadata),
        }


class OllamaProvider:
    id = "ollama"
    label = "Ollama"
    kind = ProviderKind.OLLAMA

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        http_client: HttpClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client or UrlopenHttpClient()
        self._cached_models: tuple[OllamaModelInfo, ...] | None = None

    @property
    def capabilities(self) -> tuple[ProviderCapability, ...]:
        if self._cached_models is None:
            return ()
        return _unique_capabilities(
            capability
            for model in self._cached_models
            for capability in model.capabilities
        )

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        try:
            models = self.list_models()
        except Exception as exc:
            return ProviderHealth.unavailable(
                f"Ollama API is unavailable: {exc}",
            )

        return ProviderHealth.available(
            "Ollama API is available.",
            details={"models": str(len(models))},
        )

    def list_models(self) -> tuple[OllamaModelInfo, ...]:
        payload = self._fetch_tags()
        raw_models = payload.get("models", [])
        if not isinstance(raw_models, list):
            self._cached_models = ()
            return self._cached_models

        models: list[OllamaModelInfo] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, dict):
                continue
            name = str(raw_model.get("name") or raw_model.get("model") or "")
            if not name:
                continue
            metadata = dict(raw_model)
            capabilities = infer_model_capabilities(metadata)
            models.append(
                OllamaModelInfo(
                    name=name,
                    metadata=metadata,
                    capabilities=capabilities,
                )
            )

        self._cached_models = tuple(models)
        return self._cached_models

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        capability = ProviderCapability(capability)
        if self._cached_models is None:
            self.list_models()

        supporting_models = [
            model.name
            for model in self._cached_models or ()
            if capability in model.capabilities
        ]
        if not supporting_models:
            raise ValueError(f"{capability.value} is not supported by Ollama models")

        return ProviderEstimate(
            capability=capability,
            cost="free",
            execution="local_http",
            speed="unknown",
            notes=(f"models: {', '.join(supporting_models)}",),
        )

    def _fetch_tags(self) -> dict[str, object]:
        _validate_loopback_base_url(self.base_url)
        return self._http_client.get_json(f"{self.base_url}/api/tags")


def infer_model_capabilities(
    metadata: dict[str, object],
) -> tuple[ProviderCapability, ...]:
    values: list[object] = []
    _extend_declared_capabilities(values, metadata)

    details = metadata.get("details")
    if isinstance(details, dict):
        _extend_declared_capabilities(values, details)

    rawcd = metadata.get("rawcd")
    if isinstance(rawcd, dict):
        _extend_declared_capabilities(values, rawcd)

    return _unique_capabilities(_capability_from_value(value) for value in values)


def _extend_declared_capabilities(
    values: list[object],
    metadata: dict[str, object],
) -> None:
    for key in ("rawcd_capabilities", "provider_capabilities", "capabilities"):
        raw_value = metadata.get(key)
        if isinstance(raw_value, list | tuple):
            values.extend(raw_value)


def _capability_from_value(value: object) -> ProviderCapability | None:
    if isinstance(value, ProviderCapability):
        return value
    if not isinstance(value, str):
        return None
    try:
        return ProviderCapability(value)
    except ValueError:
        return None


def _unique_capabilities(
    capabilities: Any,
) -> tuple[ProviderCapability, ...]:
    result: list[ProviderCapability] = []
    for capability in capabilities:
        if capability is None:
            continue
        if capability not in result:
            result.append(capability)
    return tuple(result)


def _validate_loopback_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Ollama base URL must use http or https.")
    hostname = parsed.hostname
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Ollama base URL must point to a loopback host.")


__all__ = [
    "HttpClient",
    "OllamaModelInfo",
    "OllamaProvider",
    "UrlopenHttpClient",
    "infer_model_capabilities",
]
