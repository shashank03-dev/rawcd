from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import isfinite
from typing import Iterable

from rawcd.models import FrameRange, FrameState
from rawcd.repair import parse_freezedetect_output


class DamageSeverity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


@dataclass(frozen=True)
class DamageRange:
    start_seconds: float
    end_seconds: float
    state: FrameState
    severity: DamageSeverity
    reason: str

    def __post_init__(self) -> None:
        if not isfinite(self.start_seconds) or not isfinite(self.end_seconds):
            raise ValueError("damage range timestamps must be finite")
        if self.start_seconds < 0:
            raise ValueError("start_seconds must be greater than or equal to zero")
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")
        object.__setattr__(self, "state", FrameState(self.state))
        object.__setattr__(self, "severity", DamageSeverity(self.severity))
        object.__setattr__(self, "start_seconds", _round_seconds(self.start_seconds))
        object.__setattr__(self, "end_seconds", _round_seconds(self.end_seconds))


@dataclass(frozen=True)
class DamageReport:
    ranges: tuple[DamageRange, ...]
    severity: DamageSeverity


class DamageDetector:
    def __init__(
        self,
        frame_rate: str | int | float = "25/1",
        minimum_freeze_duration: float = 0.5,
    ) -> None:
        self.frame_rate = _parse_frame_rate(frame_rate)
        self.minimum_freeze_duration = minimum_freeze_duration

    def detect(
        self,
        freeze_stderr: str = "",
        ffmpeg_stderr: str = "",
        missing_frame_markers: Iterable[DamageRange | FrameRange] = (),
    ) -> DamageReport:
        ranges: list[DamageRange] = []
        ranges.extend(self._freeze_ranges(freeze_stderr))
        ranges.extend(self._decode_warning_ranges(ffmpeg_stderr))
        ranges.extend(
            self._coerce_missing_marker(marker) for marker in missing_frame_markers
        )

        normalized = _normalize_ranges(ranges)
        return DamageReport(
            ranges=normalized,
            severity=_max_severity([damage_range.severity for damage_range in normalized]),
        )

    def _freeze_ranges(self, stderr: str) -> list[DamageRange]:
        ranges: list[DamageRange] = []
        for issue in parse_freezedetect_output(stderr, self.minimum_freeze_duration):
            duration = issue.end_seconds - issue.start_seconds
            ranges.append(
                DamageRange(
                    start_seconds=issue.start_seconds,
                    end_seconds=issue.end_seconds,
                    state=FrameState.DAMAGED,
                    severity=_severity_for_duration(duration),
                    reason="freezedetect",
                )
            )
        return ranges

    def _decode_warning_ranges(self, stderr: str) -> list[DamageRange]:
        ranges: list[DamageRange] = []
        frame_duration = float(Fraction(1, 1) / self.frame_rate)
        for line in stderr.splitlines():
            if not _is_decode_warning(line):
                continue
            timestamp = _extract_timestamp(line)
            if timestamp is None:
                continue
            ranges.append(
                DamageRange(
                    start_seconds=timestamp,
                    end_seconds=timestamp + frame_duration,
                    state=FrameState.DAMAGED,
                    severity=DamageSeverity.MINOR,
                    reason="decode_warning",
                )
            )
        return ranges

    def _coerce_missing_marker(
        self,
        marker: DamageRange | FrameRange,
    ) -> DamageRange:
        if isinstance(marker, DamageRange):
            return marker
        return DamageRange(
            start_seconds=marker.start_seconds,
            end_seconds=marker.end_seconds,
            state=marker.state,
            severity=_severity_for_duration(
                marker.end_seconds - marker.start_seconds,
            ),
            reason=marker.reason or "missing_frames",
        )


_DECODE_WARNING_TERMS = (
    "error while decoding",
    "invalid data",
    "corrupt",
    "damaged",
    "concealing",
    "missing reference",
    "decode_slice_header",
)
_PTS_TIME = re.compile(r"\bpts_time[:=]\s*([0-9]+(?:\.[0-9]+)?)")
_CLOCK_TIME = re.compile(
    r"\btime[:=]\s*([0-9]{1,2}):([0-9]{2}):([0-9]{2}(?:\.[0-9]+)?)"
)
_SECONDS_TIME = re.compile(r"\btime[:=]\s*([0-9]+(?:\.[0-9]+)?)")


def _is_decode_warning(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in _DECODE_WARNING_TERMS)


def _extract_timestamp(line: str) -> float | None:
    match = _PTS_TIME.search(line)
    if match is not None:
        return float(match.group(1))

    match = _CLOCK_TIME.search(line)
    if match is not None:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    match = _SECONDS_TIME.search(line)
    if match is not None:
        return float(match.group(1))

    return None


def _normalize_ranges(ranges: Iterable[DamageRange]) -> tuple[DamageRange, ...]:
    sorted_ranges = sorted(
        ranges,
        key=lambda damage_range: (
            damage_range.start_seconds,
            damage_range.end_seconds,
            damage_range.reason,
        ),
    )
    if not sorted_ranges:
        return ()

    normalized: list[DamageRange] = [sorted_ranges[0]]
    for damage_range in sorted_ranges[1:]:
        current = normalized[-1]
        if damage_range.start_seconds <= current.end_seconds + 1e-9:
            normalized[-1] = _merge_ranges(current, damage_range)
        else:
            normalized.append(damage_range)

    return tuple(normalized)


def _merge_ranges(left: DamageRange, right: DamageRange) -> DamageRange:
    return DamageRange(
        start_seconds=min(left.start_seconds, right.start_seconds),
        end_seconds=max(left.end_seconds, right.end_seconds),
        state=_merge_state(left.state, right.state),
        severity=_max_severity([left.severity, right.severity]),
        reason=", ".join(_unique_reasons((left.reason, right.reason))),
    )


def _merge_state(left: FrameState, right: FrameState) -> FrameState:
    if FrameState.MISSING in (left, right):
        return FrameState.MISSING
    return left


def _unique_reasons(reasons: Iterable[str]) -> tuple[str, ...]:
    unique: list[str] = []
    for reason in reasons:
        if reason and reason not in unique:
            unique.append(reason)
    return tuple(unique)


def _severity_for_duration(duration_seconds: float) -> DamageSeverity:
    if duration_seconds > 2.0:
        return DamageSeverity.MAJOR
    if duration_seconds >= 0.5:
        return DamageSeverity.MODERATE
    return DamageSeverity.MINOR


def _max_severity(severities: Iterable[DamageSeverity]) -> DamageSeverity:
    ordered = {
        DamageSeverity.MINOR: 0,
        DamageSeverity.MODERATE: 1,
        DamageSeverity.MAJOR: 2,
    }
    highest = DamageSeverity.MINOR
    for severity in severities:
        normalized = DamageSeverity(severity)
        if ordered[normalized] > ordered[highest]:
            highest = normalized
    return highest


def _parse_frame_rate(frame_rate: str | int | float) -> Fraction:
    try:
        rate = Fraction(str(frame_rate))
    except ValueError as exc:
        raise ValueError("frame_rate must be a positive number or fraction") from exc
    if rate <= 0:
        raise ValueError("frame_rate must be greater than zero")
    return rate


def _round_seconds(seconds: float) -> float:
    rounded = round(seconds, 10)
    if rounded == 0:
        return 0.0
    return rounded


__all__ = [
    "DamageDetector",
    "DamageRange",
    "DamageReport",
    "DamageSeverity",
]
