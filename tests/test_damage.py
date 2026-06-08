from rawcd.damage import DamageDetector, DamageRange, DamageSeverity
from rawcd.models import FrameState
from rawcd.repair import FrameIssueKind, parse_freezedetect_output


def test_existing_freeze_parser_behavior_is_unchanged() -> None:
    stderr = """
    [freezedetect @ 0x123] freeze_start: 10.48
    [freezedetect @ 0x123] freeze_duration: 1.12
    [freezedetect @ 0x123] freeze_end: 11.60
    """

    issues = parse_freezedetect_output(stderr, minimum_duration=0.5)

    assert len(issues) == 1
    assert issues[0].kind is FrameIssueKind.FROZEN_RANGE
    assert issues[0].start_seconds == 10.48
    assert issues[0].end_seconds == 11.60
    assert issues[0].duration_seconds == 1.12


def test_damage_detector_normalizes_freeze_only_input() -> None:
    stderr = """
    [freezedetect @ 0x123] freeze_start: 10.48
    [freezedetect @ 0x123] freeze_duration: 1.12
    [freezedetect @ 0x123] freeze_end: 11.60
    """

    report = DamageDetector(frame_rate="25/1").detect(freeze_stderr=stderr)

    assert report.severity is DamageSeverity.MODERATE
    assert report.ranges == (
        DamageRange(
            start_seconds=10.48,
            end_seconds=11.6,
            state=FrameState.DAMAGED,
            severity=DamageSeverity.MODERATE,
            reason="freezedetect",
        ),
    )


def test_damage_detector_normalizes_ffmpeg_decode_warnings() -> None:
    stderr = """
    [mpeg2video @ 0x123] error while decoding MB 20 14 pts_time:7.00
    [mpeg2video @ 0x123] concealing 45 DC, 45 AC, 45 MV errors in P frame pts_time:7.04
    """

    report = DamageDetector(frame_rate="25/1").detect(ffmpeg_stderr=stderr)

    assert report.severity is DamageSeverity.MINOR
    assert report.ranges == (
        DamageRange(
            start_seconds=7.0,
            end_seconds=7.08,
            state=FrameState.DAMAGED,
            severity=DamageSeverity.MINOR,
            reason="decode_warning",
        ),
    )


def test_damage_detector_combines_missing_frame_markers_with_other_damage() -> None:
    freeze_stderr = """
    [freezedetect @ 0x123] freeze_start: 4.0
    [freezedetect @ 0x123] freeze_duration: 0.8
    [freezedetect @ 0x123] freeze_end: 4.8
    """

    report = DamageDetector(frame_rate=10).detect(
        freeze_stderr=freeze_stderr,
        missing_frame_markers=(
            DamageRange(
                start_seconds=4.5,
                end_seconds=5.1,
                state=FrameState.MISSING,
                severity=DamageSeverity.MODERATE,
                reason="missing_frames",
            ),
        ),
    )

    assert report.severity is DamageSeverity.MODERATE
    assert report.ranges == (
        DamageRange(
            start_seconds=4.0,
            end_seconds=5.1,
            state=FrameState.MISSING,
            severity=DamageSeverity.MODERATE,
            reason="freezedetect, missing_frames",
        ),
    )
