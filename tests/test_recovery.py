from pathlib import Path
from subprocess import CompletedProcess

import pytest

from rawcd.models import RecoveryMode, RecoverySeverity
from rawcd.recovery import DdrescueAdapter, RecoveryPlanner


def test_quick_recovery_plan_uses_direct_source_without_work_dir(
    tmp_path: Path,
) -> None:
    input_path = Path("/media/DISC/clip.vob")

    result = RecoveryPlanner().plan(input_path, tmp_path, RecoveryMode.QUICK)

    assert result.mode is RecoveryMode.QUICK
    assert result.source_path == input_path
    assert result.work_dir is None
    assert result.image_path is None
    assert result.map_path is None
    assert result.retry_count == 0
    assert result.warnings == ()
    assert result.severity is RecoverySeverity.INFO


def test_maximum_recovery_plan_creates_deterministic_work_source(
    tmp_path: Path,
) -> None:
    input_path = Path("/media/OLD DISC")

    result = RecoveryPlanner().plan(input_path, tmp_path, RecoveryMode.MAXIMUM)

    assert result.mode is RecoveryMode.MAXIMUM
    assert result.work_dir is not None
    assert result.work_dir.parent == tmp_path / ".rawcd-work"
    assert result.work_dir.name.startswith("OLD-DISC-")
    assert result.image_path == result.work_dir / "source.img"
    assert result.map_path == result.work_dir / "source.map"
    assert result.source_path == input_path
    assert result.warnings == (
        "Maximum recovery requested, but no rescue adapter is configured; using the direct source.",
    )
    assert result.severity is RecoverySeverity.WARNING
    assert result.work_dir.exists()


def test_ddrescue_adapter_builds_command_without_running_real_tool(
    tmp_path: Path,
) -> None:
    adapter = DdrescueAdapter()

    command = adapter.build_command(
        Path("/dev/sr0"),
        tmp_path / "source.img",
        tmp_path / "source.map",
        retry_count=3,
    )

    assert command == [
        "ddrescue",
        "--force",
        "--retry-passes=3",
        "/dev/sr0",
        str(tmp_path / "source.img"),
        str(tmp_path / "source.map"),
    ]


def test_missing_rescue_tool_falls_back_to_direct_source_with_warning(
    tmp_path: Path,
) -> None:
    class MissingRunner:
        def run(self, command: list[str]) -> CompletedProcess[str]:
            raise FileNotFoundError(command[0])

    result = RecoveryPlanner(
        rescue_adapter=DdrescueAdapter(runner=MissingRunner()),
        retry_count=2,
    ).plan(Path("/dev/sr0"), tmp_path, RecoveryMode.MAXIMUM)

    assert result.source_path == Path("/dev/sr0")
    assert result.work_dir is not None
    assert result.work_dir.name.startswith("sr0-")
    assert result.image_path == result.work_dir / "source.img"
    assert result.map_path == result.work_dir / "source.map"
    assert result.retry_count == 2
    assert result.warnings == (
        "ddrescue is not installed; using the direct source instead of a recovered image.",
    )
    assert result.severity is RecoverySeverity.WARNING
    assert result.attempts[0].command == (
        "ddrescue",
        "--force",
        "--retry-passes=2",
        "/dev/sr0",
        str(result.image_path),
        str(result.map_path),
    )


def test_successful_rescue_tool_result_uses_recovered_image(
    tmp_path: Path,
) -> None:
    class SuccessfulRunner:
        def run(self, command: list[str]) -> CompletedProcess[str]:
            return CompletedProcess(command, 0, stdout="copied", stderr="rescued")

    result = RecoveryPlanner(
        rescue_adapter=DdrescueAdapter(runner=SuccessfulRunner()),
        retry_count=1,
    ).plan(Path("/dev/sr0"), tmp_path, RecoveryMode.MAXIMUM)

    assert result.source_path == result.image_path
    assert result.retry_count == 1
    assert result.warnings == ()
    assert result.severity is RecoverySeverity.INFO
    assert result.attempts[0].returncode == 0
    assert result.attempts[0].stdout == "copied"
    assert result.attempts[0].stderr == "rescued"


def test_failed_rescue_tool_result_falls_back_to_direct_source(
    tmp_path: Path,
) -> None:
    class FailedRunner:
        def run(self, command: list[str]) -> CompletedProcess[str]:
            return CompletedProcess(command, 1, stdout="", stderr="read error")

    result = RecoveryPlanner(
        rescue_adapter=DdrescueAdapter(runner=FailedRunner()),
    ).plan(Path("/dev/sr0"), tmp_path, RecoveryMode.MAXIMUM)

    assert result.source_path == Path("/dev/sr0")
    assert result.severity is RecoverySeverity.ERROR
    assert result.warnings == (
        "Maximum recovery failed; using the direct source instead of a recovered image.",
    )
    assert result.attempts[0].returncode == 1
    assert result.attempts[0].stderr == "read error"


def test_negative_retry_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="retry_count"):
        RecoveryPlanner(retry_count=-1)


def test_unsafe_source_name_uses_deterministic_hash_work_dir(
    tmp_path: Path,
) -> None:
    result = RecoveryPlanner().plan(
        Path("/media/!!!"),
        tmp_path,
        RecoveryMode.MAXIMUM,
    )

    assert result.work_dir is not None
    assert result.work_dir.parent == tmp_path / ".rawcd-work"
    assert result.work_dir.name.startswith("source-")
    assert result.work_dir.name != "source"


def test_same_basename_sources_get_distinct_work_directories(
    tmp_path: Path,
) -> None:
    planner = RecoveryPlanner()

    first = planner.plan(
        Path("/media/disc-a/clip.vob"),
        tmp_path,
        RecoveryMode.MAXIMUM,
    )
    second = planner.plan(
        Path("/media/disc-b/clip.vob"),
        tmp_path,
        RecoveryMode.MAXIMUM,
    )

    assert first.work_dir != second.work_dir
    assert first.image_path != second.image_path


def test_recovery_mode_accepts_stable_api_string_values(tmp_path: Path) -> None:
    result = RecoveryPlanner().plan(
        Path("/media/DISC/clip.vob"),
        tmp_path,
        "quick",  # type: ignore[arg-type]
    )

    assert result.mode is RecoveryMode.QUICK
    assert result.work_dir is None
