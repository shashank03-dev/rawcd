from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

from rawcd.models import ProviderCapability, ProviderKind
from rawcd.providers.base import ProviderHealthStatus
from rawcd.providers.topaz import TopazApiProvider, TopazCliProvider


class FakeExists:
    def __init__(self, paths: set[Path]) -> None:
        self.paths = paths

    def __call__(self, path: Path) -> bool:
        return path in self.paths


class FakeCommandRunner:
    def __init__(self, result: CompletedProcess[str]) -> None:
        self.result = result
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return self.result


class TimeoutCommandRunner:
    def run(self, command: list[str]) -> CompletedProcess[str]:
        raise TimeoutExpired(command, timeout=10)


def test_topaz_cli_uses_configured_path_before_known_paths() -> None:
    configured = Path("/custom/topaz-video-ai")
    known = Path("/usr/local/bin/topaz-video-ai")
    provider = TopazCliProvider(
        cli_path=configured,
        known_paths=(known,),
        exists=FakeExists({configured, known}),
    )

    assert provider.detect_cli_path() == configured


def test_topaz_cli_detects_known_install_path_without_configured_path() -> None:
    known = Path("/opt/Topaz Video AI/topaz-video-ai")
    provider = TopazCliProvider(
        known_paths=(known,),
        exists=FakeExists({known}),
    )

    assert provider.detect_cli_path() == known


def test_topaz_cli_reports_license_required_when_not_installed() -> None:
    provider = TopazCliProvider(
        known_paths=(Path("/missing/topaz-video-ai"),),
        exists=FakeExists(set()),
    )

    health = provider.health_check()

    assert health.status is ProviderHealthStatus.LICENSE_REQUIRED
    assert "not installed" in health.message
    assert provider.capabilities == ()


def test_topaz_cli_reports_available_and_exposes_supported_capabilities() -> None:
    cli_path = Path("/usr/local/bin/topaz-video-ai")
    runner = FakeCommandRunner(
        CompletedProcess(
            [str(cli_path), "--version"],
            0,
            stdout="Topaz Video AI CLI 5.0",
            stderr="",
        ),
    )
    provider = TopazCliProvider(
        cli_path=cli_path,
        exists=FakeExists({cli_path}),
        runner=runner,
    )

    health = provider.health_check()

    assert runner.commands == [[str(cli_path), "--version"]]
    assert health.status is ProviderHealthStatus.AVAILABLE
    assert provider.capabilities == (
        ProviderCapability.INTERPOLATION,
        ProviderCapability.UPSCALE,
        ProviderCapability.STABILIZATION,
        ProviderCapability.ARTIFACT_CLEANUP,
        ProviderCapability.DENOISE,
        ProviderCapability.DEINTERLACE,
    )


def test_topaz_cli_reports_license_required_when_not_authenticated() -> None:
    cli_path = Path("/usr/local/bin/topaz-video-ai")
    provider = TopazCliProvider(
        cli_path=cli_path,
        exists=FakeExists({cli_path}),
        runner=FakeCommandRunner(
            CompletedProcess(
                [str(cli_path), "--version"],
                1,
                stdout="",
                stderr="not authenticated",
            ),
        ),
    )

    health = provider.health_check()

    assert health.status is ProviderHealthStatus.LICENSE_REQUIRED
    assert "authenticate" in health.message


def test_topaz_cli_reports_unavailable_when_health_check_times_out() -> None:
    cli_path = Path("/usr/local/bin/topaz-video-ai")
    provider = TopazCliProvider(
        cli_path=cli_path,
        exists=FakeExists({cli_path}),
        runner=TimeoutCommandRunner(),
    )

    health = provider.health_check()

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert "timed out" in health.message


def test_topaz_cli_builds_capability_command_without_running_cli() -> None:
    cli_path = Path("/usr/local/bin/topaz-video-ai")
    provider = TopazCliProvider(
        cli_path=cli_path,
        exists=FakeExists({cli_path}),
    )

    command = provider.build_enhancement_command(
        ProviderCapability.UPSCALE,
        Path("/in.mov"),
        Path("/out.mov"),
    )

    assert command == [
        str(cli_path),
        "--input",
        "/in.mov",
        "--output",
        "/out.mov",
        "--upscale",
    ]


def test_topaz_api_provider_is_separate_api_key_mode() -> None:
    provider = TopazApiProvider(api_key="secret")

    assert provider.id == "topaz-api"
    assert provider.kind is ProviderKind.TOPAZ
    assert provider.health_check().status is ProviderHealthStatus.AVAILABLE
    assert provider.estimate(ProviderCapability.DENOISE).to_dict() == {
        "capability": "denoise",
        "cost": "paid",
        "execution": "cloud_api",
        "speed": "unknown",
        "notes": ["Requires user-provided Topaz API credentials."],
    }


def test_topaz_api_provider_requires_user_api_key() -> None:
    health = TopazApiProvider(api_key=None).health_check()

    assert health.status is ProviderHealthStatus.LICENSE_REQUIRED
    assert "API key" in health.message
