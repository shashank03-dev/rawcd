from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import (
    EnhancementProvider,
    ProviderEstimate,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderInfo,
)


class DummyProvider:
    id = "dummy"
    label = "Dummy Provider"
    kind = ProviderKind.OPEN_LOCAL
    capabilities = (ProviderCapability.DENOISE,)

    def health_check(self) -> ProviderHealth:
        return ProviderHealth.available("ready")

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        return ProviderEstimate(
            capability=capability,
            cost="free",
            execution="local",
            speed="unknown",
            notes=("test provider",),
        )


def test_provider_info_serializes_capabilities_as_api_strings() -> None:
    info = ProviderInfo(
        id="local-ffmpeg",
        label="Local FFmpeg",
        kind=ProviderKind.OPEN_LOCAL,
        capabilities=(
            ProviderCapability.DEINTERLACE,
            ProviderCapability.PREVIEW_RENDER,
        ),
    )

    assert info.to_dict() == {
        "id": "local-ffmpeg",
        "label": "Local FFmpeg",
        "kind": "open_local",
        "capabilities": ["deinterlace", "preview_render"],
    }


def test_provider_health_states_are_stable_serializable_values() -> None:
    assert ProviderHealth.available("ready").to_dict() == {
        "status": "available",
        "message": "ready",
        "details": {},
    }
    assert ProviderHealth.unavailable("missing").status is (
        ProviderHealthStatus.UNAVAILABLE
    )
    assert ProviderHealth.license_required("sign in").to_dict() == {
        "status": "license_required",
        "message": "sign in",
        "details": {},
    }
    assert ProviderHealth.degraded("partial", details={"tool": "ffmpeg"}).to_dict() == {
        "status": "degraded",
        "message": "partial",
        "details": {"tool": "ffmpeg"},
    }


def test_provider_estimate_serializes_capability_and_execution_context() -> None:
    estimate = ProviderEstimate(
        capability=ProviderCapability.DENOISE,
        cost="free",
        execution="local",
        speed="unknown",
        notes=("CPU bound",),
    )

    assert estimate.to_dict() == {
        "capability": "denoise",
        "cost": "free",
        "execution": "local",
        "speed": "unknown",
        "notes": ["CPU bound"],
    }


def test_enhancement_provider_protocol_requires_adapter_surface() -> None:
    provider = DummyProvider()

    assert isinstance(provider, EnhancementProvider)
    assert provider.health_check().status is ProviderHealthStatus.AVAILABLE
    assert provider.estimate(ProviderCapability.DENOISE).to_dict() == {
        "capability": "denoise",
        "cost": "free",
        "execution": "local",
        "speed": "unknown",
        "notes": ["test provider"],
    }
