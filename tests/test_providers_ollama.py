from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderHealthStatus
from rawcd.providers.ollama import OllamaProvider


class FakeHttpClient:
    def __init__(self, payloads: dict[str, object]) -> None:
        self.payloads = payloads
        self.urls: list[str] = []

    def get_json(self, url: str) -> dict[str, object]:
        self.urls.append(url)
        payload = self.payloads[url]
        if isinstance(payload, Exception):
            raise payload
        return payload  # type: ignore[return-value]


def test_ollama_provider_defaults_to_local_base_url() -> None:
    client = FakeHttpClient(
        {"http://127.0.0.1:11434/api/tags": {"models": []}},
    )
    provider = OllamaProvider(http_client=client)

    health = provider.health_check()

    assert provider.base_url == "http://127.0.0.1:11434"
    assert provider.id == "ollama"
    assert provider.kind is ProviderKind.OLLAMA
    assert client.urls == ["http://127.0.0.1:11434/api/tags"]
    assert health.status is ProviderHealthStatus.AVAILABLE
    assert health.details == {"models": "0"}


def test_ollama_health_is_unavailable_when_api_request_fails() -> None:
    provider = OllamaProvider(
        http_client=FakeHttpClient(
            {"http://127.0.0.1:11434/api/tags": ConnectionError("offline")},
        ),
    )

    health = provider.health_check()

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert "offline" in health.message


def test_ollama_health_populates_capabilities_from_model_metadata() -> None:
    provider = OllamaProvider(
        http_client=FakeHttpClient(
            {
                "http://127.0.0.1:11434/api/tags": {
                    "models": [
                        {
                            "name": "rawcd-repair:latest",
                            "rawcd_capabilities": ["interpolation", "inpainting"],
                        },
                    ],
                },
            },
        ),
    )

    health = provider.health_check()

    assert health.status is ProviderHealthStatus.AVAILABLE
    assert health.details == {"models": "1"}
    assert provider.capabilities == (
        ProviderCapability.INTERPOLATION,
        ProviderCapability.INPAINTING,
    )


def test_ollama_rejects_non_loopback_base_url_before_request() -> None:
    client = FakeHttpClient({})
    provider = OllamaProvider(base_url="http://169.254.169.254", http_client=client)

    health = provider.health_check()

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert "loopback" in health.message
    assert client.urls == []


def test_ollama_lists_models_and_infers_only_declared_capabilities() -> None:
    client = FakeHttpClient(
        {
            "http://localhost:11434/api/tags": {
                "models": [
                    {
                        "name": "rawcd-vision:latest",
                        "details": {
                            "rawcd_capabilities": [
                                "inpainting",
                                "artifact_cleanup",
                                "preview_render",
                            ],
                        },
                    },
                    {
                        "name": "llama3:latest",
                        "details": {"family": "llama"},
                    },
                ],
            },
        },
    )
    provider = OllamaProvider(base_url="http://localhost:11434/", http_client=client)

    models = provider.list_models()

    assert [model.name for model in models] == [
        "rawcd-vision:latest",
        "llama3:latest",
    ]
    assert models[0].capabilities == (
        ProviderCapability.INPAINTING,
        ProviderCapability.ARTIFACT_CLEANUP,
        ProviderCapability.PREVIEW_RENDER,
    )
    assert models[1].capabilities == ()
    assert provider.capabilities == (
        ProviderCapability.INPAINTING,
        ProviderCapability.ARTIFACT_CLEANUP,
        ProviderCapability.PREVIEW_RENDER,
    )


def test_ollama_does_not_assume_generic_models_can_edit_frames() -> None:
    provider = OllamaProvider(
        http_client=FakeHttpClient(
            {
                "http://127.0.0.1:11434/api/tags": {
                    "models": [{"name": "mistral:latest", "details": {}}],
                },
            },
        ),
    )

    provider.list_models()

    assert provider.capabilities == ()


def test_ollama_estimate_names_models_that_support_capability() -> None:
    provider = OllamaProvider(
        http_client=FakeHttpClient(
            {
                "http://127.0.0.1:11434/api/tags": {
                    "models": [
                        {
                            "name": "rawcd-cleanup:latest",
                            "capabilities": ["denoise"],
                        },
                    ],
                },
            },
        ),
    )
    provider.list_models()

    estimate = provider.estimate(ProviderCapability.DENOISE)

    assert estimate.to_dict() == {
        "capability": "denoise",
        "cost": "free",
        "execution": "local_http",
        "speed": "unknown",
        "notes": ["models: rawcd-cleanup:latest"],
    }
