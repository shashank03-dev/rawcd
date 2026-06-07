from pathlib import Path

from rawcd.jobs import ConversionRequest
from rawcd.models import RecoveryMode, SourceState
from rawcd.source import create_source_plan


def test_create_source_plan_for_quick_mounted_source() -> None:
    input_path = Path("/media/DISC")

    plan = create_source_plan(input_path, RecoveryMode.QUICK)

    assert plan.input_path == input_path
    assert plan.recovery_mode is RecoveryMode.QUICK
    assert plan.recovery_requested is False
    assert plan.active_path == input_path
    assert plan.source.path == input_path
    assert plan.source.state is SourceState.MOUNTED
    assert plan.source.label == "DISC"


def test_create_source_plan_for_maximum_recovery_source() -> None:
    input_path = Path("/media/OLD_DISC")

    plan = create_source_plan(input_path, RecoveryMode.MAXIMUM)

    assert plan.input_path == input_path
    assert plan.recovery_mode is RecoveryMode.MAXIMUM
    assert plan.recovery_requested is True
    assert plan.active_path == input_path
    assert plan.recovered_image_path is None
    assert plan.source.recovery_mode is RecoveryMode.MAXIMUM


def test_source_plan_can_switch_to_recovered_image_path() -> None:
    plan = create_source_plan(Path("/media/OLD_DISC"), RecoveryMode.MAXIMUM)

    recovered = plan.with_recovered_image(Path("/out/.rawcd-work/old-disc/image.iso"))

    assert recovered.input_path == Path("/media/OLD_DISC")
    assert recovered.recovered_image_path == Path("/out/.rawcd-work/old-disc/image.iso")
    assert recovered.active_path == Path("/out/.rawcd-work/old-disc/image.iso")
    assert recovered.source.state is SourceState.RECOVERED_IMAGE
    assert recovered.source.label == "OLD_DISC"


def test_conversion_request_keeps_source_paths_and_exposes_source_plans(
    tmp_path: Path,
) -> None:
    source_paths = [
        Path("/media/disc/VIDEO_TS/VTS_01_1.VOB"),
        Path("/media/disc/VIDEO_TS/VTS_01_2.VOB"),
    ]

    request = ConversionRequest(
        source_paths=source_paths,
        output_dir=tmp_path,
        recovery_mode=RecoveryMode.MAXIMUM,
    )

    assert request.source_paths == source_paths
    assert [plan.input_path for plan in request.source_plans] == source_paths
    assert [plan.source.path for plan in request.source_plans] == source_paths
    assert all(plan.recovery_requested for plan in request.source_plans)
