from rawcd.models import FrameRange, FrameState
from rawcd.timeline import FrameTimeline


def test_timeline_builds_from_duration_frame_rate_and_known_damage() -> None:
    timeline = FrameTimeline.from_duration(
        duration_seconds=4.0,
        frame_rate="2/1",
        known_damaged_ranges=(
            FrameRange(
                start_seconds=1.0,
                end_seconds=2.0,
                state=FrameState.DAMAGED,
                reason="freezedetect",
            ),
        ),
    )

    assert timeline.ranges == (
        FrameRange(0.0, 1.0, FrameState.ORIGINAL, ""),
        FrameRange(1.0, 2.0, FrameState.DAMAGED, "freezedetect"),
        FrameRange(2.0, 4.0, FrameState.ORIGINAL, ""),
    )
    assert timeline.summary() == {
        "duration_seconds": 4.0,
        "frame_rate": "2/1",
        "total_frames": 8,
        "range_counts": {
            "original": 2,
            "damaged": 1,
            "missing": 0,
            "interpolated": 0,
            "generated": 0,
            "enhanced": 0,
            "skipped": 0,
        },
        "frame_counts": {
            "original": 6,
            "damaged": 2,
            "missing": 0,
            "interpolated": 0,
            "generated": 0,
            "enhanced": 0,
            "skipped": 0,
        },
        "seconds": {
            "original": 3.0,
            "damaged": 1.0,
            "missing": 0.0,
            "interpolated": 0.0,
            "generated": 0.0,
            "enhanced": 0.0,
            "skipped": 0.0,
        },
    }


def test_mark_range_overlays_overlapping_ranges_with_stable_summary() -> None:
    timeline = FrameTimeline.from_duration(duration_seconds=3.0, frame_rate=2)

    timeline.mark_range(0.5, 2.5, FrameState.DAMAGED, "freeze")
    timeline.mark_range(1.0, 1.5, FrameState.MISSING, "decode gap")
    timeline.mark_range(2.0, 3.0, FrameState.INTERPOLATED, "rife")

    assert timeline.ranges == (
        FrameRange(0.0, 0.5, FrameState.ORIGINAL, ""),
        FrameRange(0.5, 1.0, FrameState.DAMAGED, "freeze"),
        FrameRange(1.0, 1.5, FrameState.MISSING, "decode gap"),
        FrameRange(1.5, 2.0, FrameState.DAMAGED, "freeze"),
        FrameRange(2.0, 3.0, FrameState.INTERPOLATED, "rife"),
    )
    assert timeline.summary()["range_counts"] == {
        "original": 1,
        "damaged": 2,
        "missing": 1,
        "interpolated": 1,
        "generated": 0,
        "enhanced": 0,
        "skipped": 0,
    }
    assert timeline.summary()["frame_counts"] == {
        "original": 1,
        "damaged": 2,
        "missing": 1,
        "interpolated": 2,
        "generated": 0,
        "enhanced": 0,
        "skipped": 0,
    }
