from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderHealthStatus
from rawcd.providers.cloud import CloudApiProvider


def test_cloud_api_provider_requires_configured_api_key_and_base_url() -> None:
    provider = CloudApiProvider(api_key=None, base_url=None)

    health = provider.health_check()

    assert provider.id == "cloud-api"
    assert provider.kind is ProviderKind.CLOUD
    assert health.status is ProviderHealthStatus.LICENSE_REQUIRED
    assert "API key" in health.message


def test_cloud_api_provider_exposes_configured_capability_options() -> None:
    provider = CloudApiProvider(
        api_key="secret",
        base_url="https://provider.example",
        capabilities=(ProviderCapability.INPAINTING, ProviderCapability.UPSCALE),
    )

    assert provider.info().to_dict() == {
        "id": "cloud-api",
        "label": "Cloud/API Provider",
        "kind": "cloud",
        "capabilities": ["inpainting", "upscale"],
    }
    assert provider.health_check().to_dict() == {
        "status": "degraded",
        "message": (
            "Cloud/API provider credentials are configured locally, "
            "but authentication has not been verified."
        ),
        "details": {
            "base_url": "https://provider.example",
            "authentication": "not_verified",
        },
    }
    assert provider.estimate(ProviderCapability.UPSCALE).to_dict() == {
        "capability": "upscale",
        "cost": "paid",
        "execution": "cloud_api",
        "speed": "unknown",
        "notes": ["Requires user-provided API credentials and provider terms."],
    }
