from __future__ import annotations

from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderEstimate, ProviderHealth, ProviderInfo


DEFAULT_CLOUD_CAPABILITIES = (
    ProviderCapability.INTERPOLATION,
    ProviderCapability.INPAINTING,
    ProviderCapability.DENOISE,
    ProviderCapability.DEINTERLACE,
    ProviderCapability.UPSCALE,
    ProviderCapability.STABILIZATION,
    ProviderCapability.COLOR_CORRECTION,
    ProviderCapability.ARTIFACT_CLEANUP,
    ProviderCapability.PREVIEW_RENDER,
)


class CloudApiProvider:
    id = "cloud-api"
    label = "Cloud/API Provider"
    kind = ProviderKind.CLOUD

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        capabilities: tuple[ProviderCapability, ...] = DEFAULT_CLOUD_CAPABILITIES,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self.capabilities = tuple(ProviderCapability(capability) for capability in capabilities)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            kind=self.kind,
            capabilities=self.capabilities,
        )

    def health_check(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth.license_required(
                "Cloud/API provider API key is not configured.",
            )
        if not self._base_url:
            return ProviderHealth.unavailable(
                "Cloud/API provider base URL is not configured.",
            )
        return ProviderHealth.available(
            "Cloud/API provider credentials are configured.",
            details={"base_url": self._base_url},
        )

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        capability = ProviderCapability(capability)
        if capability not in self.capabilities:
            raise ValueError(f"{capability.value} is not supported by {self.id}")
        return ProviderEstimate(
            capability=capability,
            cost="paid",
            execution="cloud_api",
            speed="unknown",
            notes=("Requires user-provided API credentials and provider terms.",),
        )


__all__ = ["CloudApiProvider", "DEFAULT_CLOUD_CAPABILITIES"]
