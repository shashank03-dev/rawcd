from dataclasses import asdict
from math import inf
from pathlib import Path

import pytest

from rawcd.models import (
    ExportProfile,
    FrameRange,
    FrameState,
    FrameTimeline,
    ProviderCapability,
    ProviderKind,
    RecoveryMode,
    RestoreLane,
    RestoreMode,
    RestoreReport,
    RestoreSource,
    SourceState,
)


def test_restore_mode_enum_values_are_stable_api_strings() -> None:
    assert RestoreLane.HOME.value == "home"
    assert RestoreLane.PRO.value == "pro"
    assert RestoreMode.FAITHFUL.value == "faithful"
    assert RestoreMode.ENHANCED.value == "enhanced"
    assert RecoveryMode.QUICK.value == "quick"
    assert RecoveryMode.MAXIMUM.value == "maximum"


def test_source_state_enum_values_are_stable_api_strings() -> None:
    assert SourceState.MOUNTED.value == "mounted"
    assert SourceState.RECOVERED_IMAGE.value == "recovered_image"
    assert SourceState.DIRECT_FILE.value == "direct_file"
    assert SourceState.UNAVAILABLE.value == "unavailable"


def test_frame_state_enum_values_are_stable_api_strings() -> None:
    assert [state.value for state in FrameState] == [
        "original",
        "damaged",
        "missing",
        "interpolated",
        "generated",
        "enhanced",
        "skipped",
    ]


def test_provider_enum_values_are_stable_api_strings() -> None:
    assert [kind.value for kind in ProviderKind] == [
        "open_local",
        "managed_local",
        "ollama",
        "topaz",
        "cloud",
    ]
    assert [capability.value for capability in ProviderCapability] == [
        "interpolation",
        "inpainting",
        "denoise",
        "deinterlace",
        "upscale",
        "stabilization",
        "color_correction",
        "artifact_cleanup",
        "preview_render",
    ]


def test_export_profile_values_are_stable_api_strings() -> None:
    assert [profile.value for profile in ExportProfile] == [
        "home_mp4",
        "prores_422_hq",
        "dnxhr_hqx",
        "ffv1_mkv",
    ]


def test_restore_source_captures_path_state_and_recovery_mode() -> None:
    source = RestoreSource(
        path=Path("/media/disc/VIDEO_TS"),
        state=SourceState.MOUNTED,
        label="VIDEO_TS",
        recovery_mode=RecoveryMode.MAXIMUM,
    )

    assert source.path == Path("/media/disc/VIDEO_TS")
    assert source.state is SourceState.MOUNTED
    assert source.label == "VIDEO_TS"
    assert source.recovery_mode is RecoveryMode.MAXIMUM


def test_frame_range_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="end_seconds"):
        FrameRange(
            start_seconds=10.0,
            end_seconds=9.5,
            state=FrameState.DAMAGED,
        )


def test_frame_range_rejects_invalid_start_time() -> None:
    with pytest.raises(ValueError, match="start_seconds"):
        FrameRange(
            start_seconds=-0.1,
            end_seconds=1.0,
            state=FrameState.DAMAGED,
        )


def test_frame_range_rejects_non_finite_timestamps() -> None:
    with pytest.raises(ValueError, match="finite"):
        FrameRange(
            start_seconds=1.0,
            end_seconds=inf,
            state=FrameState.DAMAGED,
        )


def test_report_defaults_are_isolated_immutable_and_serializable() -> None:
    damaged_range = FrameRange(
        start_seconds=1.0,
        end_seconds=1.5,
        state=FrameState.DAMAGED,
        reason="freeze",
    )
    first = RestoreReport(
        warnings=("first warning",),
        timeline=FrameTimeline(ranges=(damaged_range,)),
    )
    second = RestoreReport()

    with pytest.raises(AttributeError):
        first.warnings.append("another warning")
    with pytest.raises(AttributeError):
        first.timeline.ranges.append(damaged_range)

    assert second.warnings == ()
    assert second.timeline.ranges == ()
    assert asdict(first) == {
        "lane": RestoreLane.HOME,
        "mode": RestoreMode.FAITHFUL,
        "recovery_mode": RecoveryMode.QUICK,
        "clips": 0,
        "warnings": ("first warning",),
        "timeline": {
            "ranges": (
                {
                    "start_seconds": 1.0,
                    "end_seconds": 1.5,
                    "state": FrameState.DAMAGED,
                    "reason": "freeze",
                },
            ),
            "duration_seconds": None,
            "frame_rate": None,
        },
    }
